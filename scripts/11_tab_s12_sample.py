#!/usr/bin/env python3
"""
11_tab_s12_sample.py -- Table S12: the random 10% validation sample.
Output: results/tables/TableS12_sample.docx

Lists the 20 studies (10% of N = 196) used for (a) the internal consistency
check, in which a second, blinded LLM rater re-extracted and re-appraised each
study from the parsed full text, and (b) the human gold-standard comparison,
in which two authors independently rated the same studies on CLAIM 2024 and
QUADAS-2 (Revision, Reviewer 1).

Provenance of the draw
----------------------
The sample was drawn in the extraction pipeline (PaperMole), not in this
repository: simple random sample of the included studies, seed 20260721,
drawn on the pipeline's internal paper ids. Those ids are not the manuscript
reference numbers (two papers excluded after extraction shift the numbering),
so the sample is pinned here by manuscript reference number after matching on
DOI. Re-running the draw therefore requires the pipeline database; this script
only renders the fixed list and pulls each study's descriptors from the
released database, using the same criteria logic as Table S7.

NOTE: booleans() is duplicated from 04_tab_s7_feasibility.py. Any change to a
criterion must be made in all five places.
"""

import os
from collections import defaultdict

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS12_sample.docx")

SEED = 20260721
SAMPLE_REFS = [2, 32, 45, 48, 52, 61, 70, 94, 96, 99,
               101, 111, 117, 147, 155, 156, 159, 175, 189, 191]
# Second sample: human gold-standard comparison (Revision; see 12_tab_s13_gold.py)
GOLD_REFS = [4, 5, 6, 10, 14, 15, 29, 42, 46, 47,
             57, 64, 82, 102, 107, 128, 143, 177, 180, 181]

NR = ("", "not_reported", "not reported", "n/a")

PRIORITY = ["Quantification", "Stenosis detection", "Classification",
            "Other detection", "Vessel segmentation", "Image processing"]
ABBR = {"Vessel segmentation": "VeSeg", "Stenosis detection": "StDet",
        "Classification": "Class", "Other detection": "OtDet",
        "Image processing": "ImPro", "Quantification": "Quant"}

conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)
by_ref = {p.ref: p for p in papers}
missing = [r for r in SAMPLE_REFS + GOLD_REFS if r not in by_ref]
assert not missing, f"sample refs not in database: {missing}"

by_domain, _ = C.application_domains(conn, papers)
paper_domains = C.domains_per_paper(by_domain, papers)


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


def booleans(pid):
    """The 15 feasibility criteria (identical to Table S7 / Fig 3)."""
    return [
        val(pid, "external_validation_used") == "y",
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
        any_like(pid, "annotator_count__%", pos=[str(n) for n in range(2, 30)] + [">=3"]),
    ]


def claim_pct(pid):
    r = conn.execute(
        "SELECT SUM(result='yes') y, SUM(result='no') n FROM checklist_results "
        "WHERE checklist_name='CLAIM 2024' AND paper_id=?", (pid,)).fetchone()
    y, n = r[0] or 0, r[1] or 0
    return round(100 * y / (y + n)) if (y + n) else 0


def task(pid):
    doms = paper_domains.get(pid, set())
    for t in PRIORITY:
        if t in doms:
            return ABBR[t]
    return "Other"


def describe(ref):
    p = by_ref[ref]
    return {"ref": ref, "author": p.first_author, "year": p.year or "",
            "type": "Journal" if p.pub_type == "journal" else "Conference",
            "task": task(p.paper_id), "sigma": sum(booleans(p.paper_id)),
            "claim": claim_pct(p.paper_id)}


rows = [describe(ref) for ref in sorted(SAMPLE_REFS)]
gold_rows = [describe(ref) for ref in sorted(GOLD_REFS)]
conn.close()

# ── console summary ──
for label, rs in (("A consistency check", rows), ("B gold standard", gold_rows)):
    n_j = sum(r["type"] == "Journal" for r in rs)
    sig = sorted(r["sigma"] for r in rs)
    print(f"Table S12 {label}: n={len(rs)} of {N}; journal {n_j} / conference {len(rs) - n_j}; "
          f"Sigma median {sig[len(sig) // 2]} range {sig[0]}-{sig[-1]}; "
          f"tasks {sorted(set(r['task'] for r in rs))}")

