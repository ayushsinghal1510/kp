# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

`kp` is a **uv workspace monorepo** (Python ≥ 3.13, `uv_build` backend) bundling several independent apps for two domains plus a shared library. The root package itself is a stub; real code lives in the workspace members declared in `pyproject.toml`:

| Member                     | Kind      | Purpose                                                                                                                                                               | Port |
| -------------------------- | --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| `vps/server`               | FastAPI   | Voice scenario creation/editing — Gemini generates a scenario prompt, pushes a workflow to the Voxio API (`database.voxio.in`), persists to MongoDB.                  | 8888 |
| `vps/posta`                | FastAPI   | Decrypts a JWE session token, pulls session data from Voxio chat API, writes transcription/feedback/score back into MongoDB (`students`/`scenarios`/`sessions`).      | 8000 |
| `retail/rpoc`              | Streamlit | Retail purchase-order / master-list app: upload supplier price lists & PO images, an LLM "data agent" chatbot, ordering lists, orders, purchases. The largest member. | 8501 |
| `retail/mt`                | Streamlit | Tiny utility to POST a JWE token to a configured URL and view the response.                                                                                           | —    |
| `benchmarking/vpsb/postab` | FastAPI   | Benchmarking stub for posta (echoes posted JSON).                                                                                                                     | 9999 |
| `services`                 | Library   | Shared code: colored logger, env-string parsers, Gemini chat helpers. Imported as `from services import ...`.                                                         | —    |

`vps/*` (Voice Practice/Scenario) and `retail/*` are unrelated product lines that happen to share this repo and the `services` package.

## Running

Each member must be run **from its own directory** — `config.yml` and all `assets/` paths in the code are relative to the member root (see the `nohup.out` error from running rpoc at the repo root).

```sh
# FastAPI members (entry points defined in their pyproject [project.scripts])
cd vps/server && uv run server     # also: posta, postab
cd vps/posta  && uv run posta

# Streamlit members (no usable main(); launch the app module directly)
cd retail/rpoc && uv run streamlit run src/rpoc/app.py
cd retail/mt   && uv run streamlit run src/mt/app.py
```

`uv sync` resolves the whole workspace from the root `uv.lock`. There is **no test suite, linter, or formatter** configured.

## Configuration & secrets

- Every app calls `load_dotenv()` and reads secrets directly from `os.environ` (e.g. `GROQ_API_KEY`, `GEMINI_API_KEY`, `DEEPGRAM_API_KEY`, `MONGO_URL`, `VOXIO_API_KEY`, `JWE_SECRET`, CORS `ALLOWED_*`). Missing keys crash at startup/import. `.env` files are gitignored.
- Non-secret settings live in each member's `config.yml` (loaded via `yaml.safe_load`): model names, prompt/asset paths, MongoDB db/collection names, Streamlit widget kwargs. Prompts are markdown files under `assets/prompts/` and are read at load time.

## Architecture notes

**`services` shared package** — Members that depend on it declare `services = { workspace = true }` under `[tool.uv.sources]` and import top-level names (`load_config`, `load_logger`, `env_str_to_list`, `env_str_to_bool`, `json_to_google_chat`, `create_generation_config`). Note `vps/server` carries its **own copy** of these helpers (in `src/server/services/` and `src/server/loader/`) rather than depending on the `services` package — keep the two in sync if you touch shared logic.

