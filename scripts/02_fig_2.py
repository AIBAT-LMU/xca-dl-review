#!/usr/bin/env python3
"""
02_fig_2.py
Figure 2 - Application domains and task structure

Systematic Review: "Toward clinical-grade deep learning in coronary angiography"

Input:  xca_dl_review.db
Output: results/figures/Fig2_application_domains.png / .pdf

Panel A: proportion of studies addressing one versus several domains.
Panel B: number of studies per application domain (studies may appear in
         several categories).

Domain definitions live in common.DOMAIN_MAP and are shared with 02_tab_s1.py,
so the figure and the supplementary table cannot drift apart.
"""

import math
import os
from collections import Counter

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
import numpy as np

import common as C

plt.rcParams.update({
    "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight",
    "font.family": "sans-serif", "font.size": 10,
    "pdf.fonttype": 42, "ps.fonttype": 42,   # embed real fonts, not outlines
    "svg.fonttype": "none",
})

# Panel letters and panel titles are placed in figure coordinates. Placing them
# per-axes puts them at different heights, because the donut carries
# aspect="equal" and its axes box is therefore shorter than the bar chart's.
TITLE_Y = 0.95
LETTER_Y = 0.99

### Data
conn = C.connect()
papers = C.load_papers(conn)
N = len(papers)

by_domain, _ = C.application_domains(conn, papers)
per_paper = C.domains_per_paper(by_domain, papers)
conn.close()

sizes = Counter(len(d) for d in per_paper.values())
if sizes[0]:
    raise AssertionError(
        f"{sizes[0]} studies have no application domain in the published database")

n_single = sizes[1]
n_multi = sum(v for k, v in sizes.items() if k > 1)
counts = {d: len(by_domain.get(d, set())) for d in C.DOMAIN_ORDER}

print(f"Figure 2 (N = {N})")
print(f"  A. Single domain: {C.fmt(n_single, N)}   "
      f"Multiple domains: {C.fmt(n_multi, N)}")
print(f"     domains per study: {dict(sorted(sizes.items()))}")
print("  B. Application domains:")
for d in C.DOMAIN_ORDER:
    print(f"       {d:22s} {C.fmt(counts[d], N)}")

### Figure
fig = plt.figure(figsize=(11, 4.4))
gs = gridspec.GridSpec(1, 2, width_ratios=[0.72, 1.28], wspace=0.28,
                       left=0.06, right=0.97, top=0.88, bottom=0.10)

# Panel A - task structure
ax_a = fig.add_subplot(gs[0])
wedges, _ = ax_a.pie(
    [n_single, n_multi], labels=None, startangle=90,
    colors=["#4285F4", "#C8C8C8"],
    wedgeprops=dict(width=0.35, edgecolor="white", linewidth=2.5),
    counterclock=False,
)
for wedge, n in zip(wedges, (n_single, n_multi)):
    angle = math.radians((wedge.theta1 + wedge.theta2) / 2)
    ax_a.text(0.83 * math.cos(angle), 0.83 * math.sin(angle),
              f"{C.pct(n, N)}%", ha="center", va="center",
              fontsize=10, fontweight="bold", color="#111111")
ax_a.text(0, 0, f"n={N}", ha="center", va="center",
          fontsize=12, fontweight="bold", color="#333333")
ax_a.set_aspect("equal")
ax_a.legend(
    handles=[
        mpatches.Patch(facecolor="#4285F4", label=f"Single domain (n={n_single})"),
        mpatches.Patch(facecolor="#C8C8C8", label=f"Multiple domains (n={n_multi})"),
    ],
    loc="upper center", bbox_to_anchor=(0.5, -0.05), frameon=False,
    fontsize=8.5, handlelength=1.0, handleheight=0.9, labelspacing=0.3)


# Panel B - application domains
ax_b = fig.add_subplot(gs[1])
labels = list(reversed(C.DOMAIN_ORDER))
values = [counts[d] for d in labels]
y = np.arange(len(labels))

ax_b.barh(y, values, color=[C.DOMAIN_COLORS[d] for d in labels],
          height=0.55, edgecolor="white", linewidth=0.8)
for value, yy in zip(values, y):
    ax_b.text(value + 0.8, yy, f"{value} ({C.pct(value, N)}%)",
              va="center", ha="left", fontsize=9,
              fontweight="bold", color="#333333")

ax_b.set_yticks(y)
ax_b.set_yticklabels(labels, fontsize=9.5)
ax_b.set_xlabel("Number of studies", fontsize=10)
ax_b.set_xlim(0, max(values) + 22)
ax_b.spines["top"].set_visible(False)
ax_b.spines["right"].set_visible(False)


# Titles and letters share a baseline across both panels.
for x, title in ((0.22, "Task Structure"), (0.66, "Application Domains")):
    fig.text(x, TITLE_Y, title, fontsize=11.5, fontweight="bold",
             ha="center", va="center")
for x, letter in ((0.015, "a"), (0.40, "b")):
    fig.text(x, LETTER_Y, letter, fontsize=14, fontweight="bold",
             ha="left", va="top")

C.ensure_dirs()
stem = os.path.join(C.OUT_FIGURES, "Fig2_application_domains")
# bbox_inches="tight" would re-crop and undo the figure-coordinate alignment.
for ext in ("png", "pdf", "svg"):
    fig.savefig(f"{stem}.{ext}", facecolor="white")
plt.close()
print(f"\nSaved \u2192 {stem}.png / .pdf / .svg")
