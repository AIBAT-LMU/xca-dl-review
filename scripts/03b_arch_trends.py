#!/usr/bin/env python3
"""
03b_arch_trends.py -- architecture composition by publication period.

Reproducible source for the "architectural choices shifted over time" numbers in
the Deep learning methodologies chapter (there was previously no script for
these; they were computed ad hoc on the pre-reextraction database). Definitions
match Table S2: architecture *class* = base_architecture, *family* =
architecture_family, both per primary model, a study counted once per class /
family it uses.

Note on the period bins: these are deliberately NOT the same as Table 1's
([table1] periods in review.toml). Table 1 is a descriptive census, so it breaks
2026 onto its own line as the current, incomplete year. Here the cells are
*within-period composition percentages* read as a trend, where a standalone ~6-
month 2026 bin (~22 studies) would be both too thin to be a trend point and an
unfair comparison against full three-year windows -- a partial-year sample can
swing a composition % on noise and read as a shift that is really just
incompleteness. So 2026 stays folded into the final 2023-2026 window and these
bins are hardcoded rather than read from C.PERIODS, so a future change to Table
1's binning cannot silently re-split the trend.

Prints per period (2016-2019, 2020-2022, 2023-2026; last window includes the
partial year 2026):
  CNN-only          all primary models base_architecture == CNN
  Transformer       base_architecture in {Transformer, Hybrid CNN+Transformer}
    hybrid / pure   split of the above
  U-Net             architecture_family == U-Net
  Object detector   architecture_family == Object detector
    YOLO            a primary model named 'YOLO...'
  GNN               base_architecture == GNN/GCN
"""
from collections import defaultdict

import common as C

# Hardcoded on purpose -- see the module docstring. Do NOT switch to C.PERIODS:
# the trend keeps 2026 folded into 2023-2026, unlike Table 1's descriptive bins.
PERIODS = [(2016, 2019), (2020, 2022), (2023, 2026)]
TX = {"Transformer", "Hybrid CNN+Transformer"}

conn = C.connect()
papers = C.load_papers(conn)
year = {p.paper_id: p.year for p in papers}

ba, fam = defaultdict(set), defaultdict(set)
for r in C.primary_model_rows(conn, papers):
    if r.base_architecture:
        ba[r.paper_id].add(r.base_architecture)
    if r.architecture_family:
        fam[r.paper_id].add(r.architecture_family)

# YOLO: a primary model whose name/type contains 'yolo'
yolo = set()
for pid, val in conn.execute(
        "SELECT paper_id, value FROM extractions "
        "WHERE field_name LIKE 'model_label%' OR field_name LIKE 'model_type%'"):
    if val and "yolo" in val.lower():
        yolo.add(pid)
conn.close()

CRITERIA = [
    ("CNN-only", lambda p: ba[p] and ba[p] <= {"CNN"}),
    ("Transformer-incorporating", lambda p: bool(ba[p] & TX)),
    ("  hybrid CNN+Transformer", lambda p: "Hybrid CNN+Transformer" in ba[p]),
    ("  pure Transformer", lambda p: "Transformer" in ba[p]),
    ("U-Net (family)", lambda p: "U-Net" in fam[p]),
    ("Object detector (family)", lambda p: "Object detector" in fam[p]),
    ("  YOLO (named)", lambda p: p in yolo),
    ("GNN/GCN", lambda p: "GNN/GCN" in ba[p]),
]

print(f"Architecture composition by period (studies; % of period)")
hdr = "  ".join(f"{lo}-{hi}" for lo, hi in PERIODS)
print(f"{'':32s}{hdr}")
sizes = [sum(1 for p in papers if lo <= year[p.paper_id] <= hi) for lo, hi in PERIODS]
print(f"{'n studies':32s}" + "  ".join(f"{s:^9d}" for s in sizes))
for label, pred in CRITERIA:
    cells = []
    for (lo, hi), tot in zip(PERIODS, sizes):
        hit = sum(1 for p in papers if lo <= year[p.paper_id] <= hi and pred(p.paper_id))
        cells.append(f"{hit} ({round(100*hit/tot) if tot else 0}%)")
    print(f"{label:32s}" + "  ".join(f"{c:^9s}" for c in cells))
