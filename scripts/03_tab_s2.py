#!/usr/bin/env python3
"""
03_tab_s2.py
Table S2 - Model architectures and domain-specific adaptations

Systematic Review: "Toward clinical-grade deep learning in coronary angiography"

Input:  xca_dl_review.db
Output: results/tables/TableS2_architectures.docx

Architectures are reported at the level recorded by the extraction
(base_architecture). An earlier version of this table classified models into
hand-curated families (U-Net variant, object detector, backbone); that is not
reproducible from the published database, because proposed networks are named
freely and the family cannot be recovered from the name. Where a named family
is still informative, it is reported explicitly as a name match and labelled
as such.

Counts are per study: a study is counted once under an architecture if any of
its primary models uses it, so column totals exceed the domain size.
"""

import json
import os
from collections import defaultdict

from docx import Document
from docx.shared import Pt, Cm
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml.ns import qn

import common as C

OUT_PATH = os.path.join(C.OUT_TABLES, "TableS2_architectures.docx")

# Architectures in reporting order; anything else falls under "Other".
ARCH_ORDER = ["CNN", "Hybrid CNN+Transformer", "Transformer", "GAN",
              "GNN/GCN", "RNN", "Hybrid CNN+RNN", "MLP", "Diffusion", "Other"]
ARCH_MISSING = {"NA", "Not reported", ""}

# Secondary architecture family (extractions.architecture_family, adjudicated
# per model during database preparation). Reporting order; anything else falls under "Other".
# "NA" (no family stated) is not reported. Unlike the old model-name regex this
# is adjudicated per model against the full text, so it no longer understates
# families published under a custom name.
FAMILY_ORDER = ["U-Net", "Object detector", "ResNet/backbone", "ViT/SegFormer",
                "Swin Transformer", "GAN-family", "FCN", "DeepLab", "PSPNet",
                "HRNet", "Hourglass", "SegNet", "RNN/LSTM", "MLP", "Diffusion",
                "Other"]
FAMILY_MISSING = {"NA", ""}

STANDARD_LOSSES = ["Cross-entropy", "Dice", "Binary cross-entropy", "Focal",
                   "L1", "MSE/L2", "IoU/Jaccard", "Tversky"]
VESSEL_LOSSES = ["Centerline/topological", "Boundary-aware"]
TRAINING_LOSSES = ["Consistency", "Contrastive", "Adversarial", "Distillation",
                   "Perceptual"]


### Data
conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)
ref_of = {p.paper_id: p.ref for p in papers}
primary = C.primary_models(conn, papers)
by_domain, _ = C.application_domains(conn, papers)


def field(pid, name, idx):
    r = conn.execute(
        "SELECT value FROM extractions WHERE paper_id=? AND field_name=?",
        (pid, f"{name}__{idx}")).fetchone()
    return (r["value"] or "").strip() if r else ""


def repeated_paper_field(base):
    """{value: set(paper_id)} for a repeated paper-level field."""
    out = defaultdict(set)
    for pid, value in conn.execute(
            "SELECT paper_id, value FROM extractions "
            "WHERE field_name LIKE ? ESCAPE '\\' "
            "AND value IS NOT NULL AND value != ''", (base + "\\_\\_%",)):
        out[value.strip()].add(pid)
    return out


# Architecture x domain is joined PER MODEL: a study counts under (domain,
# architecture) only if the SAME model has both. Intersecting arch_papers[arch]
# with by_domain[domain] (two study-level sets) would instead count studies that
# have the architecture on one model and the domain on another -- a spurious
# cross-product (see common.primary_model_rows). arch_dom/fam_dom therefore key
# off each model's own field_of_application__N, base_architecture__N and
# architecture_family__N.
arch_dom = defaultdict(lambda: defaultdict(set))   # domain -> arch   -> {paper_id}
fam_dom = defaultdict(lambda: defaultdict(set))    # domain -> family -> {paper_id}
fam_all = defaultdict(set)                          # family -> {paper_id}, all studies
for m in C.primary_model_rows(conn, papers):
    if m.architecture_family and m.architecture_family not in FAMILY_MISSING:
        fam = m.architecture_family if m.architecture_family in FAMILY_ORDER else "Other"
        fam_all[fam].add(m.paper_id)
    if m.domain is None:
        continue
    if m.base_architecture and m.base_architecture not in ARCH_MISSING:
        arch_dom[m.domain][m.base_architecture if m.base_architecture in ARCH_ORDER
                           else "Other"].add(m.paper_id)
    if m.architecture_family and m.architecture_family not in FAMILY_MISSING:
        fam_dom[m.domain][m.architecture_family if m.architecture_family in FAMILY_ORDER
                          else "Other"].add(m.paper_id)

