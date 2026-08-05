#!/usr/bin/env python3
"""
04_tab_s5_agg.py -- Table S5: Clinical feasibility and reproducibility (aggregate)
Output: results/tables/TableS5_feasibility.docx

Paper-level flags (external_validation_used, prospective_validation,
real_time_capability, code_availability, trained_model_available) plus per-model
flags collapsed to the study (inference_time_reported, hardware). Per-frame
inference-time magnitudes are NOT aggregated here: inference_time_value mixes
units (s vs ms) and denominators (per-frame / per-vessel / per-volume / total)
and needs a curation pass before it can be pooled.
"""

import os
import re

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS5_feasibility.docx")
NR = {"", "not_reported", "not reported", "n/a", "none", "unclear"}

conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)
ref_of = {p.paper_id: p.ref for p in papers}


def paper_flag(field, positive):
    return {pid for pid, v in conn.execute(
        "SELECT paper_id, value FROM extractions WHERE field_name=?", (field,))
        if (v or "").strip() in positive}


def any_model(base, positive=None):
    """Studies where any model_instance row matches (or, if positive is None, is reported)."""
    out = set()
    for pid, v in conn.execute(
            "SELECT paper_id, value FROM extractions WHERE field_name LIKE ?",
            (base + "__%",)):
        v = (v or "").strip()
        if positive is None:
            if v.lower() not in NR:
                out.add(pid)
        elif v in positive:
            out.add(pid)
    return out


ext = paper_flag("external_validation_used", {"Y"})
prosp = paper_flag("prospective_validation", {"Y", "Yes"})
inf = any_model("inference_time_reported", {"Y"})
hw = any_model("hardware")
code = paper_flag("code_availability", {"Y", "Partly"})
weights = paper_flag("trained_model_available", {"Y", "Yes"})

# Curated per-frame inference time: one clean ms number per study, or
# 'Excluded' for non-per-frame figures (prepared during database curation).
RT_MS = 67   # real-time = displayable at 15 fps
pf = {}      # paper_id -> per-frame ms
for pid, v in conn.execute(
        "SELECT paper_id, value FROM extractions WHERE field_name='inference_per_frame_ms'"):
    try:
        pf[pid] = float(v)
    except (TypeError, ValueError):
        pass  # 'Excluded'
realtime = {pid for pid, v in pf.items() if v <= RT_MS}
conn.close()

# (label, members, denominator). Hardware and real-time are scoped to the
# relevant subset so the table matches the text (of studies reporting inference
# time, and of studies reporting per-frame time, respectively).
rows = [
    ("Validation", None, N),
    ("External validation on independent cohort", ext, N),
    ("Prospective / in-workflow validation", prosp, N),
    ("Computational reporting", None, N),
    ("Inference time reported", inf, N),
    ("Hardware specified ᵇ", hw & inf, len(inf)),
    ("Per-frame inference time reported ᵃ", set(pf), N),
    ("Real-time capable (≤67 ms/frame, 15 fps) ᵇ", realtime, len(pf)),
    ("Reproducibility", None, N),
    ("Code publicly available", code, N),
    ("Pretrained weights shared", weights, N),
]

print(f"Table S5: Clinical feasibility and reproducibility (N={N})")
out_rows = []
for label, members, denom in rows:
    if members is None:
        out_rows.append((label, "", "", "", True))
        print(f"\n{label}")
    else:
        refs = sorted(ref_of[p] for p in members)
        out_rows.append((label, len(members), C.pct(len(members), denom),
                         C.ref_ranges(refs), False))
        print(f"  {label}: {len(members)} ({C.pct(len(members), denom)}%)")


C.ensure_dirs()
doc = Document()
section = doc.sections[0]
section.page_width, section.page_height = Cm(21), Cm(29.7)
section.top_margin = section.bottom_margin = Cm(2)
section.left_margin = section.right_margin = Cm(1.5)

p = doc.add_paragraph()
run = p.add_run("Table S5. ")
run.bold = True
run.font.size = Pt(11)
run.font.name = "Arial"
run = p.add_run("Clinical feasibility and reproducibility")
run.font.size = Pt(11)
run.font.name = "Arial"

table = doc.add_table(rows=len(out_rows) + 1, cols=4)
table.alignment = WD_TABLE_ALIGNMENT.LEFT
table.style = "Table Grid"
for i, text in enumerate(["Characteristic", "n", "%", "References"]):
    cell = table.rows[0].cells[i]
    cell.text = ""
    r = cell.paragraphs[0].add_run(text)
    r.bold = True
    r.font.size = Pt(9)
    r.font.name = "Arial"
    tcPr = cell._element.get_or_add_tcPr()
    tcPr.append(tcPr.makeelement(qn("w:shd"),
                                 {qn("w:fill"): "E8E8E8", qn("w:val"): "clear"}))

for i, (label, n, pct, refs, hdr) in enumerate(out_rows):
    cell = table.rows[i + 1].cells[0]
    cell.text = ""
    r = cell.paragraphs[0].add_run(("" if hdr else "   ") + label)
    r.bold = hdr
    r.font.size = Pt(9)
    r.font.name = "Arial"
    for j, text in enumerate((str(n) if n != "" else "",
                              str(pct) if pct != "" else "", refs)):
        cell = table.rows[i + 1].cells[j + 1]
        cell.text = ""
        r = cell.paragraphs[0].add_run(text)
        r.font.size = Pt(8) if j == 2 else Pt(9)
        r.font.name = "Arial"

for row in table.rows:
    row.cells[0].width = Cm(5.5)
    row.cells[1].width = Cm(1)
    row.cells[2].width = Cm(1)
    row.cells[3].width = Cm(10.5)

import statistics
_pf = sorted(pf.values())
_med = statistics.median(_pf)
_q1, _q3 = statistics.quantiles(_pf, n=4)[0], statistics.quantiles(_pf, n=4)[2]
p = doc.add_paragraph()
run = p.add_run(
    "External validation: evaluation on a cohort from a source different from "
    f"the training data. ᵃ Per-frame inference time (milliseconds per single "
    "frame; per-vessel, per-video and total-runtime figures excluded): median "
    f"{_med:.0f} ms (IQR {_q1:.0f}–{_q3:.0f}; range {min(_pf):.0f} ms to "
    f"{max(_pf)/1000:.0f} s). ᵇ Percentage of studies reporting inference time "
    "(hardware; n=64) or per-frame time (real-time; n=44); other percentages "
    "are of all included studies.")
run.italic = True
run.font.size = Pt(8)
run.font.name = "Arial"

doc.save(OUT_PATH)
print(f"\nSaved → {OUT_PATH}")
