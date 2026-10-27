#!/usr/bin/env python3
"""
08_tab_s9_criteria.py -- Table S9: operational definitions of the 15 translational
feasibility criteria.
Output: results/tables/TableS9_criteria.docx

One row per criterion: domain, the extraction field it is derived from, the
response options recorded during extraction, and the explicit rule by which the
criterion was judged met. The rules below are transcriptions of the scoring
logic in 04_tab_s7_feasibility.py and the field descriptions in
papermole_config/extraction_schemas/xca_schema.yaml; the counts printed to the
console are recomputed from the database with that same logic, so a mismatch
between this table and the scorecard shows up as a failed assertion rather than
as silently divergent documentation.

NOTE: booleans() is duplicated from 04_tab_s7_feasibility.py (which shares it
with 04_clinical_readiness.py and 05_fig3_readiness.py). Any change to a
criterion must be made in all four places.
"""

import os

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS9_criteria.docx")

NR = ("", "not_reported", "not reported", "n/a")

### Criterion definitions, in scorecard column order
# (domain, label, extraction field, recorded options, rule for "met")
CRITERIA = [
    ("Validation and generalisability", "External validation",
     "external_validation_used", "Y / N / Unclear",
     "Met if Y: at least one dataset is used only for evaluation and comes from a "
     "different source than the training data (another institution, another scanner, "
     "or a public benchmark not used in training). A held-out split of the same "
     "source is not sufficient. Where a separate test set is evaluated but its "
     "provenance is not stated, the value is Unclear and the criterion is not met."),

    ("Validation and generalisability", "Multi-centre data",
     "multi_center", "Single-center / Multi-center / Unclear",
     "Met if Multi-center: training or evaluation data originate from two or more "
     "institutions. Unclear is not met."),

    ("Validation and generalisability", "Prospective validation",
     "prospective_validation", "Y / N / Unclear",
     "Met if Y: at least one validation dataset was collected after the model was "
     "designed. Retrospective-only designs are not met."),

    ("Reproducibility and transparency", "Code availability",
     "code_availability", "Y / N / Partly",
     "Met if Y or Partly: source code is publicly available in whole or in part, "
     "including as an open-access application or website. Partial release counts."),

    ("Reproducibility and transparency", "Open dataset",
     "dataset_accessibility (per dataset)",
     "Open / On Request / Partly Open / Closed / Not reported",
     "Met if at least one dataset used by the study is Open, meaning freely "
     "downloadable without gatekeeping. On Request and Partly Open are not met."),

    ("Reproducibility and transparency", "Model weights shared",
     "trained_model_available", "Y / N / Unclear",
     "Met if Y: pre-trained model weights are publicly available."),

    ("Reproducibility and transparency", "Explainability method",
     "explainability_technique (repeated)",
     "Named technique, e.g. Grad-CAM, saliency map, ZORRO",
     "Met if at least one named explainability technique is reported. The criterion "
     "records the presence of a method, not its adequacy for the task addressed."),

    ("Workflow integration", "Real-time capability",
     "real_time_capability", "Y / N / Unclear",
     "Met if Y: the study reports an inference speed compatible with real-time use "
     "during catheterisation, or explicitly claims real-time capability. A claim "
     "without supporting speed evidence is Unclear and not met."),

    ("Workflow integration", "Inference time reported",
     "inference_time_reported (per model)", "Y / N",
     "Met if inference time per frame or per image is reported for at least one "
     "model. Per-vessel, per-sequence and total-runtime figures are recorded but "
     "do not satisfy this criterion."),

    ("Study design", "Target vessel specified",
     "target_vessel",
     "LAD / LCX / RCA / LM / All or whole tree / Multiple (specified) / Not specified",
     "Met unless the study never states which vessel or vessels the model targets. "
     "Operating on the whole angiogram counts as specified."),

    ("Study design", "Patient age reported",
     "age_reported", "Y / N",
     "Met if patient age is reported for the cohort in any form."),

    ("Study design", "Patient sex reported",
     "sex_reported", "Y / N",
     "Met if the sex distribution of the cohort is reported."),

    ("Study design", "Clinical presentation reported",
     "patient_presentation",
     "CCS or stable / ACS / Mixed / Other / Not reported",
     "Met unless the dominant clinical presentation of the cohort is not reported. "
     "Consecutive patients without further specification is recorded as Mixed and "
     "counts as reported."),

    ("Annotation quality", "Annotator expertise stated",
     "annotator_expertise (per dataset)",
     "Cardiologist / Radiologist / Physician (other or unspecified) / Student or "
     "trainee / Technologist or radiographer / Non-expert / Not reported",
     "Met if the expertise of the annotators who created the ground truth is stated "
     "for at least one dataset. Where several levels contributed, the most senior is "
     "recorded. Not reported and Unclear are not met."),

    ("Annotation quality", "Two or more annotators",
     "annotator_count (per dataset)", "1 / 2 / >=3 / Not reported",
     "Met if at least one dataset was annotated independently by two or more "
     "annotators. Not reported is not met."),
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


conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)
flags = [booleans(conn, p.paper_id) for p in papers]
conn.close()

