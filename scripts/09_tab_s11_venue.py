#!/usr/bin/env python3
"""
09_tab_s11_venue.py -- Table S11: journal versus conference subset analysis.
Output: results/tables/TableS11_venue.docx

Compares journal articles with conference papers on the 15 feasibility criteria,
the composite score and CLAIM 2024 compliance. Requested by Reviewer 1 as a
subset analysis strengthening internal validity.

Tests: two-proportion z test for the binary criteria, Mann-Whitney U (normal
approximation, tie-corrected ranks) for the composite score and CLAIM
compliance. Implemented here in the standard library so the script adds no
dependency beyond the existing requirements.

NOTE: booleans() is duplicated from 04_tab_s7_feasibility.py. Any change to a
criterion must be made in all four places.
"""

import math
import os
import statistics as st

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS11_venue.docx")

NR = ("", "not_reported", "not reported", "n/a")

LABELS = [
    "External validation", "Multi-centre data", "Prospective validation",
    "Code availability", "Open dataset", "Model weights shared",
    "Explainability method", "Real-time capability", "Inference time reported",
    "Target vessel specified", "Patient age reported", "Patient sex reported",
    "Clinical presentation reported", "Annotator expertise stated",
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
def two_proportion(a, b):
    """Two-sided z test for a difference in proportions. Returns (p1, p2, p)."""
    x1, n1, x2, n2 = sum(a), len(a), sum(b), len(b)
    p1, p2 = x1 / n1, x2 / n2
    p = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    if se == 0:
        return p1, p2, None
    return p1, p2, math.erfc(abs((p1 - p2) / se) / math.sqrt(2))


def mann_whitney(a, b):
    """Two-sided Mann-Whitney U, normal approximation with tie-corrected ranks."""
    pooled = sorted([(v, 0) for v in a] + [(v, 1) for v in b])
    ranks, i = [0.0] * len(pooled), 0
    while i < len(pooled):
        j = i
        while j + 1 < len(pooled) and pooled[j + 1][0] == pooled[i][0]:
            j += 1
        for k in range(i, j + 1):
            ranks[k] = (i + j) / 2 + 1
        i = j + 1
    na, nb = len(a), len(b)
    ra = sum(ranks[k] for k in range(len(pooled)) if pooled[k][1] == 0)
    u = ra - na * (na + 1) / 2
    z = (u - na * nb / 2) / math.sqrt(na * nb * (na + nb + 1) / 12)
    return z, math.erfc(abs(z) / math.sqrt(2))


def fmt_p(p):
    if p is None:
        return "n.a."
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


conn = C.connect()
papers = C.load_papers(conn)
rows = []
for p in papers:
    rows.append({"type": p.pub_type, "bools": booleans(conn, p.paper_id),
                 "sigma": sum(booleans(conn, p.paper_id)), "claim": claim_pct(conn, p.paper_id)})
conn.close()

J = [r for r in rows if r["type"] == "journal"]
K = [r for r in rows if r["type"] == "conference"]
N = len(rows)

### Console summary
print(f"Table S11: journal (n={len(J)}) versus conference (n={len(K)}), total {N}")
sj, sk = [r["sigma"] for r in J], [r["sigma"] for r in K]
_, p_sigma = mann_whitney(sj, sk)
print(f"  composite score: {st.mean(sj):.2f} vs {st.mean(sk):.2f} "
      f"(median {st.median(sj):.0f} vs {st.median(sk):.0f}) p={fmt_p(p_sigma)}")
cj = [r["claim"] for r in J if r["claim"] is not None]
ck = [r["claim"] for r in K if r["claim"] is not None]
_, p_claim = mann_whitney(cj, ck)
print(f"  CLAIM 2024:      {st.mean(cj):.1f}% vs {st.mean(ck):.1f}% p={fmt_p(p_claim)}")

### DOCX
C.ensure_dirs()
doc = Document()
sec = doc.sections[0]
sec.top_margin = sec.bottom_margin = Cm(1.8)
sec.left_margin = sec.right_margin = Cm(2.0)

title = doc.add_paragraph()
r = title.add_run("Table S11. ")
r.bold = True
r.font.size = Pt(11)
r.font.name = "Arial"
r = title.add_run("Translational feasibility by publication type "
                  f"(journal articles n = {len(J)}, conference papers n = {len(K)})")
r.font.size = Pt(11)
r.font.name = "Arial"

HEAD = ["Criterion", "Journal", "Conference", "Difference", "p"]
WIDTHS = [Cm(6.4), Cm(2.4), Cm(2.6), Cm(2.6), Cm(2.0)]

# Raw p-values for every testable comparison, then Holm adjustment over all of
# them (prospective validation and target vessel are not testable: identical
# in both strata). Revision: the ">=6/15" row was removed with the cut-points.
raw = []
for i, label in enumerate(LABELS):
    p1, p2, pv = two_proportion([r["bools"][i] for r in J], [r["bools"][i] for r in K])
    raw.append([label, f"{p1 * 100:.0f}%", f"{p2 * 100:.0f}%", f"{(p1 - p2) * 100:+.0f} pp", pv])
raw.append(["Composite score, mean (median)",
            f"{st.mean(sj):.2f} ({st.median(sj):.0f})",
            f"{st.mean(sk):.2f} ({st.median(sk):.0f})",
            f"{st.mean(sj) - st.mean(sk):+.2f}", p_sigma])
raw.append(["CLAIM 2024 compliance, mean (median)",
            f"{st.mean(cj):.1f}% ({st.median(cj):.0f}%)",
            f"{st.mean(ck):.1f}% ({st.median(ck):.0f}%)",
            f"{st.mean(cj) - st.mean(ck):+.1f} pp", p_claim])


def holm(pvals):
    """Holm step-down adjusted p-values (None entries are left untested)."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    m = len(idx)
    order = sorted(idx, key=lambda i: pvals[i])
    adj, running = {}, 0.0
    for rank, i in enumerate(order):
        running = max(running, (m - rank) * pvals[i])
        adj[i] = min(running, 1.0)
    return [adj.get(i) for i in range(len(pvals))], m


adjusted, n_tests = holm([row[4] for row in raw])
print(f"  Holm adjustment over {n_tests} comparisons")
body = [tuple(row[:4]) + (fmt_p(pa),) for row, pa in zip(raw, adjusted)]
for row, pa in zip(raw, adjusted):
    if row[4] is not None:
        print(f"  {row[0]:38s} raw {fmt_p(row[4]):>7s}  Holm {fmt_p(pa):>7s}")

table = doc.add_table(rows=len(body) + 1, cols=len(HEAD))
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.style = "Table Grid"


def shade(cell, fill):
    tcPr = cell._element.get_or_add_tcPr()
    tcPr.append(tcPr.makeelement(qn("w:shd"), {qn("w:fill"): fill, qn("w:val"): "clear"}))


def put(cell, text, *, bold=False, size=9, fill=None, width=None, align_left=False):
    cell.text = ""
    para = cell.paragraphs[0]
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(1)
    if not align_left:
        para.alignment = 1
    run = para.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Arial"
    if fill:
        shade(cell, fill)
    if width is not None:
        cell.width = width


for j, h in enumerate(HEAD):
    put(table.rows[0].cells[j], h, bold=True, fill="F2F2F2", width=WIDTHS[j],
        align_left=(j == 0))
for i, row in enumerate(body, start=1):
    bold = i > len(LABELS)  # the two continuous rows
    for j, v in enumerate(row):
        put(table.rows[i].cells[j], v, bold=bold, width=WIDTHS[j], align_left=(j == 0))

note = doc.add_paragraph()
r = note.add_run(
    "Proportions compared with a two-sided z test for a difference in proportions; "
    "composite score and CLAIM 2024 compliance compared with the Mann-Whitney U test "
    "(normal approximation, tie-corrected ranks). p-values are Holm-adjusted over the "
    f"{n_tests} comparisons. Prospective validation and target vessel were identical in "
    "both strata, so no test is reported for them. pp, percentage points.")
r.font.size = Pt(8)
r.font.name = "Arial"

doc.save(OUT_PATH)
print(f"Saved -> {OUT_PATH}")