# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`kp` is a **uv workspace** monorepo holding several unrelated Python 3.13 projects. The root
package (`src/kp`) is an empty placeholder — all real code lives in the workspace members declared
in the root `pyproject.toml`:

| Member | Kind | Entry point | Purpose |
| --- | --- | --- | --- |
| `vps/server` | FastAPI (port 8888) | `server.app:main` | Voxio scenario CRUD: Gemini generates a scenario prompt, injects it into a workflow JSON, POSTs/PUTs it to `database.voxio.in`, mirrors it in MongoDB |
| `vps/posta` | FastAPI (port 8000) | `posta.app:main` | Post-session hook: decrypts a JWE header token, pulls session data from `chat.voxio.in`, writes a session doc and back-links it onto the student and scenario docs |
| `benchmarking/vpsb/postab` | Streamlit | `postab:main` | Trivial manual tester for `posta` — paste a JWE token, POST it at the URL in `config.yml` |
| `retail/rpoc` | Streamlit | `rpoc:main` | Large retail price/PO app for Tian Ma Group. **Has its own `CLAUDE.md` — read it before touching this subtree.** |
| `retail/mt` | FastAPI (port 9999) | `mt.app:main` | Skeleton webhook receiver; only logs request bodies |
| `services` | library | — | Shared helpers imported as `from services import ...` by `posta` and `mt` |

## Commands

```bash
uv sync                       # install the whole workspace from the root
uv run <script>               # server | posta | postab | rpoc | mt
```

**Always run a member from its own directory**, not the repo root: every app loads `config.yml`,
`assets/…` and prompt files by relative path (`open('config.yml')`), so the CWD must be the member
dir. E.g. `cd vps/server && uv run server`.

There are no tests, linter, or formatter configured anywhere in this repo.

Each app calls `load_dotenv()` and reads a `.env` in its own directory. Env vars in use:
`MONGO_URL`, `GEMINI_API_KEY`, `DEEPGRAM_API_KEY`, `VOXIO_API_KEY`, `ALLOWED_ORIGINS`,
`ALLOWED_CREDENTIALS`, `ALLOWED_METHODS`, `ALLOWED_HEADERS` (server); `MONGO_URL`, `JWE_SECRET`
(posta). `rpoc` additionally needs `GROQ_API_KEY`.

Note `retail/rpoc` carries its own `uv.lock` and is also usable standalone; the root `uv.lock`
covers the workspace.

## Shared architectural pattern

The FastAPI members are deliberately near-identical in shape — copy that shape when adding one:

1. `state_.py` / `state/` defines a plain `AppState` class of typed attributes (config, logger,
   clients, Mongo collections).
2. `loader/` has one `load_*` function per external client plus a `load_all_clients()` /
   `load_clients()` that returns them as a tuple.
3. `app.py` wires them in an `asynccontextmanager` `lifespan`, assigns them onto a module-level
   `state` singleton, adds permissive CORS, defines routes inline, and exposes
   `def main() : uvicorn.run(app, host='0.0.0.0', port=…)`.
4. Routes stay thin-ish; heavier logic goes in `routers/`, `llm/`, `services/`.

`config.yml` (never checked-in secrets) holds per-feature sub-dicts — prompt paths, model names,
Mongo database/collection names, logger colors — and is passed down as `config['<feature>']`
rather than read again deeper in the stack.

**`services/` is the intended home for shared code, but is only partly adopted.** `vps/server`
still carries its own private copies of `load_config`, `load_logger`, `ColoredFormatter`,
`env_str_to_bool`, `env_str_to_list` in `loader/loader.py` and `services/`, while `posta` and `mt`
import them from `services`. Also note `services.load_logger` is currently gutted — its body is
commented out and it returns a bare unconfigured logger, so log formatting there differs from
`server`'s working copy.

## Conventions

- **Idiosyncratic code style, used consistently across every member**: spaces around colons in
  annotations and dict literals (`key : value`, `x : int`), one-argument-per-line call sites with
  the trailing ` , `, single-line `if cond : return x` bodies, and one-line
  `def f() : do_thing()`. Match it.
- Trailing-underscore module names (`state_.py`, `logger_.py`, `general_.py`, `services_.py`) mark
  the implementation file inside a package directory; the package `__init__.py` re-exports with
  `from .x_ import *`.
- Comment markers in use: `# *` for explanatory notes, `# !` for TODO/warning.
- Type hints are used on signatures and even on local variables (`config : dict = ...`).

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