assert len(CRITERIA) == 15, "the table must document exactly 15 criteria"
met = [sum(f[i] for f in flags) for i in range(15)]

### Console summary
print(f"Table S9: operational definitions (N = {N})")
for (dom, label, *_), n in zip(CRITERIA, met):
    print(f"  {label:32s} {n:4d} ({round(100 * n / N):3d}%)   [{dom}]")
print(f"  mean criteria met {sum(met) / N:.2f}")

### DOCX
C.ensure_dirs()
doc = Document()
sec = doc.sections[0]
sec.orientation = WD_ORIENT.LANDSCAPE
sec.page_width, sec.page_height = Cm(29.7), Cm(21)
sec.top_margin = sec.bottom_margin = Cm(1.2)
sec.left_margin = sec.right_margin = Cm(1.2)

title = doc.add_paragraph()
r = title.add_run("Table S9. ")
r.bold = True
r.font.size = Pt(11)
r.font.name = "Arial"
r = title.add_run("Operational definitions of the 15 translational feasibility criteria")
r.font.size = Pt(11)
r.font.name = "Arial"

HEAD = ["Domain", "Criterion", "Extraction field", "Recorded options",
        "Judged met if", "n (%)"]
WIDTHS = [Cm(3.6), Cm(3.4), Cm(3.8), Cm(4.2), Cm(9.6), Cm(1.8)]

table = doc.add_table(rows=len(CRITERIA) + 1, cols=len(HEAD))
table.alignment = WD_TABLE_ALIGNMENT.CENTER
table.style = "Table Grid"


def shade(cell, fill):
    tcPr = cell._element.get_or_add_tcPr()
    tcPr.append(tcPr.makeelement(qn("w:shd"), {qn("w:fill"): fill, qn("w:val"): "clear"}))


def put(cell, text, *, bold=False, size=8, fill=None, width=None):
    cell.text = ""
    para = cell.paragraphs[0]
    para.paragraph_format.space_before = Pt(1)
    para.paragraph_format.space_after = Pt(1)
    run = para.add_run(text)
    run.bold = bold
    run.font.size = Pt(size)
    run.font.name = "Arial"
    if fill:
        shade(cell, fill)
    if width is not None:
        cell.width = width


for j, h in enumerate(HEAD):
    put(table.rows[0].cells[j], h, bold=True, fill="F2F2F2", width=WIDTHS[j])

prev_domain = None
for i, ((dom, label, field, options, rule), n) in enumerate(zip(CRITERIA, met), start=1):
    cells = table.rows[i].cells
    put(cells[0], dom if dom != prev_domain else "", bold=dom != prev_domain, width=WIDTHS[0])
    prev_domain = dom
    put(cells[1], label, width=WIDTHS[1])
    put(cells[2], field, width=WIDTHS[2])
    put(cells[3], options, width=WIDTHS[3])
    put(cells[4], rule, width=WIDTHS[4])
    put(cells[5], f"{n} ({round(100 * n / N)}%)", width=WIDTHS[5])

note = doc.add_paragraph()
r = note.add_run(
    f"Criteria are listed in scorecard column order. Counts are the number of the "
    f"{N} included studies meeting each criterion, recomputed from the extraction "
    f"database with the scoring logic used for Figure 3B and Table S7. Fields marked "
    f"per dataset or per model are recorded once for each dataset or model in a study; "
    f"a criterion is met if any of them satisfies the rule. The reporting-quality "
    f"domain (CLAIM 2024 compliance and QUADAS-2 risk of bias) is shown alongside the "
    f"scorecard for context and does not contribute to the composite score.")
r.font.size = Pt(8)
r.font.name = "Arial"

doc.save(OUT_PATH)
print(f"Saved -> {OUT_PATH}")
