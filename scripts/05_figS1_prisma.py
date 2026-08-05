#!/usr/bin/env python3
"""
05_figS1_prisma.py -- Figure S1: PRISMA 2020 flow diagram (Round 1 + Round 2 merged).
Output: results/figures/FigS1_PRISMA.png / .pdf

Cumulative flow across both search rounds, ending at the n = 196 corpus. Numbers
are the merged R1+R2 tallies checked in the session ledger. The one Round-1 study
included but not extracted in the first round is carried through the citation-
chasing arm (Included 105 -> 106). The three Round-1 "reports not retrieved" were
located in Round 2, so cumulative "not retrieved" is 0 in both arms.
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

import common as C

# ── palette: classic black-and-white PRISMA 2020 ──
HEADER = "white"       # header bars
BAND = "#d9d9d9"       # phase band labels (light grey)
EDGE = "#000000"       # box borders
INC_FILL = "white"     # included box
INC_EDGE = "#000000"
TXT = "#000000"
ARROW = dict(arrowstyle="-|>", color="#000000", lw=1.2, mutation_scale=13)

plt.rcParams.update({"font.family": "DejaVu Sans"})
fig, ax = plt.subplots(figsize=(13.2, 7.4))
ax.set_xlim(-0.35, 16.4)
ax.set_ylim(0, 10)
ax.axis("off")


def box(cx, cy, w, h, text, *, fill="white", edge=EDGE, tc=TXT, fs=8.0,
        bold=False, align="center"):
    ax.add_patch(FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle="round,pad=0.015,rounding_size=0.08",
        linewidth=1.4, edgecolor=edge, facecolor=fill, zorder=2))
    if align == "left":
        ax.text(cx - w / 2 + 0.16, cy, text, ha="left", va="center",
                fontsize=fs, color=tc, fontweight="bold" if bold else "normal",
                zorder=3, linespacing=1.3)
    else:
        ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, color=tc,
                fontweight="bold" if bold else "normal", zorder=3, linespacing=1.3)


def band(cy, h, label):
    w = 0.6
    ax.add_patch(FancyBboxPatch((-0.05, cy - h / 2), w, h,
                                boxstyle="round,pad=0.01,rounding_size=0.06",
                                linewidth=1.0, edgecolor=EDGE, facecolor=BAND, zorder=2))
    ax.text(-0.05 + w / 2, cy, label, ha="center", va="center", rotation=90,
            fontsize=10, color=TXT, fontweight="bold", zorder=3)


def arrow(x0, y0, x1, y1, elbow=False):
    cs = "angle,angleA=-90,angleB=0,rad=0" if elbow else "arc3,rad=0"
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops={**ARROW, "connectionstyle": cs}, zorder=1)


# ── column geometry ──
A1, A1x = 2.95, 6.5     # arm-1 main, arm-1 excluded
A2, A2x = 10.1, 13.65   # arm-2 main, arm-2 excluded
MW, XW = 3.3, 3.0       # main / excluded box widths

# ── header bars ──
for cx, w, label in [(4.65, 6.7, "Identification of studies via databases"),
                     (11.8, 6.7, "Identification of studies via other methods")]:
    ax.add_patch(FancyBboxPatch((cx - w / 2, 9.05), w, 0.55,
                                boxstyle="round,pad=0.01,rounding_size=0.06",
                                linewidth=1.2, edgecolor=EDGE, facecolor=HEADER, zorder=2))
    ax.text(cx, 9.32, label, ha="center", va="center", fontsize=10.5,
            color=TXT, fontweight="bold", zorder=3)

# ── phase bands ──
band(7.95, 2.5, "Identification")
band(4.9, 4.0, "Screening")
band(1.35, 1.5, "Included")

# ── row y-centres ──
Y_ID, Y_SCR, Y_SGT, Y_ASS, Y_INC = 8.0, 6.35, 5.1, 3.6, 1.35

# ── ARM 1: databases ──
box(A1, Y_ID, MW, 1.45,
    "Records identified from:\nPubMed (n=973)\nWeb of Science (n=399)\n"
    "IEEE Xplore (n=162)", align="left")
box(A1x, Y_ID, XW, 1.0, "Records removed:\nDuplicates (n=361)", align="left")
box(A1, Y_SCR, MW, 0.85, "Records screened\n(n=1173)")
box(A1x, Y_SCR, XW, 0.85, "Records excluded\n(n=1048)")
box(A1, Y_SGT, MW, 0.85, "Reports sought for retrieval\n(n=125)")
box(A1, Y_ASS, MW, 0.85, "Reports assessed for eligibility\n(n=125)")
box(A1x, Y_ASS, XW, 1.55,
    "Reports excluded:\nNo peer review (n=3)\nNo DL on XCA input (n=9)\n"
    "Wrong modality (n=20)\nCommercial system (n=2)\nNo performance (n=1)",
    align="left")

# ── ARM 2: other methods ──
box(A2, Y_ID, MW, 1.45,
    "Records identified from:\nBackward citation (n=2287)\n"
    "Forward citation (n=575)", align="left")
box(A2x, Y_ID, XW, 1.45,
    "Records removed:\nAlready reviewed (n=626)\nOlder than 10 years (n=391)\n"
    "Duplicates (n=62)\nBooks (n=3)", align="left")
box(A2, Y_SCR, MW, 0.85, "Records screened\n(n=1780)")
box(A2x, Y_SCR, XW, 0.85, "Records excluded\n(n=1604)")
box(A2, Y_SGT, MW, 0.85, "Reports sought for retrieval\n(n=176)")
box(A2, Y_ASS, MW, 0.85, "Reports assessed for eligibility\n(n=176)")
box(A2x, Y_ASS, XW, 1.35,
    "Reports excluded:\nNo peer review (n=20)\nNo DL on XCA input (n=41)\n"
    "Wrong modality (n=8)\nNo performance (n=1)", align="left")

# ── included box ──
box(A1, Y_INC, 3.5, 0.9, "Studies included in review\n(n=196)",
    fill=INC_FILL, edge=INC_EDGE, tc=TXT, fs=10, bold=True)

# ── arrows ──
for A, Ax in [(A1, A1x), (A2, A2x)]:
    arrow(A + MW / 2, Y_ID, Ax - XW / 2, Y_ID)          # identified -> removed
    arrow(A, Y_ID - 0.73, A, Y_SCR + 0.43)             # identified -> screened
    arrow(A + MW / 2, Y_SCR, Ax - XW / 2, Y_SCR)       # screened -> excluded
    arrow(A, Y_SCR - 0.43, A, Y_SGT + 0.43)            # screened -> sought
    arrow(A, Y_SGT - 0.43, A, Y_ASS + 0.43)            # sought -> assessed
    arrow(A + MW / 2, Y_ASS, Ax - XW / 2, Y_ASS)       # assessed -> excluded reasons

arrow(A1, Y_ASS - 0.43, A1, Y_INC + 0.45)              # arm1 assessed -> included
arrow(A2, Y_ASS - 0.43, A1 + 3.5 / 2, Y_INC, elbow=True)  # arm2 assessed -> included

C.ensure_dirs()
for ext in ("png", "pdf"):
    fig.savefig(os.path.join(C.OUT_FIGURES, f"FigS1_PRISMA.{ext}"),
                dpi=200, bbox_inches="tight", facecolor="white")
print("Saved FigS1_PRISMA.png / .pdf  (n=196; databases 90 + other methods 106)")
