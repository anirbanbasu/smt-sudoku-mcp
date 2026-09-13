# AGENTS.md

This file provides guidance to coding agents (Claude Code, Codex, and similar tools) when working with code in this repository.

## Project

smt-sudoku-mcp: an MCP server demonstrating SMT/Z3 constraint solving via Sudoku. Four tools: generating a puzzle, validating a partial grid, validating a full solution, and solving a puzzle (or reporting why it cannot be solved).

## Commands

`uv` manages the Python 3.13 environment — do not use `pip` directly. Commands run either via plain `uv run` or the `justfile` (`just -l` lists every recipe).

```bash
just install              # sync minimal (runtime-only) dependencies
just install-all          # sync all dependency groups (dev, test)
just format                # ruff format + ruff check --fix
just type-check             # uv run ty check
just test-coverage           # pytest (via coverage) across tests/, then coverage report
just launch-inspector        # run the MCP Inspector against the server (needs nvm/node)
just run-streamable-http      # run the server over streamable-http, for use with the Inspector
just vulnerability-scan       # osv-scanner over the source tree
just install-pre-commit-hooks / just pre-commit-update  # manage hooks via `prek`, not `pre-commit`
```

Run a single test:

```bash
uv run pytest tests/test_sudoku.py::TestSolvePuzzle::test_satisfiable -v
```

`just test-coverage` enforces `fail_under = 100` (see `[tool.coverage.report]` in `pyproject.toml`); use `# pragma: no cover` for genuinely unreachable branches rather than writing tests around them. Running a single test with plain `pytest`/`uv run pytest` skips the coverage gate, which is expected during iterative development.

Ruff (line length 120, Google-style docstrings, isort, pyupgrade, complexity ≤ 15) and `ty` are also run by pre-commit hooks (`.pre-commit-config.yaml`), installed with `prek`, not the `pre-commit` CLI.

## Architecture

### Core logic (`sudoku.py`)

`src/smt_sudoku_mcp/sudoku.py` holds the `SudokuGrid`/`Cell`/result Pydantic models and all Z3 encoding, generation, validation, and solving logic. It has no FastMCP import at all, so it can be exercised directly in tests without going through the MCP protocol. Cell coordinates are 0-indexed internally (`rows[r][c]`), but any output field that names a specific cell (e.g. `Cell`) reports 1-indexed `row`/`col`, matching how Sudoku cells are conventionally described in text.

Z3 solving uses `z3.SolverFor("QF_FD")`, not the generic `z3.Solver()` — the finite-domain tactic is roughly two orders of magnitude faster for this kind of small-domain CSP; the generic tactic took tens of seconds on a single grid in testing, where QF_FD takes tens of milliseconds. Always go through `_new_solver()` rather than instantiating `z3.Solver()` directly.

Puzzle content outcomes (conflicting givens, no completion possible) are returned as plain result fields (e.g. `SolvePuzzleResult.status`), never raised as exceptions — those are expected, informative results an LLM caller needs to reason about and relay to the user, not tool failures. Only a genuinely unexpected failure should propagate as a real exception, and FastMCP already converts any unhandled exception into an MCP tool error automatically; there is no custom exception hierarchy in this project.

### MCP server (`server.py`)

`build_server()` builds a `FastMCP` instance and registers the four tools with plain `@mcp.tool` decorators — no declarative mixin/registry layer, since four tools with no resources or prompts don't earn that abstraction's keep. `run()` picks the transport from `EnvVars.SMT_SUDOKU_MCP_TRANSPORT` and calls `FastMCP.run()` directly; there is no manual Starlette/uvicorn assembly. `FastMCP.run()`'s `allowed_origins`/`host_origin_protection` parameters are a server-side request guard against spoofed `Origin`/`Host` headers (DNS-rebinding/CSRF-style protection) — they are explicitly not CORS and never emit `Access-Control-Allow-Origin`. Actual browser CORS support is provided separately via an explicit `starlette.middleware.cors.CORSMiddleware` passed through `FastMCP.run()`'s `middleware` kwarg, which `run_http_async` (what `transport="streamable-http"` dispatches to) accepts directly — so the "no manual Starlette/uvicorn assembly" principle still holds.

This project depends on `fastmcp>=4.0.3`, the first line built on MCP Python SDK v2, which is what supports the 2026-07-28 MCP protocol revision this project targets — the older FastMCP 3.x line depends on `mcp<2.0` and cannot speak that protocol at all. FastMCP 4 was still in beta (`4.0.0b3`) when this project first adopted it, hence an exact pin at the time; FastMCP 4 left beta at `4.0.3`, so the dependency is now a floor rather than an exact pin. Still treat any FastMCP major-version bump as a deliberate, explicit change, not a routine `uv lock -U`, since a new major line can again mean a different underlying MCP SDK version.

### Configuration (`__init__.py`)

Environment variables are declared once as class attributes on `EnvVars` in `src/smt_sudoku_mcp/__init__.py`, using `environs`/`marshmallow` for typed parsing and validation (`OneOf`, `Range`). Add new environment-driven config here rather than reading `os.environ` elsewhere.

### Tests (`tests/`)

Two layers, matching the core/server split: `tests/test_sudoku.py` calls `sudoku.py`'s functions directly (no MCP involved at all). `tests/test_server.py` exercises the four tools through FastMCP's in-process `Client`/`FastMCP` pair (`async with Client(mcp) as client: await client.call_tool(...)`), which actually serialises through the MCP protocol rather than calling Python functions directly — read `result.structured_content` (a plain dict) in assertions, not `result.data` (a dynamically-typed attribute-access object). `tests/test_entrypoints.py` covers `main()`/`server.run()`'s transport-dispatch wiring by stubbing out FastMCP's actual `run()`, since that call would otherwise block starting a real server.

## Documentation

`README.md` is the complete, sole source of user-facing documentation for this project — installation, configuration, and the four tools with example calls all live there. There is no external documentation site.
