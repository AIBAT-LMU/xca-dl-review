#!/usr/bin/env python3
"""
05_fig4_quadas.py -- Figure 4: QUADAS-2 risk of bias and applicability.
Output: results/figures/Fig4_QUADAS2.png / .pdf

Risk-of-bias domain ratings are derived from the signalling questions the
standard way (all 'yes' -> low; any 'no' -> high; else unclear); the three
applicability ratings are stored directly.
"""
import os
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import common as C

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False})
LOW, UNC, HIGH = "#2E8B6F", "#E7C24B", "#C0483B"

conn = C.connect()
sig = defaultdict(dict)
for r in conn.execute("SELECT paper_id, item_id, result FROM checklist_results "
                      "WHERE checklist_name='QUADAS-2'"):
    sig[r["paper_id"]][r["item_id"]] = (r["result"] or "").strip().lower()
conn.close()
N = len(sig)

ROB = [("Patient selection", ["1.1", "1.2", "1.3"]),
       ("Index test", ["2.1", "2.2"]),
       ("Reference standard", ["3.1", "3.2"]),
       ("Flow & timing", ["4.1", "4.2", "4.3", "4.4"])]
APP = [("Patient selection", "1.app"), ("Index test", "2.app"),
       ("Reference standard", "3.app")]


def derive(vals):
    if any(v == "no" for v in vals):
        return "high"
    if all(v == "yes" for v in vals):
        return "low"
    return "unclear"


def pct(items, applic=False):
    c = {"low": 0, "unclear": 0, "high": 0}
    for d in sig.values():
        r = d.get(items, "unclear") if applic else derive([d.get(q, "unclear") for q in items])
        c[r] += 1
    return [100 * c[k] / N for k in ("low", "unclear", "high")]


rows = ([(f"{n}", pct(qs)) for n, qs in ROB]
        + [(f"{n} ", pct(it, True)) for n, it in APP])   # trailing space marks applicability
labels = [r[0] for r in rows][::-1]
data = [r[1] for r in rows][::-1]

fig, ax = plt.subplots(figsize=(9, 5.2))
y = range(len(rows))
lefts = [0] * len(rows)
for i, (col, name) in enumerate([(LOW, "Low"), (UNC, "Unclear"), (HIGH, "High")]):
    widths = [d[i] for d in data]
    ax.barh(y, widths, left=lefts, color=col, label=name, height=0.66,
            edgecolor="white", linewidth=0.8)
    for yi, (w, l) in enumerate(zip(widths, lefts)):
        if w >= 7:
            ax.text(l + w / 2, yi, f"{w:.0f}", ha="center", va="center",
                    color="white", fontsize=9, fontweight="bold")
    lefts = [l + w for l, w in zip(lefts, widths)]

ax.set_yticks(list(y))
ax.set_yticklabels(labels)
ax.set_xlim(0, 100)
ax.set_xlabel("Proportion of studies (%)")
ax.axhline(2.5, color="#cccccc", lw=0.8, ls="--")
ax.text(101, 5.0, "Risk of bias", rotation=90, va="center", fontsize=9,
        color="#555", fontweight="bold")
ax.text(101, 1.0, "Applicability", rotation=90, va="center", fontsize=9,
        color="#555", fontweight="bold")
ax.legend(ncol=3, loc="upper center", bbox_to_anchor=(0.5, -0.13), frameon=False)
plt.tight_layout()
C.ensure_dirs()
for ext in ("png", "pdf"):
    fig.savefig(os.path.join(C.OUT_FIGURES, f"Fig4_QUADAS2.{ext}"),
                dpi=200, bbox_inches="tight")
print("Saved Fig4_QUADAS2.png / .pdf")
