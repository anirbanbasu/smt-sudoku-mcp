"""Sudoku grid model and Z3-backed generation, validation, and solving logic.

Framework-free: no FastMCP import here, so this module can be exercised directly in tests
without going through the MCP protocol at all.
"""

import random
from collections.abc import Sequence
from typing import Literal

import z3
from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

GRID_SIZE = 9
BOX_SIZE = 3
EMPTY = 0

DifficultyName = Literal["very easy", "easy", "medium", "hard", "very hard"]

# Approximate clue counts; generation stops at or above the target, not necessarily exactly on it,
# since a further removal may break the puzzle's unique-solution property. "very hard"'s target of
# 21 sits safely above the proven minimum of 17 givens for any uniquely-solvable Sudoku puzzle, so it
# stays reachable rather than always flooring out below its nominal target.
_DIFFICULTY_TARGET_GIVENS: dict[DifficultyName, int] = {
    "very easy": 63,
    "easy": 51,
    "medium": 42,
    "hard": 30,
    "very hard": 21,
}


class SudokuGrid(BaseModel):
    """A 9x9 Sudoku grid; 0 marks an empty cell."""

    model_config = ConfigDict(frozen=True)

    rows: tuple[tuple[int, ...], ...] = Field(description="9 rows of 9 cells each; 1-9 for a digit, 0 for empty")

    @model_validator(mode="after")
    def _check_shape_and_range(self) -> "SudokuGrid":
        if len(self.rows) != GRID_SIZE:
            raise ValueError(f"rows must contain exactly {GRID_SIZE} rows, got {len(self.rows)}")
        for row in self.rows:
            if len(row) != GRID_SIZE:
                raise ValueError(f"each row must contain exactly {GRID_SIZE} cells, got {len(row)}")
            for value in row:
                if not (0 <= value <= 9):
                    raise ValueError(f"each cell must be 0-9, got {value}")
        return self


class Cell(BaseModel):
    """A single cell's position.

    row and col are 1-indexed, matching how Sudoku cells are conventionally described in text,
    rather than the 0-indexed positions used internally.
    """

    row: int = Field(ge=1, le=9, description="1-indexed row")
    col: int = Field(ge=1, le=9, description="1-indexed column")


class GeneratePuzzleResult(BaseModel):
    """Result of generating a new puzzle."""

    puzzle: SudokuGrid
    difficulty: DifficultyName
    givens: int = Field(description="Actual number of filled cells in the generated puzzle")


class ValidatePartialResult(BaseModel):
    """Result of validating a partially-filled grid."""

    conflicts: list[Cell]
    is_completable: bool | None = Field(
        description="Whether the grid can still be completed; None when has_conflicts is True, "
        "since completability is not a meaningful question until conflicts are resolved"
    )
    empty_cells: list[Cell] = Field(description="Every still-empty cell in the grid, regardless of has_conflicts")

    @computed_field
    @property
    def has_conflicts(self) -> bool:
        return bool(self.conflicts)

    @computed_field(description="Number of still-empty cells, i.e. len(empty_cells)")
    @property
    def empty_cells_count(self) -> int:
        return len(self.empty_cells)


class ValidateFullResult(BaseModel):
    """Result of validating a fully-filled grid."""

    has_empty_cells: bool
    conflicts: list[Cell]

    @computed_field
    @property
    def is_valid(self) -> bool:
        return not self.has_empty_cells and not self.conflicts


class SolvePuzzleResult(BaseModel):
    """Result of solving an unsolved grid."""

    status: Literal["satisfiable", "conflicting_givens", "unsatisfiable"]
    solution: SudokuGrid | None
    conflicts: list[Cell] = Field(description="Populated only when status is conflicting_givens")


def _box_cells(box_row: int, box_col: int) -> list[tuple[int, int]]:
    """Return the 9 (row, col) coordinates of the 3x3 box at box position (box_row, box_col), each 0-2."""
    return [(box_row * BOX_SIZE + r, box_col * BOX_SIZE + c) for r in range(BOX_SIZE) for c in range(BOX_SIZE)]


