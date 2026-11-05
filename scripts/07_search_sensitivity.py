#!/usr/bin/env python3
"""
07_search_sensitivity.py -- search performance and sensitivity analysis.
Output: console only (the figures are quoted in Supplementary Methods M3).

Quantifies the recall cost of requiring the coronary-artery-disease concept
block (block 3) in the database search, and the sensitivity of the review's
findings to the studies that block would have missed.

Inputs: the published extraction database and the reference bibliography, both
part of the deposit. Each bibliography entry carries two provenance fields,
xcaroute and xcablock3, which record how that study was retrieved.

Two modes:

    python 07_search_sensitivity.py
        the analysis. Reads the database and the bibliography only, so every
        reported figure is reproducible from the deposit.

    XCA_EXPORTS=/path/to/exports python 07_search_sensitivity.py --annotate
        writes the two provenance fields into the bibliography from the raw
        search and citation-chasing exports. Run once during database
        preparation. Those exports contain third-party abstracts and are not
        redistributed, so this mode is not runnable from the deposit; the fields
        it produces are, which is why the analysis reads them rather than
        recomputing them. Rerun it after any fresh Zotero export of the
        bibliography, which would otherwise drop the fields.

Analyses
--------
1. Capture history of the included studies across the two retrieval routes.
2. Block-3 strata. A study is search-invisible if its record carries no block-3
   term AND it was retrieved only by citation chasing. The block-3 test is a
   text-level proxy applied by --annotate and cannot reproduce PubMed MeSH
   auto-explosion, so studies without block-3 terms that the database search
   nevertheless retrieved count as retrievable, not as invisible.
3. Chapman capture-recapture estimate of the eligible population.
4. The search-invisible stratum compared with the retrievable stratum on the 15
   feasibility criteria and CLAIM 2024 compliance, and a projection of the
   corpus-level proportions if the unretrieved studies resembled the invisible
   stratum.

NOTE: booleans() is duplicated from 04_tab_s7_feasibility.py. Any change to a
criterion must be made in all four places.
"""

from __future__ import annotations

import math
import os
import re
import statistics as st
import sys
from collections import Counter

import common as C

### Configuration

EXPORTS = os.environ.get("XCA_EXPORTS", "exports")

DB_SOURCES = [
    "pubmed_dublicates_removed.bib",
    "web_of_science_dublicates_removed.bib",
    "ieee_dublicates_removed.bib",
    "pubmed2426_03_06_26.nbib",
    "wos2426_03_06_26.ris",
    "IEEEXplore2426_03_06_26.ris",
]

CIT_SOURCES = [
    "lens_backward-search-raw.bib",
    "lens_forward-search-raw.bib",
    "backward.bib",
    "forward.bib",
]

BLOCK3 = [
    r"coronary stenos",
    r"coronary artery disease",
    r"coronary arterial disease",
    r"constriction, pathologic",
]

MIN_TEXT = 200
_title_of = {}
norm_title_cache = {}

### Annotation mode (--annotate)
# Run once, locally, to write xcaroute and xcablock3 into the bibliography from
# the raw search and citation-chasing exports. Those exports contain third-party
# abstracts and are not redistributed, so this mode is not runnable from the
# deposit; the fields it produces are, which is why the analysis below reads
# them from the bibliography rather than recomputing them.

### Readers

def norm_doi(doi):
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    doi = doi.rstrip(" .,;}")
    return doi or None


def _read_bib(path):
    import bibtexparser
    lib = bibtexparser.parse_file(path)
    out = []
    for entry in lib.entries:
        f = {x.key: x.value for x in entry.fields}
        out.append({"title": f.get("title", ""), "abstract": f.get("abstract", ""),
                    "keywords": f.get("keywords", ""), "doi": norm_doi(f.get("doi"))})
    return out


