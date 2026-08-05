#!/usr/bin/env python3
"""
common.py
Shared utilities for the analysis scripts of the systematic review
"Toward clinical-grade deep learning in coronary angiography".

Provides:
  * paths (overridable via environment variables)
  * the canonical paper list, with manuscript reference numbers
  * small formatting helpers shared across tables

Manuscript metadata
-------------------
Reference numbers and publication type are owned by the Zotero library and are
imported into `papers.ref_number` and `papers.pub_type` during database
preparation, matched on DOI (Zotero's author-string ordering agrees with neither
papers.id order nor bibtex-key order). The published database already carries
this numbering and is self-contained.
"""

from __future__ import annotations

import collections
import os
import re
import sqlite3
from dataclasses import dataclass

### Configuration
# Settings resolve in this order, first hit wins:
#
#   1. an explicit argument passed to the function
#   2. an environment variable  (XCA_DB, XCA_BIB, ...)
#   3. the config file          (config/review.yaml, or $XCA_CONFIG)
#   4. the built-in default     (repo-relative, so a fresh clone just runs)
#
# Paths in the config file are resolved relative to the config file itself,
# not the working directory, so the scripts can be run from anywhere.

# YAML is the project default; TOML/JSON are accepted so the artifact keeps
# working if the file is renamed. PyYAML is imported only when a YAML config
# is actually present.
_CONFIG_NAMES = ("review.yaml", "review.yml", "review.toml", "review.json")
_HERE = os.path.dirname(os.path.abspath(__file__))


def _find_config() -> str | None:
    explicit = os.environ.get("XCA_CONFIG")
    if explicit:
        if not os.path.exists(explicit):
            raise FileNotFoundError(f"XCA_CONFIG points to {explicit!r}")
        return explicit
    for base in (_HERE, os.path.dirname(_HERE), os.getcwd()):
        for sub in ("config", ""):
            for name in _CONFIG_NAMES:
                cand = os.path.join(base, sub, name)
                if os.path.exists(cand):
                    return cand
    return None


def _read_config() -> tuple[dict, str | None]:
    path = _find_config()
    if path is None:
        return {}, None
    ext = os.path.splitext(path)[1].lower()
    if ext == ".toml":
        import tomllib
        with open(path, "rb") as fh:
            return tomllib.load(fh), path
    if ext in (".yaml", ".yml"):
        import yaml
        with open(path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}, path
    import json
    with open(path, encoding="utf-8") as fh:
        return json.load(fh), path


CONFIG, CONFIG_PATH = _read_config()
_CONFIG_DIR = os.path.dirname(os.path.abspath(CONFIG_PATH)) if CONFIG_PATH else None


def setting(*keys, env: str | None = None, default=None):
    """Look up a config value by nested key, with environment override."""
    if env and os.environ.get(env):
        return os.environ[env]
    node = CONFIG
    for k in keys:
        if not isinstance(node, dict) or k not in node:
            return default
        node = node[k]
    return node


def _path(key: str, env: str, default: str) -> str:
    if os.environ.get(env):
        return os.environ[env]
    val = setting("paths", key)
    if val is None:
        return default
    if os.path.isabs(val):
        return val
    return os.path.normpath(os.path.join(_CONFIG_DIR, val))


DB_PATH = _path("db", "XCA_DB", "xca_dl_review.db")
BIB_PATH = _path("bib", "XCA_BIB", "xca_dl_review_references.bib")
OUT_TABLES = _path("tables", "XCA_TABLES", os.path.join(os.path.dirname(_HERE), "results", "tables"))
OUT_FIGURES = _path("figures", "XCA_FIGURES", os.path.join(os.path.dirname(_HERE), "results", "figures"))

# Analysis parameters that are editorial choices rather than data.
FIRST_REF = int(setting("references", "start", env="XCA_FIRST_REF", default=21))
PERIODS = [tuple(p) for p in setting(
    "table1", "periods", default=[[2016, 2019], [2020, 2022], [2023, 2026]])]


def describe_config() -> str:
    src = CONFIG_PATH or "built-in defaults (no config file found)"
    return (f"config: {src}\n"
            f"  db      {DB_PATH}\n"
            f"  bib     {BIB_PATH}\n"
            f"  tables  {OUT_TABLES}\n"
            f"  figures {OUT_FIGURES}")


# Values that mean "the paper did not report this".
NOT_REPORTED = {"", "not_reported", "not reported", "n/a", "na", "none", "unclear"}


def normalise_doi(doi: str) -> str:
    """Lowercase, strip any resolver prefix and trailing punctuation."""
    doi = (doi or "").strip().lower()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi)
    return doi.rstrip(" .,;")


