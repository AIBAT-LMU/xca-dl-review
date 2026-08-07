# Reproducible analysis -- deep learning in X-ray coronary angiography
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.21808800.svg)](https://doi.org/10.5281/zenodo.21808800)

Analysis code and structured data for the systematic review
**"Toward clinical-grade deep learning in coronary angiography: a systematic review."**

This repository regenerates every table and figure in the manuscript from a single
structured database. It is the analysis companion to the extraction tool
(**PaperMole**), which is published separately.

## Contents

| Path | What it is |
|------|------------|
| `xca_dl_review.db` | Structured database for all 196 included studies (SQLite), reduced to exactly what the scripts need to build the tables and figures. Three tables: `papers` (id, ref_number, pub_type, year, title, authors, doi), `extractions` (paper_id, field_name, value), `checklist_results` (paper_id, checklist_name, item_id, result). Full text, abstracts, figure captions, evidence quotes, provenance flags, file paths and author contact details have all been removed (copyright and data protection). |
| `xca_dl_review_references.bib` | Bibliography for the 196 included studies (used to build the reference list). |
| `scripts/` | Table and figure generators (`01_*`-`06_*`), shared helpers (`common.py`), and configuration (`review.toml`). |
| `scripts/paradigm_labels.json` | Precomputed supervision-type (self-/semi-/weakly-/unsupervised) labels used by `03_tab_s2.py`, since that classification originally derived from full text (now removed). |
| `results/` | Generated output (git-ignored, not committed) -- created by running the scripts: `results/tables/` (`.docx`) and `results/figures/` (`.png`/`.pdf`/`.svg`). Regenerate at any time. |
| `papermole_config/` | The exact PaperMole configuration that drove extraction and quality appraisal for this review: the XCA extraction schema, the CLAIM 2024 and QUADAS-2 checklists, and the run settings. See below. |

## Reproduce the tables and figures

Set up the environment with either [uv](https://docs.astral.sh/uv/) (fast) or plain `pip`.

**With uv:**

```bash
uv venv --python 3.11
uv pip install -r requirements.txt
```

Then run generators with `uv run` (no activation needed), e.g. `uv run python 01_tab_1.py`
from `scripts/`.

**With pip:**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

**Run the generators:**

```bash
cd scripts
python3 01_tab_1.py            # Table 1
python3 03_tab_s2.py           # Table S2
python3 05_fig4_quadas.py      # Figure 4
# ...run any 0X_tab_*.py / 0X_fig_*.py generator
```

Scripts are numbered by manuscript order. `0X_tab_*.py` write `.docx` files to
`results/tables/`; `0X_fig_*.py` write images to `results/figures/` (both created
on first run). Reference numbering (1-196) is carried in the published database
(`papers.ref_number`), which is the source of truth.

This repository contains the analysis that turns the published database into the
manuscript's tables and figures. How the database itself was curated from the raw
extraction (domain/architecture fixes, dataset normalisation, reference numbering)
is described in the manuscript Methods.

## How PaperMole was configured for this review

PaperMole is a general-purpose extraction/appraisal tool, published separately and
independent of this review. This repository carries the review-specific runtime
configuration it consumed, so the extraction is reproducible without pinning the tool
to this paper:

| File | Role |
|------|------|
| `papermole_config/extraction_schemas/xca_schema.yaml` | The XCA extraction schema -- the paper-level fields and repeat groups (dataset, model, performance) extracted from each study. |
| `papermole_config/checklists/claim_2024.yaml` | CLAIM 2024 reporting-quality checklist (44 items). |
| `papermole_config/checklists/quadas2.yaml` | QUADAS-2 risk-of-bias appraisal (signalling + applicability items). |
| `papermole_config/default.yaml` | Run settings: provider/model (a locally served Qwen model over a vLLM OpenAI-compatible endpoint, temperature 0.1, 262 144-token context), embedding model (SPECTER2), and the pointer to the schema above. `base_url`/`api_key` are placeholders overridden at runtime. |

To re-run extraction with the published tool, install PaperMole and point it at these
files (schema via `extraction.schema_file` or `--schema`; checklists via `--checklist`).
See the PaperMole repository for the tool's own usage.

## Data and code availability

- **This repository** (https://github.com/AIBAT-LMU/xca-dl-review) -- review-specific
  PaperMole configuration (`papermole_config/`), the structured extraction database,
  and all analysis code that regenerates the tables and figures. Archived at Zenodo
  (see the manuscript's Data Availability).
- **PaperMole (the tool)** (https://github.com/AIBAT-LMU/papermole) -- the general-purpose
  extraction/appraisal pipeline, published separately.

## License

- **Code** (`scripts/`, `papermole_config/`): MIT License (see `LICENSE`).
- **Dataset** (`xca_dl_review.db`): Creative Commons Attribution 4.0 International
  ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)).

If you use these materials, please cite the article and the archived Zenodo
record (see `CITATION.cff`).
