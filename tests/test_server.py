"""Integration tests for the MCP tool layer, exercised through FastMCP's in-process Client.

Calling tools through a Client (rather than the underlying functions directly) exercises the
actual MCP protocol serialisation, not just the Python-level logic already covered by
test_sudoku.py. Assertions read `result.structured_content` (a plain dict) rather than
`result.data` (a dynamically-typed attribute-access object), since dict access keeps the
assertions simple.
"""

import pytest
from fastmcp import Client

from smt_sudoku_mcp.server import build_server
from smt_sudoku_mcp.sudoku import EMPTY, GRID_SIZE

pytestmark = pytest.mark.anyio


def _empty_rows() -> list[list[int]]:
    return [[EMPTY] * GRID_SIZE for _ in range(GRID_SIZE)]


@pytest.fixture
def mcp():
    """A freshly built FastMCP server instance, for in-process Client use."""
    return build_server()


async def test_generate_sudoku_puzzle(mcp) -> None:
    """generate_sudoku_puzzle should return a puzzle with roughly the requested number of givens."""
    async with Client(mcp) as client:
        result = await client.call_tool("generate_sudoku_puzzle", {"difficulty": "easy"})
    content = result.structured_content
    assert content["difficulty"] == "easy"
    assert content["givens"] >= 40
    assert len(content["puzzle"]["rows"]) == GRID_SIZE


async def test_validate_partial_sudoku_solution(mcp) -> None:
    """validate_partial_sudoku_solution should report a row conflict as a non-error result."""
    rows = _empty_rows()
    rows[0][0] = 5
    rows[0][1] = 5
    async with Client(mcp) as client:
        result = await client.call_tool("validate_partial_sudoku_solution", {"grid": {"rows": rows}})
    content = result.structured_content
    assert content["has_conflicts"] is True
    assert content["is_completable"] is None


async def test_validate_full_sudoku_solution(mcp) -> None:
    """A generated-then-solved puzzle should validate as a correct full solution."""
    async with Client(mcp) as client:
        generated = await client.call_tool("generate_sudoku_puzzle", {"difficulty": "easy"})
        solved = await client.call_tool("solve_sudoku_puzzle", {"grid": generated.structured_content["puzzle"]})
        result = await client.call_tool(
            "validate_full_sudoku_solution", {"grid": solved.structured_content["solution"]}
        )
    content = result.structured_content
    assert content["is_valid"] is True
    assert content["has_empty_cells"] is False


async def test_solve_sudoku_puzzle(mcp) -> None:
    """solve_sudoku_puzzle should solve an empty grid."""
    async with Client(mcp) as client:
        result = await client.call_tool("solve_sudoku_puzzle", {"grid": {"rows": _empty_rows()}})
    content = result.structured_content
    assert content["status"] == "satisfiable"
    assert content["solution"] is not None


async def test_solve_sudoku_puzzle_conflicting_givens(mcp) -> None:
    """solve_sudoku_puzzle should report conflicting givens as a non-error result."""
    rows = _empty_rows()
    rows[0][0] = 3
    rows[0][2] = 3
    async with Client(mcp) as client:
        result = await client.call_tool("solve_sudoku_puzzle", {"grid": {"rows": rows}})
    content = result.structured_content
    assert content["status"] == "conflicting_givens"
    assert content["solution"] is None
