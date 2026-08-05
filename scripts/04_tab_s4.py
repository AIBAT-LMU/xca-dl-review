#!/usr/bin/env python3
"""
04_tab_s4.py -- Table S4: Publicly available XCA datasets
Output: results/tables/TableS4_datasets.docx

The dataset list and its metadata (size, annotation type, URL) are curated;
they cannot be recovered from the database. The Reference column, however, is
computed from the database at run time -- each dataset is matched to the studies
that use it (dataset_source_type='Public' or dataset_accessibility Open) so the
citations track the current ref_number assignment.

Public dataset names are canonicalised in the database during preparation
(using these same alias patterns). The patterns below still accept the raw
aliases, so the table is correct regardless, and compound names ("DCA1 and CADICA", left un-normalised) still match
each benchmark they mention.

Restricted to X-ray coronary angiography benchmarks: general-vision or
non-coronary sets a few studies borrow for pretraining (ImageNet, COCO, DRIVE,
STARE, BSDS500) are deliberately excluded.
"""

import os
import re
from collections import defaultdict

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS4_datasets.docx")

# (name, n samples, annotation, URL, match pattern for dataset_name)
DATASETS = [
    ("ARCADE", "1,500", "Segmentation, bounding boxes",
     "zenodo.org/record/10390295", r"arcade"),
    ("CADICA", "668", "Bounding boxes",
     "data.mendeley.com/datasets/p9bpx9ctcv", r"cadica"),
    ("DCA1", "134", "Segmentation",
     "personal.cimat.mx:8181/~ivan.cruz/DB_Angiograms.html",
     r"dca[-\s]?1|cruz-?aceves|mexican social security"),
    ("AD3D (Danilov et al.)", "8,325", "Bounding boxes",
     "data.mendeley.com/datasets/ydrm75xywg/3",
     r"danilov|ad3d|angiographic dataset for stenosis"),
    ("DSDD (Antczak & Liberadzki)", "125", "Image-level (patches)",
     "github.com/KarolAntczak/DeepStenosisDetection",
     r"antczak|deep stenosis detection|\bdsdd\b"),
    ("XCAD", "1,747", "Segmentation",
     "github.com/AISIGSJTU/SSVS", r"xcad|x-?cad\b"),
    ("XCA-Renji (SVS-net)", "332", "Segmentation",
     "github.com/Binjie-Qin/SVS-net (data offline)", r"renji|svs-?net|\bhao et al"),
    ("CHUAC", "30", "Segmentation",
     "figshare.com/s/4d24cf3d14bc901a94bf", r"chuac"),
    ("DRVR *", "19,384", "Segmentation",
     "github.com/BaochangZhang/X3im2Real (no longer public)", r"\bdrvr\b"),
    ("AngioCAD (Hosseini et al.)", "413 †", "Vessel/stenosis + clinical data",
     "zenodo.org/records/15826856", r"angiocad"),
    ("DeNVeR / XACV (Wu et al.)", "111", "Segmentation (video)",
     "github.com/kirito878/denver", r"\bxacv\b|denver"),
    ("MOSXAV", "62 ‡", "Multi-object seg. (video)",
     "github.com/xilin-x/MOSXAV", r"mosxav"),
    ("CoronaryDominance (Kruzhilov et al.)", "1,574 †", "Dominance classification",
     "huggingface.co/datasets/BearSubj13/CoronaryDominance", r"coronarydominance"),
    ("CardioSYNTAX (Kruzhilov et al.)", "3,018 †", "SYNTAX score, dominance",
     "github.com/palevas/syntax-score-prediction", r"cardiosyntax"),
]


conn = C.connect()
papers = C.load_papers(conn)
ref_of = {p.paper_id: p.ref for p in papers}

inst = defaultdict(lambda: defaultdict(dict))
for pid, fname, val in conn.execute(
        "SELECT paper_id, field_name, value FROM extractions "
        "WHERE field_name LIKE 'dataset_%__%' AND value IS NOT NULL AND value!=''"):
    m = re.match(r"(dataset_\w+)__(\d+)$", fname)
    if m:
        inst[pid][int(m.group(2))][m.group(1)] = val.strip()

usage = {name: set() for name, *_ in DATASETS}
for pid, idxs in inst.items():
    for f in idxs.values():
        name = f.get("dataset_name", "")
        public = (f.get("dataset_source_type") == "Public"
                  or f.get("dataset_accessibility") in ("Open", "Partly Open"))
        if not name or not public:
            continue
        for dname, _n, _a, _u, pat in DATASETS:
            if re.search(pat, name, re.I):
                usage[dname].add(ref_of[pid])
conn.close()


print("Table S4: Publicly available XCA datasets")
table_rows = []
for name, n, ann, url, _pat in DATASETS:
    refs = C.ref_ranges(sorted(usage[name]))
    table_rows.append((name, n, ann, url, refs))
    print(f"  {name:26s} {len(usage[name]):2d} studies  [{refs}]")


C.ensure_dirs()
doc = Document()
section = doc.sections[0]
section.page_width, section.page_height = Cm(21), Cm(29.7)
section.top_margin = section.bottom_margin = Cm(2)
section.left_margin = section.right_margin = Cm(1.5)

p = doc.add_paragraph()
run = p.add_run("Table S4. ")
run.bold = True
run.font.size = Pt(11)
run.font.name = "Arial"
run = p.add_run("Publicly available datasets for coronary angiography")
run.font.size = Pt(11)
run.font.name = "Arial"

table = doc.add_table(rows=len(table_rows) + 1, cols=5)
table.alignment = WD_TABLE_ALIGNMENT.LEFT
table.style = "Table Grid"
for i, text in enumerate(["Dataset", "n", "Annotation", "URL", "References"]):
    cell = table.rows[0].cells[i]
    cell.text = ""
    r = cell.paragraphs[0].add_run(text)
    r.bold = True
    r.font.size = Pt(9)
    r.font.name = "Arial"
    tcPr = cell._element.get_or_add_tcPr()
    tcPr.append(tcPr.makeelement(qn("w:shd"),
                                 {qn("w:fill"): "E8E8E8", qn("w:val"): "clear"}))

for i, (name, n, ann, url, refs) in enumerate(table_rows):
    for j, text in enumerate((name, n, ann, url, refs)):
        cell = table.rows[i + 1].cells[j]
        cell.text = ""
        r = cell.paragraphs[0].add_run(text)
        r.font.size = Pt(8) if j in (3, 4) else Pt(9)
        r.font.name = "Arial"

for row in table.rows:
    row.cells[0].width = Cm(3)
    row.cells[1].width = Cm(1.3)
    row.cells[2].width = Cm(3.2)
    row.cells[3].width = Cm(6)
    row.cells[4].width = Cm(4.5)

p = doc.add_paragraph()
run = p.add_run("n = number of images or frames unless noted. * Synthetic dataset "
                "generated from CT angiography. † patients. ‡ videos. "
                "References list included studies that use each dataset; reference "
                "numbers correspond to the supplementary reference list L1.")
run.italic = True
run.font.size = Pt(8)
run.font.name = "Arial"

doc.save(OUT_PATH)
print(f"\nSaved → {OUT_PATH}")