**FastAPI members** follow one shape: a `loader/` builds all external clients (Mongo, Gemini, Deepgram) + logger + config and returns them as a tuple; an `AppState` holds them; a `lifespan` async context manager populates `AppState` on startup; route handlers live in `routers/` (server) or inline in `app.py` (posta). Gemini calls go through `llm/runner.py`: `run_json_gemini` streams text then strips ` ``` ` / `json` fences and `ast.literal_eval`s it into a dict, retrying once and falling back to a canned error dict — so prompts must return Python-literal-parseable JSON-ish text, not strict JSON.

**`retail/rpoc`** is a multi-page Streamlit app. `app.py` wires `st.navigation` over the `src/rpoc/pages_/` tree (master*list, chatbot, ordering_lists, orders, purchase), each page folder using a `page.py` + `services*.py`split. All state is bootstrapped once by`load*session_state()` (`services/state*.py`) into `st.session_state`— clients, parsed config sections, prompt strings, and the working **Polars** DataFrame loaded from the CSV at`config['main']['path']['csv']`.

The chatbot (`pages_/chatbot/chatbot_.py`) is a **coder→reviewer retry loop**: a Groq LLM (`coder` prompt) emits a ` ```python ` block of Polars code; `execute_code` (`services/services_.py`) `exec()`s it with `df` in scope, writes the mutated `df` back to the CSV, and a second Groq call (`review` prompt) returns `SUCCESS:`/`RETRY` to decide whether to accept or retry (max 3). Fuzzy product-name matching seeds hints into the coder prompt. Editing the LLM behavior means editing the markdown prompts in `assets/prompts/`, not Python.

## Code style

The codebase has a distinctive, consistent style — match it: spaces around `:` and `=` even in annotations/calls (`def f(x : int = 0)`), heavy explicit type annotations, and one-liner `if cond : ...` / `else : ...` and single-expression function bodies on the same line. Mirror the surrounding file rather than reformatting to PEP 8.

# Writitng convention :

You are an expert Python developer who writes code adhering to a highly specific, custom formatting style. You must completely ignore standard PEP8, Black, or Ruff formatting rules and strictly follow the structural and spacing rules outlined below.

### CORE PHILOSOPHY

Your code must be visually "airy" and spacious. Every piece of punctuation (colons, commas) must be padded with spaces to separate them from the text. not the start and end of the parenthesis and brackets

### THE STRICT FORMATTING RULES:

1. SPACING AROUND PUNCTUATION:
   - Commas: MUST have a space before AND after them (e.g., `item1 , item2`).
   - Colons: MUST have a space before AND after them in ALL contexts (type hints, dictionaries, if-statements, function definitions).
     - Correct: `data : dict` | `if condition :` | `'key' : value`

2. QUOTES:
   - Use strictly single quotes (`'`) for all strings, dictionary keys, and string literals, unless an f-string specifically requires double quotes to avoid escaping.

3. TYPE ANNOTATIONS:
   - You must annotate everything possible. Every function argument, return type, and variable assignment should have a type hint where logical.
   - Use modern union syntax (e.g., `dict | None`).
   - Format: `variable_name : type = value`

4. FUNCTION DEFINITIONS & CALLS:
   - Multi-line arguments must have the opening parenthesis `(` on the first line.
   - Each argument gets its own line, indented by 4 spaces.
   - Commas separating arguments must be placed at the end of the line, preceded by a space (e.g., `request : Request ,`).
   - The closing parenthesis `)` goes on its own line.
   - The ending colon `:` must have a space before it.

5. DICTIONARIES:
   - Keys and values must be separated by spaces around the colon.
   - Commas must have a space before them.
   - Correct: `{'key' : 'value' , 'key2' : 'value2'}`

### EXAMPLE OF EXPECTED OUTPUT:

@router.post('')
async def add_flow(
user_input : NumberAddRequest ,
user_api_key : str = Header(... , alias = 'user_api_key') ,
db = Depends(get_db)
) :

    user_data : dict | None = db.find_user_by_api_key(user_api_key)

    if not user_data :
        raise HTTPException(
            status_code = 401 ,
            detail = 'Invalid user API key'
        )

    _ , inserted_document = db.add_user(
        user_input.phone_number ,
        user_api_key
    )

    return NumberAddResponse(
        status = 'success' ,
        message = 'number associated successfully'
    )

Failure to include spaces before colons and commas is considered a critical error. Ensure your output perfectly mimics the spacing in the example above.
