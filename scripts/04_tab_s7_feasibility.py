#!/usr/bin/env python3
"""
04_tab_s7_feasibility.py -- Table S7: per-study translational feasibility scorecard.
Output: results/tables/TableS7_feasibility.docx

One row per study: the 15 binary feasibility criteria (six domains), plus CLAIM
2024 compliance and the number of QUADAS-2 domains rated low risk, for reference.
Sorted by Sigma (criteria met, 0-15) descending, then CLAIM% descending.

Supersedes the old generate_feasibility_json.py + generate_tableS5.js pair
(different DB, pre-reextraction field names, and a Node/docx dependency that is
not installed). The 15 booleans use the SAME logic as 04_clinical_readiness.py
and 05_fig3_readiness.py, so Sigma here matches the figure and the text exactly.
CLAIM% is yes/(yes+no) -- the same denominator as the reported median (70%).
QUADAS-2 risk-of-bias domains are DERIVED from the signalling questions
(all 'yes' -> low; any 'no' -> high; else unclear); applicability ratings are
stored directly. Item 37 of CLAIM was corrected during database preparation.
"""

import os
from collections import defaultdict

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.section import WD_ORIENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS7_feasibility.docx")

NR = ("", "not_reported", "not reported", "n/a")
CHECK, CROSS = "✓", "–"

# Task priority: the highest-level clinical output shown for multi-domain work,
# and the abbreviation used in the table (matches the six-domain vocabulary).
PRIORITY = ["Quantification", "Stenosis detection", "Classification",
            "Other detection", "Vessel segmentation", "Image processing"]
ABBR = {"Vessel segmentation": "VeSeg", "Stenosis detection": "StDet",
        "Classification": "Class", "Other detection": "OtDet",
        "Image processing": "ImPro", "Quantification": "Quant"}

conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)

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
    """The 15 feasibility criteria, in column order (identical to Fig 3 / readiness)."""
    return [
        val(pid, "external_validation_used") == "y",                      # Ext
        val(pid, "multi_center") == "multi-center",                       # MC
        val(pid, "prospective_validation") == "y",                        # Pro
        val(pid, "code_availability") in ("y", "partly"),                 # Cod
        any_like(pid, "dataset_accessibility__%", pos=["open"]),          # Dat
        val(pid, "trained_model_available") == "y",                       # Wt
        any_like(pid, "explainability_technique__%"),                     # XAI (named technique)
        val(pid, "real_time_capability") == "y",                          # RT
        any_like(pid, "inference_time_reported__%", pos=["y"]),           # Inf
        val(pid, "target_vessel") not in NR,                              # Vs
        val(pid, "age_reported") == "y",                                  # Ag
        val(pid, "sex_reported") == "y",                                  # Sx
        val(pid, "patient_presentation") not in NR,                       # Pr
        any_like(pid, "annotator_expertise__%", exc=list(NR) + ["unclear"]),  # Ex
        any_like(pid, "annotator_count__%", pos=[str(n) for n in range(2, 30)]),  # >=2
    ]


def claim_pct(pid):
    r = conn.execute(
        "SELECT SUM(result='yes') y, SUM(result='no') n FROM checklist_results "
        "WHERE checklist_name='CLAIM 2024' AND paper_id=?", (pid,)).fetchone()
    y, n = r[0] or 0, r[1] or 0
    return round(100 * y / (y + n)) if (y + n) else 0


# ── QUADAS-2 low-risk domain count (of 7), derived ──
sig = defaultdict(dict)
for r in conn.execute("SELECT paper_id, item_id, result FROM checklist_results "
                      "WHERE checklist_name='QUADAS-2'"):
    sig[r["paper_id"]][r["item_id"]] = (r["result"] or "").strip().lower()
ROB = {"ps": ["1.1", "1.2", "1.3"], "it": ["2.1", "2.2"],
       "rs": ["3.1", "3.2"], "ft": ["4.1", "4.2", "4.3", "4.4"]}
APP = {"ps": "1.app", "it": "2.app", "rs": "3.app"}


def derive(vals):
    if any(v == "no" for v in vals):
        return "high"
    if all(v == "yes" for v in vals):
        return "low"
    return "unclear"


def quadas_low(pid):
    d = sig.get(pid, {})
    low = sum(derive([d.get(q, "unclear") for q in qs]) == "low" for qs in ROB.values())
    low += sum(d.get(it, "unclear") == "low" for it in APP.values())
    return low


def task(pid):
    doms = paper_domains.get(pid, set())
    for t in PRIORITY:
        if t in doms:
            return ABBR[t]
    return "Other"


# ── build & sort rows ──
studies = []
for p in papers:
    b = booleans(p.paper_id)
    studies.append({
        "ref": p.ref, "author": p.first_author, "year": p.year or "",
        "task": task(p.paper_id), "bools": b, "sigma": sum(b),
        "claim": claim_pct(p.paper_id), "quadas": quadas_low(p.paper_id),
    })