# ── DOCX ──
C.ensure_dirs()
doc = Document()
title = doc.add_paragraph()
r = title.add_run("Table S12. ")
r.bold = True
r.font.size = Pt(11)
r.font.name = "Arial"
r = title.add_run(f"Studies in the two random 10% validation samples "
                  f"(n = {len(rows)} and {len(gold_rows)} of {N})")
r.font.size = Pt(11)
r.font.name = "Arial"

HEAD = ["Ref", "First author", "Year", "Type", "Task", "Σ (0–15)", "CLAIM %"]
sub = doc.add_paragraph()
r = sub.add_run("A. Internal consistency check")
r.bold = True
r.font.size = Pt(9)
r.font.name = "Arial"
table = doc.add_table(rows=len(rows) + 1, cols=len(HEAD))
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.style = "Table Grid"


def shade(cell, fill):
    tcPr = cell._element.get_or_add_tcPr()
    tcPr.append(tcPr.makeelement(qn("w:shd"), {qn("w:fill"): fill, qn("w:val"): "clear"}))


def put(cell, text, *, bold=False, size=8, align="center", fill=None):
    cell.text = ""
    para = cell.paragraphs[0]
    para.alignment = {"center": 1, "left": 0}[align]
    run = para.add_run(str(text))
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Arial Narrow"
    if fill:
        shade(cell, fill)


for j, h in enumerate(HEAD):
    put(table.rows[0].cells[j], h, bold=True, size=8, fill="F2F2F2")
for i, s in enumerate(rows):
    cells = table.rows[i + 1].cells
    vals = [s["ref"], s["author"], s["year"], s["type"], s["task"], s["sigma"], s["claim"]]
    for j, v in enumerate(vals):
        put(cells[j], v, align="left" if j == 1 else "center")

W = [0.9, 2.6, 0.9, 1.6, 1.0, 1.2, 1.2]
for row in table.rows:
    for j, w in enumerate(W):
        row.cells[j].width = Cm(w)

sub = doc.add_paragraph()
r = sub.add_run("B. Human gold-standard comparison (second sample)")
r.bold = True
r.font.size = Pt(9)
r.font.name = "Arial"
table2 = doc.add_table(rows=len(gold_rows) + 1, cols=len(HEAD))
table2.alignment = WD_TABLE_ALIGNMENT.CENTER
table2.style = "Table Grid"
for j, h in enumerate(HEAD):
    put(table2.rows[0].cells[j], h, bold=True, size=8, fill="F2F2F2")
for i, s_ in enumerate(gold_rows):
    cells = table2.rows[i + 1].cells
    vals = [s_["ref"], s_["author"], s_["year"], s_["type"], s_["task"], s_["sigma"], s_["claim"]]
    for j, v in enumerate(vals):
        put(cells[j], v, align="left" if j == 1 else "center")
for row in table2.rows:
    for j, w in enumerate(W):
        row.cells[j].width = Cm(w)

legend = doc.add_paragraph()
r = legend.add_run(
    f"A: simple random sample of the included studies (seed {SEED}), drawn in the "
    "extraction pipeline and pinned here by manuscript reference number, used for the "
    "internal consistency check (second, blinded LLM rater). B: second random sample used "
    "for the human gold-standard comparison (Table S13). Task (highest-level clinical "
    "output per study) as in Table S7: VeSeg = vessel segmentation, StDet = stenosis "
    "detection, Class = classification, OtDet = other detection, Quant = quantification, "
    "ImPro = image processing. Σ = translational feasibility criteria met (of 15); "
    "CLAIM % = CLAIM 2024 compliance (yes / [yes + no]).")
r.italic = True
r.font.size = Pt(8)
r.font.name = "Arial"

doc.save(OUT_PATH)
print(f"Saved -> {OUT_PATH}")