temporal, pretrain, any_pretrain = set(), defaultdict(set), set()
for p in papers:
    for i in primary.get(p.paper_id, []):
        if field(p.paper_id, "input_type", i) in ("Video sequence", "Multi-frame"):
            temporal.add(p.paper_id)
        if field(p.paper_id, "uses_pretrained_weights", i) == "Y":
            any_pretrain.add(p.paper_id)
        src = field(p.paper_id, "pretrained_source", i)
        if src in ("ImageNet", "COCO", "Domain-specific/medical"):
            pretrain[src].add(p.paper_id)

losses = repeated_paper_field("loss_component")
xai = repeated_paper_field("explainability_technique")
if not losses:
    raise SystemExit("no loss_component rows in the published database")

# Label-efficient training paradigms, detected from the study's own title and
# method text (proposal-cued, references stripped) since there is no dedicated
# field for supervision type.
PARADIGMS = [("Self-supervised", r"self-?supervis"),
             ("Semi-supervised", r"semi-?supervis"),
             ("Weakly-supervised", r"weakly.?supervis"),
             ("Unsupervised", r"\bunsupervis")]
paradigm = defaultdict(set)
# Supervision type has no dedicated DB field; it is detected from each study's own
# title/method text. The published database ships without full text (copyright), so
# these labels are read from paradigm_labels.json (keyed by reference number),
# precomputed once from the full-text database.
_pid_of = {p.ref: p.paper_id for p in papers}
_labels = json.load(open(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "paradigm_labels.json")))
for name, _ in PARADIGMS:
    for r in _labels.get(name, []):
        if r in _pid_of:
            paradigm[name].add(_pid_of[r])
label_efficient = set().union(*paradigm.values()) if paradigm else set()

conn.close()


### Rows: (label, n, pct, references, indent, is_header)
rows = []


def add(label, members, total, indent, header=False):
    refs = sorted(ref_of[p] for p in members)
    rows.append((label, len(members), C.pct(len(members), total),
                 C.ref_ranges(refs), indent, header))


rows.append(("Architecture by application domain", "", "", "", 0, True))
for domain in C.DOMAIN_ORDER:
    members = by_domain.get(domain, set())
    rows.append((f"{domain} (n={len(members)})", "", "", "", 1, True))
    for arch in ARCH_ORDER:
        cell = arch_dom[domain].get(arch, set())
        if cell:
            add(arch, cell, len(members), 2)
    fams = fam_dom[domain]
    if fams:
        rows.append(("of which by family", "", "", "", 2, True))
        for fam in FAMILY_ORDER:
            cell = fams.get(fam, set())
            if cell:
                add(fam, cell, len(members), 3)

rows.append((f"Domain-specific adaptations (N={N})", "", "", "", 0, True))

rows.append(("Input scope", "", "", "", 1, True))
add("Video or multi-frame input", temporal, N, 2)

rows.append(("Label-efficient training", "", "", "", 1, True))
add("Any self/semi/weakly/unsupervised", label_efficient, N, 2)
for name, _ in PARADIGMS:
    if paradigm.get(name):
        add(name, paradigm[name], N, 3)

rows.append(("Loss functions", "", "", "", 1, True))
std = set().union(*[losses[k] for k in STANDARD_LOSSES if k in losses])
add("Standard objectives", std, N, 2)
for k in STANDARD_LOSSES:
    if k in losses:
        add(k, losses[k], N, 3)
vessel = set().union(*[losses[k] for k in VESSEL_LOSSES if k in losses])
add("Vessel-geometry objectives", vessel, N, 2)
for k in VESSEL_LOSSES:
    if k in losses:
        add(k, losses[k], N, 3)
train = set().union(*[losses[k] for k in TRAINING_LOSSES if k in losses])
if train:
    add("Training-strategy objectives", train, N, 2)
    for k in TRAINING_LOSSES:
        if k in losses:
            add(k, losses[k], N, 3)

rows.append(("Transfer learning", "", "", "", 1, True))
# "Any pretraining" follows uses_pretrained_weights; the named sources below
# do not sum to it, because pretrained_source is "Other" or "Unclear" for the
# remainder.
add("Any pretraining", any_pretrain, N, 2)
for k in ("ImageNet", "COCO", "Domain-specific/medical"):
    if pretrain.get(k):
        add(k, pretrain[k], N, 3)
