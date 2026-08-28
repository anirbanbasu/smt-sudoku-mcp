"""Unit tests for the framework-free Sudoku core: no FastMCP/MCP protocol involved."""

import random

import pytest
import z3
from pydantic import ValidationError

from smt_sudoku_mcp.sudoku import (
    _DIFFICULTY_TARGET_GIVENS,
    EMPTY,
    GRID_SIZE,
    Cell,
    SudokuGrid,
    _has_unique_solution,
    _solve,
    generate_puzzle,
    solve_puzzle,
    validate_full,
    validate_partial,
)


def _empty_rows() -> list[list[int]]:
    return [[EMPTY] * GRID_SIZE for _ in range(GRID_SIZE)]


def _full_solution() -> list[list[int]]:
    solution = _solve(_empty_rows())
    assert solution is not None
    return solution


# A partial grid with no pairwise row/column/box conflict, yet no valid completion exists: box
# (rows 0-2, cols 0-2) has every digit except 5 already placed, leaving only cell (2, 2) empty, so
# the box forces that cell to be 5 - but row 2 already has a 5 at column 5, so no assignment works.
_UNSATISFIABLE_CONFLICT_FREE_ROWS = [
    [1, 2, 3, 0, 0, 0, 0, 0, 0],
    [4, 6, 7, 0, 0, 0, 0, 0, 0],
    [8, 9, 0, 0, 0, 5, 0, 0, 0],
    *([0] * GRID_SIZE for _ in range(6)),
]


class _UnknownSolver:
    """Stand-in for z3.Solver whose check() always reports z3.unknown, e.g. as if it timed out."""

    def add(self, *args: object, **kwargs: object) -> None:
        pass

    def check(self) -> z3.CheckSatResult:
        return z3.unknown

    def reason_unknown(self) -> str:
        return "test-induced timeout"