### Bib parsing
@dataclass(frozen=True)
class Paper:
    paper_id: int          # papers.id in the database
    ref: int               # manuscript reference number (papers.ref_number)
    pub_type: str          # 'journal' | 'conference'
    year: int
    title: str
    first_author: str

    @property
    def is_journal(self) -> bool:
        return self.pub_type == "journal"


def _fold(s: str) -> str:
    """
    Punctuation-insensitive key for cross-checking identifiers.

    Note: bibtex keys drop non-ASCII letters outright rather than
    transliterating them (Akgül -> Akgl), so folding must discard them too
    rather than decompose them (which would give 'akgul').
    """
    return re.sub(r"[^a-z0-9]", "", s.lower())


def parse_bib(bib_path: str = BIB_PATH) -> list[tuple[str, str, int]]:
    """Return [(entry_type, key, year), ...] in file order."""
    text = open(bib_path, encoding="utf-8").read()
    out = []
    for block in re.finditer(r"@(\w+)\{([^,]+),(.*?)\n\}", text, re.S):
        etype, key, body = block.group(1).lower(), block.group(2).strip(), block.group(3)
        m = re.search(r"\byear\s*=\s*\{(\d{4})\}", body)
        out.append((etype, key, int(m.group(1)) if m else 0))
    return out