def _all_units() -> list[list[tuple[int, int]]]:
    """Return every row, column, and box as a list of its 9 (row, col) coordinates.

    A "unit" is Sudoku terminology for any group of 9 cells that must all hold distinct digits.
    Every cell belongs to exactly three units: one row, one column, and one box.
    """
    rows = [[(r, c) for c in range(GRID_SIZE)] for r in range(GRID_SIZE)]
    cols = [[(r, col) for r in range(GRID_SIZE)] for col in range(GRID_SIZE)]
    boxes = [_box_cells(box_row, box_col) for box_row in range(BOX_SIZE) for box_col in range(BOX_SIZE)]
    return rows + cols + boxes


def _find_conflicts(rows: Sequence[Sequence[int]]) -> list[Cell]:
    """Return every cell that shares its non-zero value with another cell in the same row, column, or box."""
    conflicting: set[tuple[int, int]] = set()
    for unit in _all_units():
        seen: dict[int, tuple[int, int]] = {}
        for r, c in unit:
            value = rows[r][c]
            if value == EMPTY:
                continue
            if value in seen:
                # seen[value] is deliberately left pointing at the first occurrence, not advanced
                # to (r, c): this is what makes a 3+-way duplicate (e.g. the same value at A, B, C)
                # all get flagged against the same anchor A, rather than only the first pair.
                conflicting.add(seen[value])
                conflicting.add((r, c))
            else:
                seen[value] = (r, c)
    return [Cell(row=r + 1, col=c + 1) for r, c in sorted(conflicting)]


def _find_empty_cells(rows: Sequence[Sequence[int]]) -> list[Cell]:
    """Return every still-empty cell in the grid."""
    return [Cell(row=r + 1, col=c + 1) for r in range(GRID_SIZE) for c in range(GRID_SIZE) if rows[r][c] == EMPTY]


def _build_constraints() -> tuple[list[list[z3.ArithRef]], list[z3.BoolRef]]:
    """Build the SMT encoding of the Sudoku rules, independent of any puzzle's specific givens.

    This is the entire "rules of Sudoku" translated into SMT: one integer variable per cell, plus
    two families of constraints over those variables. Callers layer puzzle-specific constraints
    (the fixed given values) on top by adding `cells[r][c] == value` for each known cell.
    """
    cells = [[z3.Int(f"cell_{r}_{c}") for c in range(GRID_SIZE)] for r in range(GRID_SIZE)]
    # Domain constraints: every cell must hold a digit 1-9. z3.Int is unbounded, so this range
    # isn't implied by the variable's declared type the way it would be with a fixed-width type.
    constraints: list[z3.BoolRef] = [
        z3.And(cells[r][c] >= 1, cells[r][c] <= 9) for r in range(GRID_SIZE) for c in range(GRID_SIZE)
    ]
    # All-different constraints: within every row, column, and box, no two cells may share a value.
    # z3.Distinct is a single constraint over N variables, rather than N choose 2 pairwise `!=`s.
    constraints.extend(z3.Distinct([cells[r][c] for r, c in unit]) for unit in _all_units())
    return cells, constraints


def _model_to_rows(model: z3.ModelRef, cells: list[list[z3.ArithRef]]) -> list[list[int]]:
    """Read the solved integer value out of each cell variable, in a satisfying model."""
    return [[model.eval(cells[r][c]).as_long() for c in range(GRID_SIZE)] for r in range(GRID_SIZE)]


def _new_solver() -> z3.Solver:
    # QF_FD (finite-domain) is dramatically faster than the generic Solver() for this kind of
    # small-domain CSP: the general-purpose arithmetic tactic takes tens of seconds on a single
    # Sudoku grid, where QF_FD takes tens of milliseconds.
    return z3.SolverFor("QF_FD")


def _check(solver: z3.Solver) -> bool:
    """Run solver.check(), returning whether it is sat and raising on a genuine z3.unknown result.

    z3.unknown (the solver gave up, e.g. due to a timeout or resource limit) is not the same as
    z3.unsat (proven no solution exists) and must never be folded into it - conflating the two
    would misreport "the solver couldn't decide" as "this puzzle has no solution."
    """
    result = solver.check()
    if result == z3.unknown:
        raise RuntimeError(f"Z3 solver returned unknown: {solver.reason_unknown()}")
    return result == z3.sat


