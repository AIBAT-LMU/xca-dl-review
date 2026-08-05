#!/usr/bin/env python3
"""
04_clinical_readiness.py -- numbers for the "Reporting quality and risk of bias"
chapter (CLAIM 2024, QUADAS-2, and the 15-point feasibility scorecard).

Prints the figures used in the text; no DOCX (the visuals are Figures 3 & 4).

Notes
-----
* CLAIM per-study compliance = yes/(yes+no); item 37 was corrected during
  database preparation (it required a measure of statistical uncertainty).
* QUADAS-2 stores signalling questions and the three applicability ratings; the
  four risk-of-bias domain ratings are DERIVED here the standard way
  (all signalling 'yes' -> low; any 'no' -> high; else unclear).
* The feasibility score is 15 booleans across six domains, read from the CURRENT
  field names (the archived generate_feasibility_json.py used several that have
  since been renamed).
"""

import statistics
from collections import defaultdict

import common as C

NR = ("", "not_reported", "not reported", "n/a")

conn = C.connect()
papers = C.load_papers(conn)
ref_of = {p.paper_id: p.ref for p in papers}
year = {p.paper_id: p.year for p in papers}


def val(pid, f):
    r = conn.execute("SELECT value FROM extractions WHERE paper_id=? AND field_name=? "
                     "AND value IS NOT NULL AND value!=''", (pid, f)).fetchone()
    return (r[0].strip().lower() if r and r[0] else "")


def any_like(pid, pat, pos=None, exc=None):
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


# ── CLAIM ──
claim = {}
for r in conn.execute(
        "SELECT paper_id, SUM(result='yes') y, SUM(result='no') n "
        "FROM checklist_results WHERE checklist_name='CLAIM 2024' GROUP BY paper_id"):
    if r["y"] + r["n"]:
        claim[r["paper_id"]] = 100 * r["y"] / (r["y"] + r["n"])
cv = sorted(claim.values())
print(f"CLAIM: n={len(cv)}  median {statistics.median(cv):.0f}%  "
      f"range {min(cv):.0f}-{max(cv):.0f}%")

# ── QUADAS-2 (derive RoB from signalling) ──
sig = defaultdict(dict)
for r in conn.execute("SELECT paper_id, item_id, result FROM checklist_results "
                      "WHERE checklist_name='QUADAS-2'"):
    sig[r["paper_id"]][r["item_id"]] = (r["result"] or "").strip().lower()
ROB = {"Patient selection": ["1.1", "1.2", "1.3"], "Index test": ["2.1", "2.2"],
       "Reference standard": ["3.1", "3.2"], "Flow & timing": ["4.1", "4.2", "4.3", "4.4"]}
APP = {"Patient selection": "1.app", "Index test": "2.app", "Reference standard": "3.app"}


def derive(vals):
    if any(v == "no" for v in vals):
        return "high"
    if all(v == "yes" for v in vals):
        return "low"
    return "unclear"


dist = defaultdict(lambda: defaultdict(int))
qlow = {}
for pid, d in sig.items():
    low = 0
    for name, qs in ROB.items():
        r = derive([d.get(q, "unclear") for q in qs])
        dist[("RoB", name)][r] += 1
        low += r == "low"
    for name, it in APP.items():
        r = d.get(it, "unclear")
        dist[("App", name)][r] += 1
        low += r == "low"
    qlow[pid] = low
print("\nQUADAS-2 risk-of-bias / applicability (low / unclear / high):")
for (kind, name), d in dist.items():
    tot = sum(d.values())
    print(f"  {kind} {name:20s} {round(100*d['low']/tot):3d}% / "
          f"{round(100*d['unclear']/tot):3d}% / {round(100*d['high']/tot):3d}%")
print(f"  studies 7/7 low: {sum(v==7 for v in qlow.values())} "
      f"-> refs {sorted(ref_of[p] for p,v in qlow.items() if v==7)}")

# ── Feasibility scorecard (15 booleans) ──
score = {}
for p in papers:
    pid = p.paper_id
    b = [val(pid, "external_validation_used") == "y",
         val(pid, "multi_center") == "multi-center",
         val(pid, "prospective_validation") == "y",
         val(pid, "code_availability") in ("y", "partly"),
         any_like(pid, "dataset_accessibility__%", pos=["open"]),
         val(pid, "trained_model_available") == "y",
         any_like(pid, "explainability_technique__%"),
         val(pid, "real_time_capability") == "y",
         any_like(pid, "inference_time_reported__%", pos=["y"]),
         val(pid, "target_vessel") not in NR,
         val(pid, "age_reported") == "y",
         val(pid, "sex_reported") == "y",
         val(pid, "patient_presentation") not in NR,
         any_like(pid, "annotator_expertise__%", exc=list(NR) + ["unclear"]),
         any_like(pid, "annotator_count__%", pos=[str(n) for n in range(2, 30)])]
    score[pid] = sum(b)
sv = list(score.values())
ext = {p.paper_id for p in papers if val(p.paper_id, "external_validation_used") == "y"}
code = {p.paper_id for p in papers if val(p.paper_id, "code_availability") in ("y", "partly")}
print(f"\nFeasibility Σ (0-15): range {min(sv)}-{max(sv)}  mean {statistics.mean(sv):.1f}  "
      f"met-all-15: {sum(v==15 for v in sv)}")
for lo, hi in [(2016, 2019), (2020, 2022), (2023, 2026)]:
    ids = [p for p in score if lo <= year[p] <= hi]
    ge6 = sum(score[p] >= 6 for p in ids)
    print(f"  {lo}-{hi}: mean {statistics.mean(score[p] for p in ids):.1f}  "
          f"≥6/15 {ge6} ({round(100*ge6/len(ids))}%)")
ge9 = sorted((p for p in score if score[p] >= 9), key=lambda p: ref_of[p])
print(f"  Σ≥9: {len(ge9)} studies -> refs {[ref_of[p] for p in ge9]}")
print(f"  external validation {len(ext)}, code {len(code)}, both {len(ext & code)}")
conn.close()