def connect(db_path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def load_papers(conn: sqlite3.Connection | None = None) -> list[Paper]:
    """
    The canonical list of included studies, ordered by reference number.

    Reads only the database, which already carries papers.ref_number and
    papers.pub_type.
    """
    own = conn is None
    conn = conn or connect()

    cols = {r[1] for r in conn.execute("PRAGMA table_info(papers)")}
    for col in ("ref_number", "pub_type"):
        if col not in cols:
            raise AssertionError(
                f"papers.{col} is missing from the published database")

    rows = conn.execute(
        "SELECT id, ref_number, pub_type, year, title, authors "
        "FROM papers ORDER BY ref_number"
    ).fetchall()

    papers = []
    for row in rows:
        if row["ref_number"] is None or not row["pub_type"]:
            raise AssertionError(
                f"papers.id={row['id']} is missing manuscript metadata "
                "in the published database")
        first = re.sub(r'^\[?"?', "", (row["authors"] or "").split(",")[0]).strip(' "[]')
        papers.append(Paper(
            paper_id=row["id"],
            ref=row["ref_number"],
            pub_type=row["pub_type"],
            year=row["year"],
            title=row["title"],
            first_author=first.split()[-1] if first.split() else "?",
        ))

    refs = [p.ref for p in papers]
    if len(set(refs)) != len(refs):
        raise AssertionError("duplicate ref_number values in papers")

    if own:
        conn.close()
    return papers


### Application domains
# The extraction vocabulary (field_of_application) has 17 values; the
# manuscript reports six top-level domains. This mapping is the single source
# of truth for both Figure 2 and Table S1, so the figure and the table cannot
# drift apart.
#
# "Coronary dominance classification" was added to the original 16-value
# vocabulary during manual adjudication; it is a
# patient-level anatomical classification with no home among the original
# categories and is aggregated under Classification.
#
# Note that "Keyframe/frame selection" sits under Image processing, whereas
# earlier versions of the schema placed frame selection under Other detection.

DOMAIN_MAP = {
    "Binary vessel extraction":               "Vessel segmentation",
    "Semantic vessel labeling":               "Vessel segmentation",
    "Stenosis detection":                     "Stenosis detection",
    "Lesion classification":                  "Classification",
    "View/angle classification":              "Classification",
    "Coronary dominance classification":      "Classification",
    "Functional significance classification": "Classification",
    "Lesion detection (non-stenosis)":        "Other detection",
    "Anatomical detection":                   "Other detection",
    "Abnormality screening":                  "Other detection",
    "Keyframe/frame selection":               "Image processing",
    "Enhancement/denoising":                  "Image processing",
    "Image matching/registration":            "Image processing",
    "3D reconstruction":                      "Image processing",
    "Stenosis quantification":                "Quantification",
    "FFR/iFR prediction":                     "Quantification",
    "Other":                                  "Other",
}

# Display order for the figure and the table.
DOMAIN_ORDER = ["Vessel segmentation", "Stenosis detection", "Classification",
                "Other detection", "Image processing", "Quantification"]

SUBDOMAIN_ORDER = {
    "Vessel segmentation": ["Binary vessel extraction", "Semantic vessel labeling"],
    "Stenosis detection":  ["Stenosis detection"],
    "Classification":      ["Lesion classification", "View/angle classification",
                            "Coronary dominance classification",
                            "Functional significance classification"],
    "Other detection":     ["Lesion detection (non-stenosis)", "Anatomical detection",
                            "Abnormality screening"],
    "Image processing":    ["Keyframe/frame selection", "Enhancement/denoising",
                            "Image matching/registration", "3D reconstruction"],
    "Quantification":      ["Stenosis quantification", "FFR/iFR prediction"],
}

DOMAIN_COLORS = {
    "Vessel segmentation": "#4285F4",
    "Stenosis detection":  "#EA4335",
    "Classification":      "#A142F4",
    "Other detection":     "#34A853",
    "Image processing":    "#FF6D01",
    "Quantification":      "#46BDC6",
}


# The three algorithm classes recorded in extractions.algorithm_type.
ALGORITHM_CLASSES = ("Deep Learning", "Classical ML", "Non-ML")


def models_by_algorithm(conn, papers, algorithm="Deep Learning"):
    """
    Model indices of a given algorithm class, as {paper_id: [index, ...]}.

    algorithm_type was split into three classes during database preparation;
    before that it lumped classical image processing together with classical
    machine learning and mislabelled seven neural networks, so a single-field
    filter was not safe. It is now, and every deep-learning model carries a
    base_architecture.
    """
    if algorithm not in ALGORITHM_CLASSES:
        raise ValueError(f"unknown algorithm class {algorithm!r}")
    ids = {p.paper_id for p in papers}
    out = {}
    for pid, field, value in conn.execute(
            "SELECT paper_id, field_name, value FROM extractions "
            "WHERE field_name LIKE 'algorithm_type__%' AND value = ?",
            (algorithm,)):
        if pid in ids:
            idx = int(re.search(r"__(\d+)$", field).group(1))
            out.setdefault(pid, []).append(idx)
    return {pid: sorted(v) for pid, v in out.items()}


def deep_learning_models(conn, papers):
    """Model indices of the deep-learning models, as {paper_id: [index, ...]}."""
    return models_by_algorithm(conn, papers, "Deep Learning")


# Roles that never represent a study's contribution in their own right.
EXCLUDED_ROLES = {"Ablation"}


def primary_models(conn, papers):
    """
    The models that carry each study's contribution, as {paper_id: [index, ...]}.

    A study is represented by its proposed deep-learning models. Ten studies
    propose nothing - benchmark comparisons, dataset papers and preprocessing
    evaluations assess existing architectures rather than introducing one - and
    are represented by their remaining deep-learning models instead, so that
    model-level tables cover the whole corpus rather than silently favouring
    studies that introduce new architectures.

    Ablations are excluded throughout: they are variants of a study's own model
    and would count the same architecture several times over.
    """
    ids = {p.paper_id for p in papers}
    role, algo = {}, {}
    for pid, field, value in conn.execute(
            "SELECT paper_id, field_name, value FROM extractions "
            "WHERE (field_name LIKE 'model_role__%' "
            "       OR field_name LIKE 'algorithm_type__%') "
            "AND value IS NOT NULL AND value != ''"):
        if pid not in ids:
            continue
        idx = int(re.search(r"__(\d+)$", field).group(1))
        (role if field.startswith("model_role") else algo)[(pid, idx)] = value.strip()

    candidates = {}
    for key, a in algo.items():
        if a == "Deep Learning" and role.get(key) not in EXCLUDED_ROLES:
            candidates.setdefault(key[0], []).append(key[1])

    out = {}
    for pid, idxs in candidates.items():
        proposed = [i for i in idxs if role.get((pid, i)) == "Proposed"]
        out[pid] = sorted(proposed or idxs)
    return out


def application_domains(conn, papers):
    """
    Index studies by application domain and sub-domain.

    Returns (by_domain, by_subdomain), both {name: set(paper_id)}. A study
    counts once per domain however many of its models address it. "Other" is
    excluded: it marks models that fall outside the vocabulary (non-DL
    baselines, image synthesis) and is never reported as a domain.
    """
    ids = {p.paper_id for p in papers}
    by_domain, by_sub = {}, {}
    for pid, value in conn.execute(
            "SELECT paper_id, value FROM extractions "
            "WHERE field_name LIKE 'field_of_application__%' "
            "AND value IS NOT NULL AND value != ''"):
        if pid not in ids:
            continue
        value = value.strip()
        if value not in DOMAIN_MAP:
            raise AssertionError(
                f"field_of_application '{value}' is not in DOMAIN_MAP "
                "- the extraction vocabulary has changed")
        if value == "Other":
            continue
        by_domain.setdefault(DOMAIN_MAP[value], set()).add(pid)
        by_sub.setdefault(value, set()).add(pid)
    return by_domain, by_sub


def domains_per_paper(by_domain, papers):
    """{paper_id: set(domain)} for every study, including any with none."""
    out = {p.paper_id: set() for p in papers}
    for domain, pids in by_domain.items():
        for pid in pids:
            out[pid].add(domain)
    return out


ModelRow = collections.namedtuple(
    "ModelRow",
    "paper_id ref idx field_of_application domain base_architecture "
    "architecture_family model_role")


def primary_model_rows(conn, papers):
    """
    One tuple per primary model (see primary_models), carrying that model's OWN
    per-model fields joined by index.

    Use this for ANY cross-tabulation of application domain against another
    per-model field. application_domains() returns {domain: {paper_id}} and
    discards the model index by design, so intersecting its output with a second
    pre-aggregated {property: {paper_id}} set counts studies that have both
    properties on DIFFERENT models -- a spurious cross-product. Reading
    field_of_application__N and X__N for the SAME N (as this helper does) is the
    only join that asserts one model has both.

    `domain` is DOMAIN_MAP[field_of_application], or None when the model's
    application is "Other" or empty (never reported as a domain). A value outside
    the vocabulary raises, matching application_domains().
    """
    ids = {p.paper_id for p in papers}
    ref_of = {p.paper_id: p.ref for p in papers}
    primary = primary_models(conn, papers)

    wanted = ("field_of_application", "base_architecture",
              "architecture_family", "model_role")
    clause = " OR ".join(f"field_name LIKE '{f}\\_\\_%' ESCAPE '\\'" for f in wanted)
    data = {}  # (paper_id, idx, base_field) -> value
    for pid, field, value in conn.execute(
            f"SELECT paper_id, field_name, value FROM extractions WHERE ({clause}) "
            "AND value IS NOT NULL AND value != ''"):
        if pid not in ids:
            continue
        m = re.match(r"(.+)__(\d+)$", field)
        data[(pid, int(m.group(2)), m.group(1))] = value.strip()

    rows = []
    for pid, idxs in primary.items():
        for idx in idxs:
            foa = data.get((pid, idx, "field_of_application"), "")
            if foa and foa not in DOMAIN_MAP:
                raise AssertionError(
                    f"field_of_application '{foa}' is not in DOMAIN_MAP "
                    "- the extraction vocabulary has changed")
            domain = DOMAIN_MAP.get(foa)
            if domain == "Other":
                domain = None
            rows.append(ModelRow(
                pid, ref_of[pid], idx, foa, domain,
                data.get((pid, idx, "base_architecture"), ""),
                data.get((pid, idx, "architecture_family"), ""),
                data.get((pid, idx, "model_role"), "")))
    return rows


### Extraction access
def scalar(conn, paper_id: int, field: str) -> str:
    """Value of a single-valued extraction field ('' if absent)."""
    r = conn.execute(
        "SELECT value FROM extractions WHERE paper_id=? AND field_name=?",
        (paper_id, field),
    ).fetchone()
    return (r["value"] or "").strip() if r else ""


def repeated(conn, paper_id: int, field_base: str) -> list[str]:
    """
    Values of a repeated extraction field, e.g. 'dataset_size_samples' returns
    every dataset_size_samples__1..N for that paper, in index order.
    """
    rows = conn.execute(
        "SELECT field_name, value FROM extractions "
        "WHERE paper_id=? AND field_name LIKE ? ESCAPE '\\' "
        "AND value IS NOT NULL AND value!=''",
        (paper_id, field_base + "\\_\\_%"),
    ).fetchall()
    def idx(name):
        m = re.search(r"__(\d+)$", name)
        return int(m.group(1)) if m else 0
    return [r["value"].strip() for r in sorted(rows, key=lambda r: idx(r["field_name"]))]


def is_reported(value: str) -> bool:
    return value.strip().lower() not in NOT_REPORTED


### Formatting
def pct(n: int, total: int) -> int:
    return round(100 * n / total) if total else 0


def fmt(n: int, total: int) -> str:
    return f"{n} ({pct(n, total)}%)"


def ref_ranges(refs) -> str:
    """Compress [20,21,22,25,26] -> '20-22, 25-26' (en dashes)."""
    refs = sorted(set(refs))
    if not refs:
        return "\u2014"
    out, start, end = [], refs[0], refs[0]
    for r in refs[1:]:
        if r == end + 1:
            end = r
        else:
            out.append(f"{start}\u2013{end}" if start != end else str(start))
            start = end = r
    out.append(f"{start}\u2013{end}" if start != end else str(start))
    return ", ".join(out)


def ensure_dirs():
    os.makedirs(OUT_TABLES, exist_ok=True)
    os.makedirs(OUT_FIGURES, exist_ok=True)