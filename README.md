[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue?logo=python&logoColor=3776ab&labelColor=e4e4e4)](https://www.python.org/downloads/release/python-3130/) [![pytest](https://github.com/anirbanbasu/smt-sudoku-mcp/actions/workflows/uv-pytest-coverage.yml/badge.svg)](https://github.com/anirbanbasu/smt-sudoku-mcp/actions/workflows/uv-pytest-coverage.yml)

```
╭─╮╭┬╮╶┬╴   ╭─╮╷ ╷╶┬╮╭─╮╷╭ ╷ ╷
╰─╮│││ │    ╰─╮│ │ │││ │├┴╮│ │
╰─╯╵ ╵ ╵    ╰─╯╰─╯╶┴╯╰─╯╵ ╵╰─╯
```

# smt-sudoku-mcp

_Now, your agents can play Sudoku confidently!_

An MCP server that demonstrates the power of satisfiability modulo theories (SMT) solving, using [Z3](https://github.com/Z3Prover/z3), through the classic constraint-satisfaction puzzle of Sudoku.

Sudoku maps cleanly onto SMT primitives: generating a puzzle means finding a model that satisfies the Sudoku constraints and then proving a reduced set of clues still has only one solution; validating a grid means checking those same constraints against given cell values; solving a puzzle means finding a model or proving none exists.

## Tools

All four tools are stateless: every call takes and/or returns a complete grid explicitly, with no server-side session state.

A Sudoku grid is represented as `{"rows": [[...9 ints...], ...9 rows...]}`, where each cell is `1`-`9` for a given digit or `0` for an empty cell. Any tool result that names a specific cell (a conflict) reports `row`/`col` as 1-indexed, matching how Sudoku cells are conventionally described in text (row 1, column 1 is the top-left cell).

### `generate_sudoku_puzzle`

Generates a new, uniquely-solvable Sudoku puzzle.

- **Input:** `difficulty` — one of `"easy"`, `"medium"`, or `"hard"` (default `"medium"`), mapping to an approximate target clue count.
- **Output:** `{"puzzle": <grid>, "difficulty": <str>, "givens": <int>}` — `givens` is the actual number of filled cells, which may be slightly above the target if removing further cells would have broken uniqueness.

### `validate_partial_sudoku_solution`

Checks whether a partially-filled grid is conflict-free and, if so, whether it can still be completed.

- **Input:** `grid` — a partial grid (0 for empty cells).
- **Output:** `{"has_conflicts": <bool>, "conflicts": [<cell>, ...], "is_completable": <bool | null>}` — `is_completable` is `null` when conflicts are present, since completability is not a meaningful question until they are resolved.

### `validate_full_sudoku_solution`

Checks whether a fully-filled grid is a correct Sudoku solution.

- **Input:** `grid` — expected to have no empty cells.
- **Output:** `{"is_valid": <bool>, "has_empty_cells": <bool>, "conflicts": [<cell>, ...]}`.

### `solve_sudoku_puzzle`

Solves an unsolved grid, or reports why it cannot be solved.

- **Input:** `grid` — a partial grid to solve (0 for empty cells).
- **Output:** `{"status": "satisfiable" | "conflicting_givens" | "unsatisfiable", "solution": <grid | null>, "conflicts": [<cell>, ...]}`. `conflicts` is only populated when `status` is `"conflicting_givens"` (two given cells directly violate a row/column/box rule); `"unsatisfiable"` means the givens are pairwise conflict-free but no completion exists.

## Installation

Requires Python 3.13+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
uv run smt-sudoku-mcp
```

## Configuration

Environment variables, all optional:

| Variable | Default | Description |
| --- | --- | --- |
| `SMT_SUDOKU_MCP_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `SMT_SUDOKU_MCP_HOST` | `127.0.0.1` | Bind host, `streamable-http` only |
| `SMT_SUDOKU_MCP_PORT` | `8000` | Bind port, `streamable-http` only |
| `SMT_SUDOKU_MCP_ALLOWED_ORIGINS` | (none) | Comma-separated browser origins to trust, `streamable-http` only |

## Development

See [AGENTS.md](AGENTS.md) for architecture notes and the full set of development commands (`just -l`).

## Contributing

Issues and pull requests are welcome.

## License

[MIT](LICENSE).