def _read_tagged(path, ti, ab, kw, do, indent=2):
    """Minimal RIS/nbib reader: TAG - value, continuation lines are indented."""
    recs, cur, last = [], {}, None
    for line in open(path, encoding="utf-8", errors="replace"):
        m = re.match(r"^([A-Z][A-Z0-9]{1,3})\s*-\s?(.*)$", line.rstrip("\n"))
        if m:
            last = m.group(1)
            cur.setdefault(last, []).append(m.group(2))
            if last == "ER":
                recs.append(cur)
                cur, last = {}, None
        elif line.startswith(" " * indent) and last:
            cur[last][-1] += " " + line.strip()
        elif not line.strip() and cur:
            recs.append(cur)
            cur, last = {}, None
    if cur:
        recs.append(cur)
    out = []
    for r in recs:
        join = lambda t: " ".join(r.get(t, []))
        doi = join(do)
        if do == "AID":  # PubMed stores the DOI as "<doi> [doi]"
            doi = next((a.split()[0] for a in r.get("AID", []) + r.get("LID", [])
                        if "[doi]" in a), "")
        out.append({"title": join(ti), "abstract": join(ab),
                    "keywords": join(kw) if isinstance(kw, str) else
                                " ; ".join(sum((r.get(k, []) for k in kw), [])),
                    "doi": norm_doi(doi)})
    return out