conn.close()
studies.sort(key=lambda s: (-s["sigma"], -s["claim"], s["ref"]))

# ── console summary ──
sv = [s["sigma"] for s in studies]
print(f"Table S7: feasibility scorecard (N={N})")
print(f"  Sigma range {min(sv)}-{max(sv)}  mean {sum(sv)/N:.1f}  "
      f">=6: {sum(v >= 6 for v in sv)}  >=10: {sum(v >= 10 for v in sv)}")

# ── DOCX ──
C.ensure_dirs()
doc = Document()
sec = doc.sections[0]
sec.orientation = WD_ORIENT.LANDSCAPE
sec.page_width, sec.page_height = Cm(29.7), Cm(21)
sec.top_margin = sec.bottom_margin = Cm(1.2)
sec.left_margin = sec.right_margin = Cm(1.0)

title = doc.add_paragraph()
r = title.add_run("Table S7. ")
r.bold = True
r.font.size = Pt(11)
r.font.name = "Arial"
r = title.add_run("Per-study translational feasibility scorecard "
                  f"(N = {N}, sorted by composite score)")
r.font.size = Pt(11)
r.font.name = "Arial"

# Column groups: (label, shade, [sub-headers])
GROUPS = [
    ("Study", "F2F2F2", ["Ref", "Author", "Yr", "Task"]),
    ("Validation", "DEEAF6", ["Ext", "MC", "Pro"]),
    ("Reproducibility", "E2EFDA", ["Cod", "Dat", "Wt", "XAI"]),
    ("Workflow", "E4DFEC", ["RT", "Inf"]),
    ("Study design", "FFF2CC", ["Vs", "Ag", "Sx", "Pr"]),
    ("Annotation", "FCE4D6", ["Ex", "≥2"]),
    ("Reporting", "D5F5E3", ["CL%", "Q2"]),
    ("Σ", "E0E0E0", ["n"]),
]
col_shades, sub_headers = [], []
for _, shade, subs in GROUPS:
    for s in subs:
        col_shades.append(shade)
        sub_headers.append(s)
ncols = len(sub_headers)   # 22

table = doc.add_table(rows=len(studies) + 2, cols=ncols)
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


# Row 0: domain group header (merged spans)
grp_cells = table.rows[0].cells
ci = 0
for label, shade_hex, subs in GROUPS:
    span = grp_cells[ci]
    if len(subs) > 1:
        span = span.merge(grp_cells[ci + len(subs) - 1])
    put(span, label, bold=True, size=8, fill=shade_hex)
    ci += len(subs)

# Row 1: sub-headers
for j, (txt, sh) in enumerate(zip(sub_headers, col_shades)):
    put(table.rows[1].cells[j], txt, bold=True, size=7, fill=sh)

# Data rows
for i, s in enumerate(studies):
    cells = table.rows[i + 2].cells
    vals = ([s["ref"], s["author"], s["year"], s["task"]]
            + [CHECK if b else CROSS for b in s["bools"]]
            + [s["claim"], s["quadas"], s["sigma"]])
    for j, v in enumerate(vals):
        align = "left" if j == 1 else "center"
        bold = j == ncols - 1                       # Sigma column
        fill = "F5F5F5" if j == ncols - 1 else None
        put(cells[j], v, bold=bold, size=8, align=align, fill=fill)

# Column widths
W = {0: 0.9, 1: 1.6, 2: 0.8, 3: 1.0}   # cm; study block
for row in table.rows:
    for j in range(ncols):
        row.cells[j].width = Cm(W.get(j, 0.85))

legend = doc.add_paragraph()
r = legend.add_run(
    "Task (highest-level clinical output per study): VeSeg = vessel segmentation, "
    "StDet = stenosis detection, Class = classification, OtDet = other detection, "
    "Quant = quantification, ImPro = image processing. "
    "Ext = external validation; MC = multi-centre; Pro = prospective validation; "
    "Cod = code available; Dat = open dataset; Wt = model weights shared; "
    "XAI = explainability method applied; RT = real-time demonstrated; "
    "Inf = inference time reported; Vs = target vessel specified; Ag = age reported; "
    "Sx = sex reported; Pr = patient presentation reported; Ex = annotator expertise "
    "described; ≥2 = two or more annotators. CL% = CLAIM 2024 compliance "
    "(yes / [yes + no]); Q2 = QUADAS-2 domains rated low risk (of 7, risk-of-bias "
    "domains derived from signalling questions). Σ = binary criteria met "
    "(of 15; CL% and Q2 are shown for reference and are not included in Σ). "
    "Sorted by Σ descending, then CL% descending.")
r.italic = True
r.font.size = Pt(8)
r.font.name = "Arial"

doc.save(OUT_PATH)
print(f"Saved -> {OUT_PATH}")