class TestSolverUnknown:
    """_solve and _has_unique_solution must raise, not silently treat z3.unknown as no-solution."""

    def test_solve_raises_on_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smt_sudoku_mcp.sudoku._new_solver", lambda: _UnknownSolver())
        with pytest.raises(RuntimeError, match="unknown"):
            _solve(_empty_rows())

    def test_has_unique_solution_raises_on_unknown(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("smt_sudoku_mcp.sudoku._new_solver", lambda: _UnknownSolver())
        with pytest.raises(RuntimeError, match="unknown"):
            _has_unique_solution(_empty_rows(), _full_solution())


class TestSudokuGrid:
    """Shape and value-range validation, not Sudoku rule-checking."""

    def test_valid_grid(self) -> None:
        SudokuGrid(rows=_empty_rows())

    def test_wrong_row_count(self) -> None:
        with pytest.raises(ValidationError, match="9 rows"):
            SudokuGrid(rows=_empty_rows()[:-1])

    def test_wrong_column_count(self) -> None:
        rows = _empty_rows()
        rows[0] = rows[0][:-1]
        with pytest.raises(ValidationError, match="9 cells"):
            SudokuGrid(rows=rows)

    def test_value_out_of_range(self) -> None:
        rows = _empty_rows()
        rows[0][0] = 10
        with pytest.raises(ValidationError, match="0-9"):
            SudokuGrid(rows=rows)

    def test_frozen_rejects_field_reassignment(self) -> None:
        grid = SudokuGrid(rows=_empty_rows())
        with pytest.raises(ValidationError, match="frozen"):
            grid.rows = _empty_rows()  # ty: ignore[invalid-assignment]

    def test_rows_are_immutable_tuples(self) -> None:
        grid = SudokuGrid(rows=_empty_rows())
        with pytest.raises(TypeError):
            grid.rows[0][0] = 5  # ty: ignore[invalid-assignment]


class TestCell:
    """Boundary validation on Cell.row/col, which are grid positions (1-9), not cell values."""

    @pytest.mark.parametrize("row", [1, 9])
    def test_row_boundaries_accepted(self, row: int) -> None:
        Cell(row=row, col=1)

    @pytest.mark.parametrize("row", [0, 10])
    def test_row_out_of_range_rejected(self, row: int) -> None:
        with pytest.raises(ValidationError):
            Cell(row=row, col=1)

    @pytest.mark.parametrize("col", [1, 9])
    def test_col_boundaries_accepted(self, col: int) -> None:
        Cell(row=1, col=col)

    @pytest.mark.parametrize("col", [0, 10])
    def test_col_out_of_range_rejected(self, col: int) -> None:
        with pytest.raises(ValidationError):
            Cell(row=1, col=col)


class TestValidatePartial:
    """validate_partial's conflict detection and completability check."""

    def test_no_conflicts_and_completable(self) -> None:
        result = validate_partial(SudokuGrid(rows=_empty_rows()))
        assert result.has_conflicts is False
        assert result.conflicts == []
        assert result.is_completable is True
        assert len(result.empty_cells) == GRID_SIZE * GRID_SIZE

    def test_row_conflict(self) -> None:
        rows = _empty_rows()
        rows[0][0] = 5
        rows[0][3] = 5
        result = validate_partial(SudokuGrid(rows=rows))
        assert result.has_conflicts is True
        assert result.is_completable is None
        assert {(c.row, c.col) for c in result.conflicts} == {(1, 1), (1, 4)}
        assert (1, 1) not in {(c.row, c.col) for c in result.empty_cells}
        assert len(result.empty_cells) == GRID_SIZE * GRID_SIZE - 2

    def test_empty_cells_reported_exactly(self) -> None:
        rows = _full_solution()
        rows = [row[:] for row in rows]
        rows[7][0] = EMPTY
        rows[8][2] = EMPTY
        result = validate_partial(SudokuGrid(rows=rows))
        assert {(c.row, c.col) for c in result.empty_cells} == {(8, 1), (9, 3)}
        assert result.empty_cells_count == 2

    def test_column_conflict(self) -> None:
        rows = _empty_rows()
        rows[0][0] = 7
        rows[3][0] = 7
        result = validate_partial(SudokuGrid(rows=rows))
        assert result.has_conflicts is True
        assert {(c.row, c.col) for c in result.conflicts} == {(1, 1), (4, 1)}

    def test_box_conflict(self) -> None:
        rows = _empty_rows()
        rows[0][0] = 9
        rows[1][1] = 9
        result = validate_partial(SudokuGrid(rows=rows))
        assert result.has_conflicts is True
        assert {(c.row, c.col) for c in result.conflicts} == {(1, 1), (2, 2)}

    def test_conflict_free_but_not_completable(self) -> None:
        result = validate_partial(SudokuGrid(rows=_UNSATISFIABLE_CONFLICT_FREE_ROWS))
        assert result.has_conflicts is False
        assert result.is_completable is False

    def test_triple_duplicate_in_one_unit(self) -> None:
        # Three cells sharing a value within a single row: seen[5] anchors on the first occurrence
        # and is never advanced, so both later duplicates get flagged against that same anchor.
        rows = _empty_rows()
        rows[0][0] = 5
        rows[0][3] = 5
        rows[0][6] = 5
        result = validate_partial(SudokuGrid(rows=rows))
        assert {(c.row, c.col) for c in result.conflicts} == {(1, 1), (1, 4), (1, 7)}

    def test_cell_conflicting_across_multiple_units(self) -> None:
        # Cell (0, 0) conflicts via its row (with (0, 3)) and, separately, via its column (with
        # (3, 0)): each unit's `seen` dict is independent, so this must not corrupt either
        # detection, and (0, 0) itself must appear only once in the deduplicated result.
        rows = _empty_rows()
        rows[0][0] = 5
        rows[0][3] = 5
        rows[3][0] = 5
        result = validate_partial(SudokuGrid(rows=rows))
        assert {(c.row, c.col) for c in result.conflicts} == {(1, 1), (1, 4), (4, 1)}


class TestValidateFull:
    """validate_full's checks for emptiness and rule conflicts."""

    def test_valid_full_solution(self) -> None:
        result = validate_full(SudokuGrid(rows=_full_solution()))
        assert result.is_valid is True
        assert result.has_empty_cells is False
        assert result.conflicts == []

    def test_has_empty_cells(self) -> None:
        rows = _full_solution()
        rows[0][0] = EMPTY
        result = validate_full(SudokuGrid(rows=rows))
        assert result.is_valid is False
        assert result.has_empty_cells is True

    def test_conflicting_full_grid(self) -> None:
        # Overwriting one cell with its row-neighbour's value necessarily creates at least two
        # conflicts in a full grid: the row duplicate itself, and a column duplicate too, since the
        # overwritten cell's column already contained that value somewhere else (every digit
        # appears exactly once per column in a valid full grid).
        rows = _full_solution()
        rows[0][1] = rows[0][0]
        result = validate_full(SudokuGrid(rows=rows))
        assert result.is_valid is False
        assert result.has_empty_cells is False
        assert {(1, 1), (1, 2)} <= {(c.row, c.col) for c in result.conflicts}


class TestSolvePuzzle:
    """solve_puzzle's three possible outcomes: satisfiable, conflicting givens, unsatisfiable."""

    def test_satisfiable(self) -> None:
        result = solve_puzzle(SudokuGrid(rows=_empty_rows()))
        assert result.status == "satisfiable"
        assert result.conflicts == []
        assert result.solution is not None
        assert validate_full(result.solution).is_valid is True

    def test_conflicting_givens(self) -> None:
        rows = _empty_rows()
        rows[0][0] = 4
        rows[0][1] = 4
        result = solve_puzzle(SudokuGrid(rows=rows))
        assert result.status == "conflicting_givens"
        assert result.solution is None
        assert len(result.conflicts) == 2

    def test_unsatisfiable(self) -> None:
        result = solve_puzzle(SudokuGrid(rows=_UNSATISFIABLE_CONFLICT_FREE_ROWS))
        assert result.status == "unsatisfiable"
        assert result.solution is None
        assert result.conflicts == []


class TestGeneratePuzzle:
    """generate_puzzle's difficulty handling and its uniqueness guarantee."""

    @pytest.mark.parametrize("difficulty", ["very easy", "easy", "medium", "hard", "very hard"])
    def test_generates_unique_solvable_puzzle(self, difficulty: str) -> None:
        result = generate_puzzle(difficulty, rng=random.Random(0))  # type: ignore[arg-type]
        assert result.difficulty == difficulty
        assert result.givens >= _DIFFICULTY_TARGET_GIVENS[difficulty]

        solved = solve_puzzle(result.puzzle)
        assert solved.status == "satisfiable"
        assert solved.solution is not None
        assert _has_unique_solution(result.puzzle.rows, solved.solution.rows) is True

    def test_default_difficulty_is_medium(self) -> None:
        result = generate_puzzle(rng=random.Random(0))
        assert result.difficulty == "medium"
