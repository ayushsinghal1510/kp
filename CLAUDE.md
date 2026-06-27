# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Structure

This is a **uv workspace** (Python 3.13) with six sub-projects:

```
kp/
├── vps/
│   ├── server/      # FastAPI – scenario creation/editing backend (port 8888)
│   └── posta/       # FastAPI – student session/data backend (port 8000)
├── retail/
│   ├── rpoc/        # Streamlit – retail price & order management app
│   └── mt/          # Thin package; depends on services
├── benchmarking/
│   └── vpsb/postab/ # Streamlit – API testing tool for posta
└── services/        # Shared utility library (used by posta and mt)
```

## Commands

All commands must be run from the relevant sub-project directory (where `pyproject.toml` lives).

```bash
# Install workspace dependencies (from repo root)
uv sync

# Run vps/server (FastAPI on :8888)
cd vps/server && uv run server

# Run vps/posta (FastAPI on :8000)
cd vps/posta && uv run posta

# Run retail/rpoc (Streamlit)
cd retail/rpoc && uv run streamlit run src/rpoc/app.py

# Run benchmarking/vpsb/postab (Streamlit)
cd benchmarking/vpsb/postab && uv run streamlit run src/postab/app.py

# Add a dependency to a specific workspace member
uv add <package> --package <member-name>
```

There are no test suites or linters configured in any sub-project.

## Architecture

### vps/server

FastAPI app that generates and edits AI "scenarios" (voice-call training scripts). On startup it loads a Gemini client, Deepgram client, and MongoDB client into a shared `AppState` singleton.

- **`/add-scenario`** – calls Gemini (configured model in `config.yml`) to generate a scenario JSON, then POSTs it to the Voxio external API (`database.voxio.in/flow`) and stores the result in MongoDB.
- **`/edit-scenario`** – fetches an existing flow from Voxio, regenerates via Gemini, PUTs the update back, and syncs MongoDB.
- LLM calls go through `llm/runner.py`: `run_json_gemini` streams Gemini output, parses JSON with `ast.literal_eval`, and retries once on parse failure.
- CORS origins/methods/headers are read from env vars (`ALLOWED_ORIGINS`, etc.).
- Required env vars: `DEEPGRAM_API_KEY`, `GEMINI_API_KEY`, `MONGODB_URI`, `VOXIO_API_KEY`, `ALLOWED_ORIGINS`, `ALLOWED_CREDENTIALS`, `ALLOWED_METHODS`, `ALLOWED_HEADERS`.

### vps/posta

FastAPI app for the student-facing dashboard backend. Receives a JWE-encrypted token, decrypts it with `JWE_SECRET`, fetches session data from `chat.voxio.in`, then writes transcriptions/scores/feedback into MongoDB across three collections: `students`, `scenarios`, `sessions`.

- Required env vars: `JWE_SECRET`, `MONGODB_URI` (and any others in `vps/posta/.env`).

### retail/rpoc

Multi-page Streamlit app for a retail business. All state is managed via `st.session_state`, initialized once in `services/state_.py:load_session_state()`.

Pages (defined in `app.py`):
- **Master List** – upload supplier Excel/CSV/PDF/image files; displays and manages the master product list
- **Chatbot** – LLM-powered chat using Groq (`llama-3.3-70b-versatile`) for review/coder tasks and Gemini for ingestion
- **Ordering Lists** – create and manage purchase order lists from uploaded PO images
- **Order Management** – manage active orders
- **Financial Purchases** – track purchase history

Key data flows:
- Master product data lives in `assets/data/data5.csv` (path configured in `config.yml`)
- Ordering lists and purchases are persisted to JSON files under `assets/jsons/`
- LLM prompts are loaded from markdown files under `assets/prompts/` (paths in `config.yml`)
- The app uses **Polars** (`pl.DataFrame`) for the master list and **Pandas** where needed
- Required env vars: `GROQ_API_KEY`, `GEMINI_API_KEY` (in `retail/rpoc/.env`)
- Must be launched from the `retail/rpoc/` directory because `config.yml` is opened with a relative path

### services

Shared library providing `env_str_to_bool` and `env_str_to_list` helpers (used by `vps/server` and `vps/posta`) plus common utilities. Referenced as a workspace dependency in `posta` and `mt`.

### benchmarking/vpsb/postab

Simple Streamlit UI for testing the `posta` `/session` endpoint. Accepts a JWE token via text input and POSTs it to the URL configured in `config.yml`.

## Configuration Pattern

Every sub-project uses a `config.yml` in its root directory, loaded at startup with `yaml.safe_load`. Paths inside configs are relative to the sub-project directory. Secrets are in `.env` files loaded via `python-dotenv`.