add("Source other or unspecified",
    any_pretrain - set().union(*pretrain.values()) if pretrain else any_pretrain, N, 3)

rows.append(("Explainability", "", "", "", 1, True))
all_xai = set().union(*xai.values()) if xai else set()
add("Any method", all_xai, N, 2)
for k, members in sorted(xai.items(), key=lambda kv: -len(kv[1])):
    add(k, members, N, 3)


### Console summary
print(f"Table S2: Model architectures (N = {N})")
for label, n, pct, _, indent, header in rows:
    prefix = "  " * indent
    print(f"\n{prefix}{label}" if header else f"{prefix}{label}: {n} ({pct}%)")


### DOCX
C.ensure_dirs()
doc = Document()
section = doc.sections[0]
section.page_width, section.page_height = Cm(21), Cm(29.7)
section.top_margin = section.bottom_margin = Cm(2)
section.left_margin = section.right_margin = Cm(1.5)

p = doc.add_paragraph()
run = p.add_run("Table S2. ")
run.bold = True
run.font.size = Pt(11)
run.font.name = "Arial"
run = p.add_run("Model architectures and domain-specific adaptations")
run.font.size = Pt(11)
run.font.name = "Arial"

table = doc.add_table(rows=len(rows) + 1, cols=4)
table.alignment = WD_TABLE_ALIGNMENT.LEFT
table.style = "Table Grid"

for i, text in enumerate(["Category", "n", "%", "References"]):
    cell = table.rows[0].cells[i]
    cell.text = ""
    run = cell.paragraphs[0].add_run(text)
    run.bold = True
    run.font.size = Pt(9)
    run.font.name = "Arial"
    tcPr = cell._element.get_or_add_tcPr()
    tcPr.append(tcPr.makeelement(
        qn("w:shd"), {qn("w:fill"): "E8E8E8", qn("w:val"): "clear"}))

for i, (label, n, pct, refs, indent, header) in enumerate(rows):
    row = table.rows[i + 1]
    cell = row.cells[0]
    cell.text = ""
    run = cell.paragraphs[0].add_run("\u00A0\u00A0\u00A0" * indent + label)
    run.bold = header
    run.italic = indent == 3
    run.font.size = Pt(9)
    run.font.name = "Arial"
    for j, (text, size) in enumerate((("" if n == "" else str(n), 9),
                                      ("" if pct == "" else str(pct), 9),
                                      (refs, 8))):
        cell = row.cells[j + 1]
        cell.text = ""
        run = cell.paragraphs[0].add_run(text)
        run.font.size = Pt(size)
        run.font.name = "Arial"

for row in table.rows:
    row.cells[0].width = Cm(5.5)
    row.cells[1].width = Cm(1)
    row.cells[2].width = Cm(1)
    row.cells[3].width = Cm(10.5)

p = doc.add_paragraph()
run = p.add_run(
    "Counts are per study; a study spanning several architectures, families or "
    "losses is counted under each, so rows may exceed the group total. Under each "
    "application domain, the upper rows give the architecture class and the "
    "\u201cof which by family\u201d rows the finer architecture family. \u201cObject "
    "detector\u201d groups bounding-box and instance-segmentation detectors (YOLO, "
    "Faster/Mask R-CNN, RetinaNet, SSD, DETR and variants). Loss objectives are "
    "grouped as standard (cross-entropy, Dice, focal, Tversky, IoU, L1, MSE), "
    "vessel-geometry (centerline/topological, boundary-aware) and training-strategy "
    "(adversarial, contrastive, consistency, distillation). Reference numbers "
    "correspond to the supplementary reference list L1. Abbreviations: CNN, "
    "convolutional neural network; GNN/GCN, graph (convolutional) neural network; "
    "GAN, generative adversarial network; MLP, multilayer perceptron; RNN/LSTM, "
    "recurrent / long short-term memory network; ViT, vision transformer; FCN, "
    "fully convolutional network; HRNet, high-resolution network; PSPNet, pyramid "
    "scene parsing network; BCE, binary cross-entropy; MSE, mean squared error; "
    "IoU, intersection over union."
)
run.italic = True
run.font.size = Pt(8)
run.font.name = "Arial"

doc.save(OUT_PATH)
print(f"\nSaved \u2192 {OUT_PATH}")