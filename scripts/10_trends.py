#!/usr/bin/env python3
"""
10_trends.py -- formal tests for the temporal claims, and a weighting
sensitivity analysis for the feasibility scorecard.
Output: console only (the figures are quoted in the Results and Methods).

Requested by Reviewer 1, who noted that the temporal trends were asserted
without testing and that the scorecard weighting and thresholds were defined
post hoc.

Analyses
--------
1. Composite feasibility score and CLAIM 2024 compliance against publication
   year: Spearman rho and ordinary least squares slope with a 95% interval.
   Publication year as a continuous predictor is the primary test; the period
   bins are descriptive, because they were chosen post hoc and the earliest
   contains few studies.
2. The same score adjusted for publication type, since journal articles score
   higher and make up a larger share of recent output.
3. Period means with 95% intervals and a Kruskal-Wallis test across periods.
4. Per-criterion trend across publication year (Cochran-Armitage, equivalent
   here to the correlation-based trend statistic).
5. Weighting sensitivity: the composite score recomputed under two alternative
   weightings, each compared with the published equal-weight ranking by
   Spearman rho and Kendall tau.

All tests are implemented in the standard library and numpy, so the script adds
no dependency beyond the existing requirements.

NOTE: booleans() is duplicated from 04_tab_s7_feasibility.py. Any change to a
criterion must be made in all four places.
"""

import math
import statistics as st
from collections import Counter

import numpy as np

import common as C

NR = ("", "not_reported", "not reported", "n/a")

# Period bins for the descriptive comparison. Deliberately not Table 1's bins:
# 2026 stays folded into the final window, as in 03b_arch_trends.py.
PERIODS = [(2016, 2019), (2020, 2022), (2023, 2026)]

LABELS = [
    "External validation", "Multi-centre data", "Prospective validation",
    "Code availability", "Open dataset", "Model weights shared",
    "Explainability method", "Real-time capability", "Inference time reported",
    "Target vessel specified", "Patient age reported", "Patient sex reported",
    "Clinical presentation", "Annotator expertise", "Two or more annotators",
]

# Domain of each criterion, in column order: 0 validation, 1 reproducibility,
# 2 workflow, 3 study design, 4 annotation.
DOMAIN = [0, 0, 0, 1, 1, 1, 1, 2, 2, 3, 3, 3, 3, 4, 4]
DOMAIN_NAMES = ["Validation", "Reproducibility", "Workflow", "Study design", "Annotation"]


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


def claim_pct(conn, pid):
    r = conn.execute("SELECT SUM(result='yes'), SUM(result='no') FROM checklist_results "
                     "WHERE checklist_name='CLAIM 2024' AND paper_id=?", (pid,)).fetchone()
    y, n = r[0] or 0, r[1] or 0
    return 100 * y / (y + n) if (y + n) else None


### Statistics
def normal_p(z):
    return math.erfc(abs(z) / math.sqrt(2))


