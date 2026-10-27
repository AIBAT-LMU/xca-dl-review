#!/usr/bin/env python3
"""
05_fig3_readiness.py -- Figure 3: clinical-readiness overview.
  A (left):  CLAIM 2024 compliance by section (stacked bars).
  B (right): translational feasibility scorecard, six domains (lollipop).
Output: results/figures/Fig3_readiness.png / .pdf

Same layout/palette as the original figure; corrected CLAIM data (item 37 fix)
and current field names. N = 196.
"""
import os
import statistics
from collections import OrderedDict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np

import common as C

plt.rcParams.update({"font.family": "sans-serif", "font.size": 15,
                     "axes.titlesize": 17, "axes.titleweight": "bold",
                     "axes.labelsize": 15, "savefig.dpi": 300, "savefig.bbox": "tight"})

D_COLORS = {"Validation &\nGeneralizability": "#1E88E5",
            "Reproducibility &\nTransparency": "#43A047",
            "Workflow\nIntegration": "#7E57C2", "Study\nDesign": "#FB8C00",
            "Annotation\nQuality": "#E53935", "Reporting\nQuality": "#00ACC1"}
COL_YES, COL_NO, COL_PARTIAL = "#1565C0", "#E0E0E0", "#64B5F6"

conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)


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
    return any(v in pos for v in vs) if pos else any(v not in exc for v in vs)


def frac(fn):
    return round(100 * sum(fn(p.paper_id) for p in papers) / N, 1)


# ── Panel A: CLAIM by section ──
CLAIM_SECTIONS = OrderedDict([
    ("Title / Abstract", (1, 2)), ("Introduction", (3, 4)), ("Study design", (5, 6)),
    ("Data provenance", (7, 13)), ("Ground truth", (14, 18)), ("Data partitions", (19, 21)),
    ("Model description", (22, 25)), ("Evaluation", (26, 31)), ("Results", (32, 38)),
    ("Discussion", (39, 42)), ("Other info", (43, 44))])
sec_yes, sec_no, sec_part = [], [], []
for name, (s, e) in CLAIM_SECTIONS.items():
    ph = ",".join(str(i) for i in range(s, e + 1))
    y, n, pa, tot = conn.execute(
        f"SELECT SUM(result='yes'), SUM(result='no'), SUM(result='partial'), "
        f"SUM(result!='not_applicable') FROM checklist_results "
        f"WHERE checklist_name='CLAIM 2024' AND CAST(item_id AS INT) IN ({ph})").fetchone()
    tot = max(tot, 1)
    sec_yes.append(100 * y / tot)
    sec_no.append(100 * n / tot)
    sec_part.append(100 * (pa or 0) / tot)

claim_scores = []
for r in conn.execute("SELECT paper_id, SUM(result='yes') y, SUM(result='no') n "
                      "FROM checklist_results WHERE checklist_name='CLAIM 2024' GROUP BY paper_id"):
    if r["y"] + r["n"]:
        claim_scores.append(100 * r["y"] / (r["y"] + r["n"]))
claim_med, claim_min, claim_max = (statistics.median(claim_scores),
                                   min(claim_scores), max(claim_scores))

# ── Panel B: feasibility domains ──
NR = ("", "not_reported", "not reported", "n/a")
domains = OrderedDict()
domains["Validation &\nGeneralizability"] = OrderedDict([
    ("External validation", frac(lambda p: val(p, "external_validation_used") == "y")),
    ("Multi-center data", frac(lambda p: val(p, "multi_center") == "multi-center")),
    ("Prospective validation", frac(lambda p: val(p, "prospective_validation") == "y"))])
domains["Reproducibility &\nTransparency"] = OrderedDict([
    ("Code available", frac(lambda p: val(p, "code_availability") in ("y", "partly"))),
    ("Open dataset", frac(lambda p: any_like(p, "dataset_accessibility__%", pos=["open"]))),
    ("Model shared", frac(lambda p: val(p, "trained_model_available") == "y")),
    ("Named explainability\ntechnique", frac(lambda p: any_like(p, "explainability_technique__%", exc=[""])))])
domains["Workflow\nIntegration"] = OrderedDict([
    ("Real-time capability\ndemonstrated", frac(lambda p: val(p, "real_time_capability") == "y")),
    ("Inference time\nreported", frac(lambda p: any_like(p, "inference_time_reported__%", pos=["y"])))])
domains["Study\nDesign"] = OrderedDict([
    ("Target vessel specified", frac(lambda p: val(p, "target_vessel") not in NR)),
    ("Age reported", frac(lambda p: val(p, "age_reported") == "y")),
    ("Sex reported", frac(lambda p: val(p, "sex_reported") == "y")),
    ("Patient presentation\nreported", frac(lambda p: val(p, "patient_presentation") not in NR))])
domains["Annotation\nQuality"] = OrderedDict([
    ("Annotator expertise\ndescribed", frac(lambda p: any_like(p, "annotator_expertise__%", exc=list(NR) + ["unclear"]))),
    ("≥2 annotators", frac(lambda p: any_like(p, "annotator_count__%", pos=[str(n) for n in range(2, 30)] + [">=3"])))])