def norm_title(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def load_exports():
    """Return {doi: set(source files)} and {doi: pooled lower-case text}.
    Records without a DOI are keyed on their normalised title ("title:<...>")
    so that they can still be matched by title."""
    sources, text = {}, {}
    for name in DB_SOURCES + CIT_SOURCES:
        path = os.path.join(EXPORTS, name)
        if not os.path.exists(path):
            sys.exit(f"missing export: {path}")
        if name.endswith(".bib"):
            recs = _read_bib(path)
        elif name.endswith(".nbib"):
            recs = _read_tagged(path, "TI", "AB", ["MH", "OT"], "AID", indent=6)
        else:
            recs = _read_tagged(path, "TI", "AB", "KW", "DO")
        for r in recs:
            key = r["doi"] or ("title:" + norm_title(r["title"]))
            if key == "title:":
                continue
            r["doi"] = key
            _title_of[key] = r["title"]
            sources.setdefault(r["doi"], set()).add(name)
            blob = " ".join([r["title"], r["abstract"], r["keywords"]]).lower()
            if len(blob) > len(text.get(r["doi"], "")):
                text[r["doi"]] = blob
    return sources, text


def classify(srcs, blob):
    """Return (xcaroute, xcablock3)."""
    db = bool(srcs & set(DB_SOURCES))
    cit = bool(srcs & set(CIT_SOURCES))
    route = "both" if db and cit else "database" if db else "citation" if cit else "none"
    if not srcs:
        return route, "unmatched"
    if len(blob) < MIN_TEXT:
        return route, "untestable"
    if any(re.search(pat, blob) for pat in BLOCK3):
        return route, "present"
    return route, "absent"


### Bibliography rewriting

ENTRY = re.compile(r"(@\w+\{[^,]+,)(.*?)(\n\})", re.S)
FIELD = re.compile(r"^\s*xca(route|block3)\s*=.*$\n?", re.M)


def annotate(text, sources, blob_by_doi):
    """Add xcaroute and xcablock3 to every entry, keyed on its doi field."""
    counts = {"route": {}, "block3": {}}
    missing = []

    def repl(m):
        head, body, tail = m.group(1), m.group(2), m.group(3)
        body = FIELD.sub("", body)  # idempotent: drop any earlier annotation
        dm = re.search(r"\bdoi\s*=\s*\{([^}]*)\}", body)
        doi = norm_doi(dm.group(1)) if dm else None
        if doi is None:
            missing.append(head)
            return head + body + tail
        if doi not in sources:
            # title fallback: exported record without a DOI, or a DOI that
            # differs from the bibliography (e.g. chapter vs volume DOI)
            tm = re.search(r"\btitle\s*=\s*\{(.*?)\},?\s*$", body, re.S | re.M)
            nt = norm_title(re.sub(r"[{}]", "", tm.group(1))) if tm else ""
            hits = [k for k in sources if nt and len(nt) > 20 and
                    (k.startswith("title:") or True) and nt in norm_title_cache.get(k, "")]
            if len(hits) == 1:
                doi = hits[0]
        route, b3 = classify(sources.get(doi, set()), blob_by_doi.get(doi, ""))
        counts["route"][route] = counts["route"].get(route, 0) + 1
        counts["block3"][b3] = counts["block3"].get(b3, 0) + 1
        added = f"\n\txcaroute = {{{route}}},\n\txcablock3 = {{{b3}}},"
        return head + body.rstrip() + added + tail

    return ENTRY.sub(repl, text), counts, missing




def annotate_bibliography():
    """--annotate: rewrite the bibliography's provenance fields from the exports."""
    sources, blob_by_doi = load_exports()
    global norm_title_cache
    norm_title_cache = {k: norm_title(_title_of.get(k, "")) for k in sources}
    path = C.BIB_PATH
    text = open(path, encoding="utf-8").read()
    n_entries = len(re.findall(r"^@", text, re.M))
    new_text, counts, missing = annotate(text, sources, blob_by_doi)
    annotated = new_text.count("xcaroute = {")
    if annotated != n_entries - len(missing):
        sys.exit(f"annotated {annotated} of {n_entries} entries; aborting without writing")
    open(path, "w", encoding="utf-8").write(new_text)
    print(f"annotated {annotated} of {n_entries} entries in {path}")
    for key in ("route", "block3"):
        for value, n in sorted(counts[key].items(), key=lambda kv: -kv[1]):
            print(f"  xca{key:8s} {value:12s} {n:4d}")
    if missing:
        print(f"  {len(missing)} entries carry no doi field and were left unannotated")


### Analysis configuration

NR = ("", "not_reported", "not reported", "n/a")

CRITERIA = [
    "External validation", "Multi-centre", "Prospective validation",
    "Code availability", "Open dataset", "Model weights", "Explainability",
    "Real-time capability", "Inference time", "Target vessel",
    "Age reported", "Sex reported", "Presentation", "Annotator expertise",
    "Two or more annotators",
]


### Scoring logic, mirrored from 04_tab_s7_feasibility.py
def booleans(conn, pid):
    def val(f):
        r = conn.execute("SELECT value FROM extractions WHERE paper_id=? AND field_name=? "
                         "AND value IS NOT NULL AND value!=''", (pid, f)).fetchone()
        return (r[0].strip().lower() if r and r[0] else "")

    def any_like(pat, pos=None, exc=None):
        vs = [(r[0] or "").strip().lower() for r in conn.execute(
            "SELECT value FROM extractions WHERE paper_id=? AND field_name LIKE ? "
            "AND value IS NOT NULL AND value!=''", (pid, pat))]
        if not vs:
            return False
        if pos:
            return any(v in pos for v in vs)
        if exc:
            return any(v not in exc for v in vs)
        return True

    return [
        val("external_validation_used") == "y",
        val("multi_center") == "multi-center",
        val("prospective_validation") == "y",
        val("code_availability") in ("y", "partly"),
        any_like("dataset_accessibility__%", pos=["open"]),
        val("trained_model_available") == "y",
        any_like("explainability_technique__%"),
        val("real_time_capability") == "y",
        any_like("inference_time_reported__%", pos=["y"]),
        val("target_vessel") not in NR,
        val("age_reported") == "y",
        val("sex_reported") == "y",
        val("patient_presentation") not in NR,
        any_like("annotator_expertise__%", exc=list(NR) + ["unclear"]),
        any_like("annotator_count__%", pos=[str(n) for n in range(2, 30)] + [">=3"]),
    ]


def claim_pct(conn, pid):
    r = conn.execute("SELECT SUM(result='yes'), SUM(result='no') FROM checklist_results "
                     "WHERE checklist_name='CLAIM 2024' AND paper_id=?", (pid,)).fetchone()
    y, n = r[0] or 0, r[1] or 0
    return 100 * y / (y + n) if (y + n) else None


### Statistics
def mann_whitney(a, b):
    """Two-sided Mann-Whitney U with normal approximation and tie-corrected ranks."""
    pooled = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    rk, i = [0.0] * len(pooled), 0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        for k in range(i, j + 1):
            rk[k] = (i + j) / 2 + 1
        i = j + 1
    na, nb = len(a), len(b)
    ra = sum(rk[k] for k in range(len(pooled)) if pooled[k][1] == 0)
    u = ra - na * (na + 1) / 2
    z = (u - na * nb / 2) / math.sqrt(na * nb * (na + nb + 1) / 12)
    return z, math.erfc(abs(z) / math.sqrt(2))


def two_proportion(a, b):
    x1, n1, x2, n2 = sum(a), len(a), sum(b), len(b)
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return p1, p2, None
    return p1, p2, math.erfc(abs((p1 - p2) / se) / math.sqrt(2))


def chapman(n1, n2, m):
    """Chapman's bias-corrected Lincoln-Petersen estimator with its standard error."""
    n = (n1 + 1) * (n2 + 1) / (m + 1) - 1
    se = math.sqrt((n1 + 1) * (n2 + 1) * (n1 - m) * (n2 - m) / ((m + 1) ** 2 * (m + 2)))
    return n, se


### Analysis
def load_provenance(path=None):
    """Read xcaroute and xcablock3 per doi from the reference bibliography."""
    path = path or C.BIB_PATH
    text = open(path, encoding="utf-8").read()
    out = {}
    for m in ENTRY.finditer(text):
        body = m.group(2)   # ENTRY groups are (head, body, closing brace)
        field = lambda name: (re.search(r"\b" + name + r"\s*=\s*\{([^}]*)\}", body) or [None, None])[1] \
            if re.search(r"\b" + name + r"\s*=\s*\{([^}]*)\}", body) else None
        doi = norm_doi(field("doi"))
        route, b3 = field("xcaroute"), field("xcablock3")
        if doi and route and b3:
            out[doi] = (route, b3)
    if not out:
        sys.exit(f"{path} carries no xcaroute/xcablock3 fields; "
                 "run this script once with --annotate against the raw exports")
    return out


def main():
    conn = C.connect()
    papers = C.load_papers(conn)
    prov = load_provenance()
    dois = {r["id"]: norm_doi(r["doi"]) for r in conn.execute("SELECT id, doi FROM papers")}

    studies = []
    for p in papers:
        rec = prov.get(dois.get(p.paper_id))
        if rec is None:
            sys.exit(f"reference {p.ref} has no provenance fields in {C.BIB_PATH}")
        route, b3 = rec
        db, cit = route in ("database", "both"), route in ("citation", "both")
        if b3 == "unmatched":
            stratum = "unmatched"
        elif b3 == "untestable":
            stratum = "retrievable" if db else "untestable"
        elif b3 == "present":
            stratum = "retrievable"
        else:
            stratum = "retrievable" if db else "invisible"
        studies.append({"ref": p.ref, "db": db, "cit": cit, "stratum": stratum,
                        "bools": booleans(conn, p.paper_id),
                        "claim": claim_pct(conn, p.paper_id)})
    conn.close()

    matched = [s for s in studies if s["stratum"] != "unmatched"]
    print(f"Included studies: {len(studies)}; traceable in the exports: {len(matched)}")

    ### 1. Capture history
    cap = Counter(("both" if s["db"] and s["cit"] else "database only" if s["db"]
                   else "citation chasing only") for s in matched)
    print("\n1. Retrieval route")
    for k in ("database only", "both", "citation chasing only"):
        print(f"   {k:24s} {cap[k]:4d}")

    ### 2. Block-3 strata
    strat = Counter(s["stratum"] for s in matched)
    print("\n2. Block-3 strata")
    for k in ("retrievable", "invisible", "untestable"):
        print(f"   {k:24s} {strat[k]:4d}")

    ### 3. Capture-recapture
    n1 = sum(s["db"] for s in matched)
    n2 = sum(s["cit"] for s in matched)
    m = sum(s["db"] and s["cit"] for s in matched)
    n_hat, se = chapman(n1, n2, m)
    print(f"\n3. Chapman capture-recapture: n1 = {n1}, n2 = {n2}, overlap = {m}")
    print(f"   estimated eligible population {n_hat:.0f} "
          f"(95% CI {n_hat - 1.96 * se:.0f} to {n_hat + 1.96 * se:.0f})")
    print(f"   implied unretrieved {n_hat - len(matched):.0f}")
    print("   the routes are not independent (citation chasing is seeded by the "
          "database results), so this is closer to a floor than a ceiling")

    ### 4. Stratum comparison and projection
    inv = [s for s in matched if s["stratum"] == "invisible"]
    ret = [s for s in matched if s["stratum"] == "retrievable"]
    sig = lambda g: [sum(s["bools"]) for s in g]
    _, p = mann_whitney(sig(inv), sig(ret))
    print(f"\n4. Search-invisible (n = {len(inv)}) versus retrievable (n = {len(ret)})")
    print(f"   feasibility score {st.mean(sig(inv)):.2f} vs {st.mean(sig(ret)):.2f} "
          f"(p = {p:.3f})")
    ca = [s["claim"] for s in inv if s["claim"] is not None]
    cb = [s["claim"] for s in ret if s["claim"] is not None]
    _, p = mann_whitney(ca, cb)
    print(f"   CLAIM 2024        {st.mean(ca):.1f}% vs {st.mean(cb):.1f}% (p = {p:.3f})")

    missing = round(n_hat - len(matched))
    print(f"\n   {'criterion':24s}{'invisible':>11s}{'retrievable':>13s}{'p':>8s}"
          f"{'corpus':>9s}{'projected':>11s}{'shift':>8s}")
    for i, label in enumerate(CRITERIA):
        p1, p2, pv = two_proportion([s["bools"][i] for s in inv],
                                    [s["bools"][i] for s in ret])
        cur = sum(s["bools"][i] for s in studies) / len(studies)
        proj = (cur * len(studies) + p1 * missing) / (len(studies) + missing)
        ptxt = f"{pv:8.3f}" if pv is not None else f"{'-':>8s}"
        print(f"   {label:24s}{p1 * 100:10.0f}%{p2 * 100:12.0f}%{ptxt}"
              f"{cur * 100:8.0f}%{proj * 100:10.0f}%{(proj - cur) * 100:+7.1f}pp")

    inv_m = st.mean(sig(inv))
    cur_m = st.mean([sum(s["bools"]) for s in studies])
    proj_m = (cur_m * len(studies) + inv_m * missing) / (len(studies) + missing)
    print(f"   {'mean score':24s}{inv_m:11.2f}{st.mean(sig(ret)):13.2f}{'':8s}"
          f"{cur_m:9.2f}{proj_m:11.2f}{proj_m - cur_m:+8.2f}")

    unt = [s for s in matched if s["stratum"] == "untestable"]
    if unt:
        alt = inv + unt
        alt_r = [sum(s["bools"][i] for s in alt) / len(alt) for i in range(15)]
        worst = max(abs((cur_c * len(studies) + alt_r[i] * missing) / (len(studies) + missing)
                        - cur_c)
                    for i, cur_c in enumerate(
                        sum(s["bools"][i] for s in studies) / len(studies)
                        for i in range(15)))
        print(f"\n   robustness: assigning the {len(unt)} untestable studies to the "
              f"invisible stratum changes no projected proportion by more than "
              f"{worst * 100:.1f} percentage points")

    ### 5. Temporal trend and venue composition under the projection
    # Reviewer 2 (search sensitivity): the projection above covers proportions
    # and the mean score. The temporal claims (Results, Spearman rho between
    # publication year and score) and the venue comparison (Table S11) could
    # still be affected if the missed studies were concentrated in time or in
    # one venue type. Compare year and venue between strata, test the trend
    # within each stratum, and resample 57 studies from the invisible stratum
    # into the corpus.
    import random

    def spearman(x, y):
        """Spearman rho via ranks with ties averaged (no scipy dependency)."""
        def ranks(v):
            order = sorted(range(len(v)), key=lambda i: v[i])
            r, i = [0.0] * len(v), 0
            while i < len(v):
                j = i
                while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                    j += 1
                for k in range(i, j + 1):
                    r[order[k]] = (i + j) / 2 + 1
                i = j + 1
            return r
        rx, ry = ranks(x), ranks(y)
        mx, my = st.mean(rx), st.mean(ry)
        num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
        den = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
        return num / den if den else float("nan")

    years = {p.ref: p.year for p in papers}
    venue = {p.ref: p.pub_type for p in papers}
    print("\n5. Temporal trend and venue composition")
    for label, grp in (("invisible", inv), ("retrievable", ret)):
        ys = [years[s["ref"]] for s in grp]
        jr = sum(venue[s["ref"]] == "journal" for s in grp) / len(grp)
        rho = spearman(ys, sig(grp))
        print(f"   {label:12s} median year {st.median(ys):.0f}, "
              f"from 2023 {100 * sum(y >= 2023 for y in ys) / len(ys):.0f}%, "
              f"journal {100 * jr:.0f}%, within-stratum rho(year, score) = {rho:.2f}")
    all_y = [years[s["ref"]] for s in studies]
    all_s = [sum(s["bools"]) for s in studies]
    base = spearman(all_y, all_s)
    rng = random.Random(20260721)
    rhos = []
    for _ in range(2000):
        draw = [rng.choice(inv) for _ in range(missing)]
        rhos.append(spearman(all_y + [years[s["ref"]] for s in draw],
                             all_s + [sum(s["bools"]) for s in draw]))
    rhos.sort()
    print(f"   corpus rho(year, score) = {base:.2f}; with {missing} studies resampled "
          f"from the invisible stratum: mean {st.mean(rhos):.2f} "
          f"(2.5-97.5%: {rhos[49]:.2f} to {rhos[1949]:.2f})")


if __name__ == "__main__":
    if "--annotate" in sys.argv:
        annotate_bibliography()
    else:
        main()