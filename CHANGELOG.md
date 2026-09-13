# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/) and this project adheres to [Semantic Versioning](https://semver.org/).

## [unreleased]

### Added

- None documented yet.

### Changed

- None documented yet.

### Deprecated

- None documented yet.

### Removed

- None documented yet.

### Fixed

- None documented yet.

### Security

- None documented yet.

## [1.0.0] - 2026-09-13

### Added

- `py.typed` marker and a `Typing :: Typed` classifier, so type checkers treat the package as typed when installed as a dependency.
- `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`, and `CONTRIBUTORS.md`.
- `.github/workflows/dco.yml`, enforcing Developer Certificate of Origin sign-off on pull requests via `KineticCafe/actions-dco`.
- `assets/logo.svg`, an SVG rendering of the terminal logo with a dark/light-mode-adaptive backdrop, used in the README in place of the ASCII art fenced code block (which rendered with an unwanted "copy" button).

### Changed

- **Development status promoted to GA:** `Development Status :: 5 - Production/Stable` (from `4 - Beta`). The four tools' input/output schemas are now treated as a stable public contract; breaking changes to them will be called out explicitly in this file and reflected in a major version bump.
- Upgraded `fastmcp` to `>=4.0.3`, the first non-beta release of the FastMCP 4 line (previously pinned to the beta `4.0.0b3`); see [AGENTS.md](AGENTS.md) for the updated pinning rationale.
- README now states explicitly that the server has no built-in authentication or authorization and is intended for local or otherwise trusted-network deployment only, rather than leaving this implicit.
- `CONTRIBUTING.md`'s DCO section now states sign-off is required and enforced by `dco.yml`, rather than merely encouraged.

### Deprecated

- None documented yet.

### Removed

- None documented yet.

### Fixed

- None documented yet.

### Security

- None documented yet.

## [0.3.0] - 2026-08-28

### Added

- `.github/workflows/osv-scan.yml`, wiring `google/osv-scanner-action` into CI so dependency vulnerability scanning runs automatically instead of only via `just vulnerability-scan` locally.
- CORS preflight test coverage for both allowed and disallowed origins.

### Changed

- `generate_sudoku_puzzle`'s removal loop now reuses a single solver/constraint set via `push`/`pop` instead of rebuilding the full Sudoku-rules encoding on every attempt, measurably reducing generation latency.
- `_all_units`' shadowed column-loop variable renamed from `c` to `col` for clarity; no behaviour change.

### Deprecated

- None documented yet.

### Removed

- None documented yet.

### Fixed

- `SudokuGrid.rows` is now an immutable tuple of tuples, preventing post-validation mutation (via attribute reassignment or in-place index assignment) that previously bypassed the shape/range validator.
- `_solve`/`_has_unique_solution` now raise on a genuine `z3.unknown` result instead of misclassifying it as `unsat`.
- `Cell.row`/`Cell.col` now validate `ge=1, le=9`.
- `generate_puzzle`'s invariant-violation `assert` replaced with an explicit `RuntimeError`, so it still fires under `-O`/`PYTHONOPTIMIZE`.
- `test_server.py`'s `generate_sudoku_puzzle` test now asserts against the real `_DIFFICULTY_TARGET_GIVENS` values, parametrized across all five difficulties, instead of a stale hardcoded bound.
- CORS session-id exposure fixed, and Sudoku grid cell types are now strictly validated.
- Explicit `CORSMiddleware` added for `streamable-http`, since FastMCP's `allowed_origins`/`host_origin_protection` is a request guard against spoofed `Origin`/`Host` headers, not CORS, and never emits `Access-Control-Allow-Origin` on its own.
- `host_origin_protection="auto"` enabled as defense-in-depth for the request guard, alongside the CORS fix above.

### Security

- See the CORS/request-guard fixes above: `SMT_SUDOKU_MCP_ALLOWED_ORIGINS` previously had no effect on browser CORS behaviour regardless of its value.

## [0.2.0] - 2026-08-27

### Added

- `validate_partial_sudoku_solution` now reports `empty_cells` (every still-empty cell) alongside the existing conflict/completability fields (closes [#1](https://github.com/anirbanbasu/smt-sudoku-mcp/issues/1)).

### Changed

- Simplified redundant boolean fields in Sudoku validation results.

### Deprecated

- None documented yet.

### Removed

- None documented yet.

### Fixed

- None documented yet.

### Security

- None documented yet.

## [0.1.0.post1] - 2026-08-27

### Changed

- Improved installation instructions now that the package is published on PyPI.

## [0.1.0] - 2026-08-27

### Added

- Initial release: `generate_sudoku_puzzle`, `validate_partial_sudoku_solution`, `validate_full_sudoku_solution`, and `solve_sudoku_puzzle` tools, backed by Z3's `QF_FD` finite-domain tactic.
- `stdio` and `streamable-http` transports, configurable via `SMT_SUDOKU_MCP_*` environment variables.
- Graceful exit on Ctrl+C in `streamable-http` mode.

[unreleased]: https://github.com/anirbanbasu/smt-sudoku-mcp/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/anirbanbasu/smt-sudoku-mcp/compare/v0.3.0...v1.0.0
[0.3.0]: https://github.com/anirbanbasu/smt-sudoku-mcp/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/anirbanbasu/smt-sudoku-mcp/compare/v0.1.0.post1...v0.2.0
[0.1.0.post1]: https://github.com/anirbanbasu/smt-sudoku-mcp/compare/v0.1.0...v0.1.0.post1
[0.1.0]: https://github.com/anirbanbasu/smt-sudoku-mcp/releases/tag/v0.1.0