def _solve(givens: Sequence[Sequence[int]]) -> list[list[int]] | None:
    """Return a solution consistent with the given fixed cells, or None if none exists."""
    cells, constraints = _build_constraints()
    solver = _new_solver()
    solver.add(*constraints)
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if givens[r][c] != EMPTY:
                solver.add(cells[r][c] == givens[r][c])
    if not _check(solver):
        return None
    return _model_to_rows(solver.model(), cells)


def _has_unique_solution(givens: Sequence[Sequence[int]], known_solution: Sequence[Sequence[int]]) -> bool:
    """Whether known_solution is the only completion of givens consistent with the Sudoku rules."""
    cells, constraints = _build_constraints()
    solver = _new_solver()
    solver.add(*constraints)
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if givens[r][c] != EMPTY:
                solver.add(cells[r][c] == givens[r][c])
    # SAT here means a *different* completion exists, since the known solution itself is forbidden.
    solver.add(z3.Or([cells[r][c] != known_solution[r][c] for r in range(GRID_SIZE) for c in range(GRID_SIZE)]))
    return not _check(solver)


def generate_puzzle(difficulty: DifficultyName = "medium", *, rng: random.Random | None = None) -> GeneratePuzzleResult:
    """Generate a new, uniquely-solvable Sudoku puzzle at the given difficulty.

    Args:
        difficulty: Target clue count bracket; see `_DIFFICULTY_TARGET_GIVENS`.
        rng: Controls only the order in which cells are considered for removal. It does not make
            the resulting puzzle reproducible: the starting full solution comes from Z3 via
            `_solve`, and Z3's choice of model for an under-constrained problem isn't seeded by
            this parameter, so the same `rng` seed does not yield the same puzzle across calls.
    """
    rng = rng or random.Random()
    full_solution = _solve([[EMPTY] * GRID_SIZE for _ in range(GRID_SIZE)])
    assert full_solution is not None  # the empty grid is always satisfiable

    puzzle = [row[:] for row in full_solution]
    target_givens = _DIFFICULTY_TARGET_GIVENS[difficulty]
    cell_order = [(r, c) for r in range(GRID_SIZE) for c in range(GRID_SIZE)]
    rng.shuffle(cell_order)

    givens_remaining = GRID_SIZE * GRID_SIZE
    for r, c in cell_order:
        if givens_remaining <= target_givens:
            break
        removed_value = puzzle[r][c]
        puzzle[r][c] = EMPTY
        if _has_unique_solution(puzzle, full_solution):
            givens_remaining -= 1
        else:
            puzzle[r][c] = removed_value

    return GeneratePuzzleResult(puzzle=SudokuGrid(rows=puzzle), difficulty=difficulty, givens=givens_remaining)


def validate_partial(grid: SudokuGrid) -> ValidatePartialResult:
    """Check whether a partially-filled grid is conflict-free and, if so, still completable."""
    conflicts = _find_conflicts(grid.rows)
    empty_cells = _find_empty_cells(grid.rows)
    if conflicts:
        return ValidatePartialResult(conflicts=conflicts, is_completable=None, empty_cells=empty_cells)
    is_completable = _solve(grid.rows) is not None
    return ValidatePartialResult(conflicts=[], is_completable=is_completable, empty_cells=empty_cells)


def validate_full(grid: SudokuGrid) -> ValidateFullResult:
    """Check whether a fully-filled grid is a correct Sudoku solution."""
    has_empty_cells = any(value == EMPTY for row in grid.rows for value in row)
    conflicts = _find_conflicts(grid.rows)
    return ValidateFullResult(has_empty_cells=has_empty_cells, conflicts=conflicts)


def solve_puzzle(grid: SudokuGrid) -> SolvePuzzleResult:
    """Solve an unsolved grid, or report why it cannot be solved."""
    conflicts = _find_conflicts(grid.rows)
    if conflicts:
        return SolvePuzzleResult(status="conflicting_givens", solution=None, conflicts=conflicts)
    solution = _solve(grid.rows)
    if solution is None:
        return SolvePuzzleResult(status="unsatisfiable", solution=None, conflicts=[])
    return SolvePuzzleResult(status="satisfiable", solution=SudokuGrid(rows=solution), conflicts=[])