def chi2_sf(x, k):
    """Upper tail of the chi-square distribution for integer degrees of freedom."""
    if x <= 0:
        return 1.0
    if k % 2 == 0:
        term, total = 1.0, 1.0
        for i in range(1, k // 2):
            term *= (x / 2) / i
            total += term
        return math.exp(-x / 2) * total
    s = math.erfc(math.sqrt(x / 2))
    if k == 1:
        return s
    term = math.sqrt(2 * x / math.pi) * math.exp(-x / 2)
    total = term
    for i in range(1, (k - 1) // 2):
        term *= x / (2 * i + 1)
        total += term
    return s + total


def ranks(v):
    order = sorted(range(len(v)), key=lambda i: v[i])
    out, i = [0.0] * len(v), 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and v[order[j + 1]] == v[order[i]]:
            j += 1
        r = (i + j) / 2 + 1
        for k in range(i, j + 1):
            out[order[k]] = r
        i = j + 1
    return out


def pearson(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    xc, yc = x - x.mean(), y - y.mean()
    denom = math.sqrt((xc @ xc) * (yc @ yc))
    return (xc @ yc) / denom if denom else 0.0


def spearman(x, y):
    r = pearson(ranks(list(x)), ranks(list(y)))
    n = len(x)
    if abs(r) >= 1:
        return r, 0.0
    t = r * math.sqrt((n - 2) / (1 - r * r))
    return r, normal_p(t)


def kendall_tau(x, y):
    """Kendall's tau-b (tie-corrected)."""
    n = len(x)
    con = dis = 0
    for i in range(n):
        for j in range(i + 1, n):
            s = (x[i] - x[j]) * (y[i] - y[j])
            if s > 0:
                con += 1
            elif s < 0:
                dis += 1
    n0 = n * (n - 1) / 2
    tie = lambda v: sum(c * (c - 1) / 2 for c in Counter(v).values())
    denom = math.sqrt((n0 - tie(x)) * (n0 - tie(y)))
    return (con - dis) / denom if denom else 0.0


def ols(X, y):
    """Least squares with normal-approximation standard errors."""
    X, y = np.asarray(X, float), np.asarray(y, float)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    cov = (resid @ resid) / dof * np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(cov))
    return beta, se, [normal_p(b / s) for b, s in zip(beta, se)]


def kruskal(groups):
    pooled = [v for g in groups for v in g]
    rk = ranks(pooled)
    n, idx, terms = len(pooled), 0, 0.0
    for g in groups:
        rs = sum(rk[idx:idx + len(g)])
        terms += rs * rs / len(g)
        idx += len(g)
    h = 12 / (n * (n + 1)) * terms - 3 * (n + 1)
    counts = Counter(pooled)
    ties = sum(c ** 3 - c for c in counts.values())
    if ties:
        h /= 1 - ties / (n ** 3 - n)
    return h, chi2_sf(h, len(groups) - 1)


def trend_z(x, flags):
    """Cochran-Armitage trend statistic for a binary outcome over an ordered score."""
    if len(set(flags)) < 2:
        return None, None
    z = pearson(x, flags) * math.sqrt(len(flags) - 1)
    return z, normal_p(z)


### Data
conn = C.connect()
papers = C.load_papers(conn)
rows = []
for p in papers:
    b = booleans(conn, p.paper_id)
    rows.append({"year": p.year, "journal": p.pub_type == "journal", "bools": b,
                 "sigma": sum(b), "claim": claim_pct(conn, p.paper_id)})
conn.close()

N = len(rows)
year = [r["year"] for r in rows]
sigma = [r["sigma"] for r in rows]
B = np.array([r["bools"] for r in rows], float)

print(f"10_trends: N = {N}, publication years {min(year)}-{max(year)}")
print(f"  composite score: mean {st.mean(sigma):.2f}, median {st.median(sigma):.0f}, "
      f"range {min(sigma)}-{max(sigma)}")
print(f"  distribution: {dict(sorted(Counter(sigma).items()))}")

### 1. Continuous-year trends
print("\n1. Trend against publication year (primary test)")
rho, p = spearman(year, sigma)
ones = np.ones(N)
beta, se, pv = ols(np.column_stack([ones, year]), sigma)
print(f"   feasibility score: Spearman rho = {rho:.3f} (p = {p:.1e}); "
      f"slope {beta[1]:.3f} points/year "
      f"(95% CI {beta[1] - 1.96 * se[1]:.3f} to {beta[1] + 1.96 * se[1]:.3f}, p = {pv[1]:.1e})")
cy = [(r["year"], r["claim"]) for r in rows if r["claim"] is not None]
rho, p = spearman([a for a, _ in cy], [b for _, b in cy])
beta_c, se_c, pv_c = ols(np.column_stack([np.ones(len(cy)), [a for a, _ in cy]]),
                         [b for _, b in cy])
print(f"   CLAIM 2024:        Spearman rho = {rho:.3f} (p = {p:.1e}); "
      f"slope {beta_c[1]:.2f} pp/year "
      f"(95% CI {beta_c[1] - 1.96 * se_c[1]:.2f} to {beta_c[1] + 1.96 * se_c[1]:.2f}, "
      f"p = {pv_c[1]:.1e})")

### 2. Adjusted for publication type
print("\n2. Feasibility score adjusted for publication type")
yc = np.array(year, float) - np.mean(year)
jr = np.array([1.0 if r["journal"] else 0.0 for r in rows])
beta_a, se_a, pv_a = ols(np.column_stack([ones, yc, jr]), sigma)
print(f"   year          beta = {beta_a[1]:.3f} (SE {se_a[1]:.3f}, p = {pv_a[1]:.1e})")
print(f"   journal       beta = {beta_a[2]:.3f} (SE {se_a[2]:.3f}, p = {pv_a[2]:.1e})")
print(f"   unadjusted year beta = {beta[1]:.3f}")

### 3. Period comparison (descriptive)
print("\n3. Period comparison (descriptive)")
groups = []
for lo, hi in PERIODS:
    v = [r["sigma"] for r in rows if lo <= r["year"] <= hi]
    groups.append(v)
    m, se_ = st.mean(v), st.stdev(v) / math.sqrt(len(v))
    print(f"   {lo}-{hi}  n = {len(v):3d}  mean {m:.2f} "
          f"(95% CI {m - 1.96 * se_:.2f} to {m + 1.96 * se_:.2f})  "
          f"median {st.median(v):.0f}")
h, p = kruskal(groups)
print(f"   Kruskal-Wallis H = {h:.2f}, p = {p:.4f}")

### 4. Per-criterion trends
print("\n4. Per-criterion trend across publication year")
print(f"   {'criterion':30s}" + "".join(f"{lo}-{hi}".rjust(10) for lo, hi in PERIODS)
      + f"{'z':>7s}{'p':>9s}")
for i, label in enumerate(LABELS):
    cells = ""
    for lo, hi in PERIODS:
        sel = [r["bools"][i] for r in rows if lo <= r["year"] <= hi]
        cells += f"{round(100 * sum(sel) / len(sel)):9d}%"
    z, p = trend_z(year, [float(r["bools"][i]) for r in rows])
    tail = f"{z:7.2f}{p:9.4f}" if z is not None else f"{'-':>7s}{'-':>9s}"
    print(f"   {label:30s}{cells}{tail}")

### 5. Weighting sensitivity
print("\n5. Weighting sensitivity of the composite score")
sizes = np.array([DOMAIN.count(d) for d in DOMAIN], float)
schemes = [
    ("equal per criterion (published)", np.ones(15)),
    ("equal per domain", (15 / len(DOMAIN_NAMES)) / sizes),
    ("validation and workflow doubled",
     np.array([2.0 if DOMAIN[i] in (0, 2) else 1.0 for i in range(15)])),
]
base = B @ schemes[0][1]
for name, w in schemes:
    s = B @ w
    line = f"   {name:34s} range {s.min():.1f}-{s.max():.1f}  mean {s.mean():.2f}"
    if name != schemes[0][0]:
        rho, p = spearman(base, s)
        tau = kendall_tau(list(base), list(s))
        line += f"  vs published ranking: rho {rho:.3f}, tau {tau:.3f}"
    print(line)
print("   Equal per-criterion weighting implicitly weights the domains in proportion "
      "to how many criteria they contribute: "
      + ", ".join(f"{n} {DOMAIN.count(i)}" for i, n in enumerate(DOMAIN_NAMES)) + ".")