domains["Reporting\nQuality"] = OrderedDict(zip(CLAIM_SECTIONS.keys(), [round(v, 1) for v in sec_yes]))
conn.close()

# ── Figure ──
fig = plt.figure(figsize=(20, 14))
gs = gridspec.GridSpec(1, 2, width_ratios=[1.05, 1], wspace=0.40)

ax_a = fig.add_subplot(gs[0])
sec_labels = [f"{n}\n(Items {s}–{e})" if s != e else f"{n}\n(Item {s})"
              for n, (s, e) in CLAIM_SECTIONS.items()]
y_pos = np.arange(len(sec_labels))
ax_a.set_title("CLAIM 2024 Checklist Compliance", fontsize=17, fontstyle="italic",
               loc="left", pad=10, color="#333333")
ax_a.barh(y_pos, sec_yes, color=COL_YES, edgecolor="white", height=0.7, label="Reported")
ax_a.barh(y_pos, sec_no, left=sec_yes,
          color=COL_NO, edgecolor="white", height=0.7, label="Not reported")
for i, (yp, pp) in enumerate(zip(sec_yes, sec_part)):
    comb = yp + pp
    if yp >= 10:
        ax_a.text(yp / 2, i, f"{yp:.0f}%", ha="center", va="center", fontsize=13,
                  color="white", fontweight="bold")
    elif comb >= 10:
        ax_a.text(comb / 2, i, f"{comb:.0f}%", ha="center", va="center", fontsize=13,
                  color="white", fontweight="bold")
    else:
        ax_a.text(comb + 2, i, f"{comb:.0f}%", ha="left", va="center", fontsize=13, color="#444")
ax_a.set_yticks(y_pos)
ax_a.set_yticklabels(sec_labels, fontsize=14, linespacing=1.2)
ax_a.invert_yaxis()
ax_a.set_xlim(0, 100)
ax_a.set_xlabel("Compliance (%)", fontsize=15)
ax_a.spines[["top", "right"]].set_visible(False)
ax_a.legend(loc="lower right", fontsize=13, frameon=True, framealpha=0.92, edgecolor="#ccc")

ax_b = fig.add_subplot(gs[1])
ax_b.set_title("Translational Feasibility Scorecard", fontsize=17, fontstyle="italic",
               loc="left", pad=10, color="#333333")
all_labels, all_values, all_colors = [], [], []
legend_patches = []
for dom, metrics in domains.items():
    col = D_COLORS[dom]
    if dom == "Reporting\nQuality":
        all_labels.append("CLAIM compliance\n(mean across 11 sections)")
        all_values.append(round(np.mean(list(metrics.values())), 1))
        all_colors.append(col)
    else:
        for lab, v in metrics.items():
            all_labels.append(lab)
            all_values.append(v)
            all_colors.append(col)
    legend_patches.append(mpatches.Patch(facecolor=col, label=dom.replace("\n", " ")))
y_pos_b, cur, dividers = [], 0, []
doms = list(domains.items())
for di, (dom, metrics) in enumerate(doms):
    n = 1 if dom == "Reporting\nQuality" else len(metrics)
    for _ in range(n):
        y_pos_b.append(cur)
        cur += 1
    if di < len(doms) - 1:
        cur += 0.8
    dividers.append(cur - 0.4)
y_pos_b = np.array(y_pos_b)
for xr in (25, 50, 75):
    ax_b.axvline(xr, color="#e8e8e8", lw=1.0, zorder=0)
ax_b.hlines(y_pos_b, 0, all_values, colors=all_colors, linewidth=3.2, alpha=0.8)
ax_b.scatter(all_values, y_pos_b, c=all_colors, s=150, zorder=5, edgecolors="white", linewidths=1.4)
for v, yp in zip(all_values, y_pos_b):
    ax_b.text(v + 2.5, yp, f"{v:.0f}%", va="center", ha="left", fontsize=14,
              fontweight="semibold", color="#333")
for dy in dividers[:-1]:
    ax_b.axhline(dy, color="#c0c0c0", lw=1.0, ls="--")
ax_b.legend(handles=legend_patches, loc="upper right", fontsize=13, frameon=True,
            framealpha=0.93, edgecolor="#ccc", title="Domain", title_fontsize=14,
            handlelength=1.2, handleheight=1.2, labelspacing=0.55)
ax_b.set_yticks(y_pos_b)
ax_b.set_yticklabels(all_labels, fontsize=14)
ax_b.invert_yaxis()
ax_b.set_xlim(0, 100)
ax_b.set_xlabel("Studies (%)", fontsize=15)
ax_b.spines[["top", "right"]].set_visible(False)
ax_b.tick_params(axis="y", pad=6)
for ax, lab in ((ax_a, "a"), (ax_b, "b")):
    ax.text(-0.06, 1.04, lab, transform=ax.transAxes, fontsize=22, fontweight="bold",
            va="bottom", ha="left", color="#111")

C.ensure_dirs()
for ext in ("png", "pdf"):
    plt.savefig(os.path.join(C.OUT_FIGURES, f"Fig3_readiness.{ext}"),
                bbox_inches="tight", facecolor="white")
print(f"Saved Fig3_readiness  (CLAIM median {claim_med:.0f}%, range {claim_min:.0f}-{claim_max:.0f}%)")
