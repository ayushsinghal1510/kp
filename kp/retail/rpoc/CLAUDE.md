# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`rpoc` is a Streamlit multi-page app for **Tian Ma Group Holdings** that manages a retail
price/product master list, ingests supplier price lists and purchase-order images via LLMs, and
compiles purchase orders with cost/profit metrics into branded PDF/Excel documents. There is **no
database** — all state persists to JSON/CSV files under `assets/`.

## Commands

```bash
uv sync                                   # install dependencies (Python >=3.13, uv build backend)
uv run rpoc                               # run the app (calls `streamlit run src/rpoc/app.py`)
uv run streamlit run src/rpoc/app.py      # equivalent, run directly
```

**Always run from the repo root.** `config.yml`, `assets/…`, and the persisted CSV/JSON paths are
all resolved relative to the current working directory, not to the source files.

Requires a `.env` (loaded by `python-dotenv` in `app.py`) with:
- `GROQ_API_KEY` — Groq (chat/vision/code agent)
- `GEMINI_API_KEY` — Google Gemini (document ingestion)

There are no tests, linter, or formatter configured in this repo.

## Architecture

**Config- and state-driven.** `config.yml` is loaded into `st.session_state.config`, and
`load_session_state()` (`src/rpoc/services/state_.py`) bootstraps *all* shared state on startup:
the Groq and Gemini clients, config sub-sections, prompt texts (from `assets/prompts/*.md`), the
master DataFrame (`st.session_state.df`, a **polars** frame read from `assets/data/data5.csv`), and
the `ordering_lists` / `purchases` lists loaded from JSON. Almost everything reads and writes
`st.session_state.*` — treat it as the app's global store. When changing data shapes, update both
`config.yml` (`main.columns`) and `root_csv_columns` in `state_.py`; they can drift.

**Page layout.** `app.py` registers pages with `st.navigation`. Each feature lives in
`src/rpoc/pages_/<feature>/` with a page file named `<x>page.py` (`mlpage`, `chpage`, `opage`,
`ppage`, `olpage`) plus a `services_.py`/`services.py` holding its logic; nested features go under
`subpages/`. Note the trailing-underscore naming convention used throughout: the `pages_/`
directory and modules like `services_`, `state_`, `general_`, `pdf_`, `excel_`.

**Two LLM providers, distinct roles:**
- **Google Gemini** (`gemini-2.5-flash`, with Google Search tool) — extracts structured product
  data from uploaded supplier price lists (Excel/PDF/Word/image/text) in the Master List flow.
  See `pages_/master_list/subpages/po_upload/services_.py`.
- **Groq** — vision (`llama-4-scout`) to parse PO *images* into order JSON
  (`pages_/ordering_lists/services_.py`); and the chatbot's code agent (`llama-3.3-70b`).

**The chatbot is a self-correcting data agent** (`pages_/chatbot/chatbot_.py`): the coder LLM emits
polars code against `st.session_state.df`, `execute_code()` (`pages_/chatbot/services_.py`) runs it
with `exec()`, mutates the df **and persists it back to the CSV**, then a reviewer LLM returns
`SUCCESS:`/`RETRY` (up to 3 attempts). Be aware this executes model-generated code and overwrites
the master CSV on success.

**Core domain flows:**
1. **Master List** (`mlpage`) — upload supplier price lists → Gemini extracts + dedups products →
   approval step → appended to the master df.
2. **Ordering Lists** (`olpage`) — upload PO images → Groq vision → stored in
   `assets/jsons/ordering_lists.json`.
3. **Order Management** (`opage`) — select ordering lists → compile: for each product pick the
   **cheapest supplier** from the master df, compute cost/GST/profit metrics
   (`orders/compile_ol/services.py`, `calculate_purchase_metrics`) → append to
   `assets/jsons/purchases.json`, advance the PO counter in `assets/jsons/po.json`, and record the
   product→vendor mapping in `previous_vendors.json`.
4. **Financial Purchases** (`ppage`) — review/manage generated purchases and export.

**Document generation.** `services/pdf_.py` (`build_tmg_pdf`) and `services/excel_.py`
(`build_tmg_excel`) produce the branded purchase-order document. Both share the same column
blueprint with four optional, color-coded sections toggled by `include_wogst / include_wgst /
include_base / include_promo`: base cost (W/O GST), cost with GST (green), base profit (blue),
discount/promo profit (orange). The `item_val` MAP in each maps blueprint keys to DataFrame column
names — keep the two files in sync when changing columns.

## Conventions

- **Code style is idiosyncratic**: spaces around colons in annotations/dicts (`key : value`,
  `x : int`), and function calls/args frequently exploded one-per-line. Match the surrounding style.
- Helpers like `safe_str` / `safe_num` are intentionally duplicated across `services/`, `pdf_.py`,
  and `excel_.py`; there is no single shared utils module for these.
