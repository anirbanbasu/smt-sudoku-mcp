"""Integration tests for the MCP tool layer, exercised through FastMCP's in-process Client.

Calling tools through a Client (rather than the underlying functions directly) exercises the
actual MCP protocol serialisation, not just the Python-level logic already covered by
test_sudoku.py. Assertions read `result.structured_content` (a plain dict) rather than
`result.data` (a dynamically-typed attribute-access object), since dict access keeps the
assertions simple.
"""

import httpx2
import pytest
from fastmcp import Client
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from smt_sudoku_mcp.server import build_server
from smt_sudoku_mcp.sudoku import _DIFFICULTY_TARGET_GIVENS, EMPTY, GRID_SIZE

pytestmark = pytest.mark.anyio


def _empty_rows() -> list[list[int]]:
    return [[EMPTY] * GRID_SIZE for _ in range(GRID_SIZE)]


@pytest.fixture
def mcp():
    """A freshly built FastMCP server instance, for in-process Client use."""
    return build_server()


_CORS_ALLOWED_ORIGIN = "http://localhost:6274"


def _cors_app():
    """A streamable-HTTP ASGI app wrapped in the same CORSMiddleware config as server.run()."""
    return build_server().http_app(
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[_CORS_ALLOWED_ORIGIN],
                allow_methods=["*"],
                allow_headers=["*"],
                expose_headers=["Mcp-Session-Id"],
            )
        ]
    )


@pytest.mark.parametrize("difficulty", ["very easy", "easy", "medium", "hard", "very hard"])
async def test_generate_sudoku_puzzle(mcp, difficulty: str) -> None:
    """generate_sudoku_puzzle should return a puzzle with at least the target number of givens."""
    async with Client(mcp) as client:
        result = await client.call_tool("generate_sudoku_puzzle", {"difficulty": difficulty})
    content = result.structured_content
    assert content["difficulty"] == difficulty
    assert content["givens"] >= _DIFFICULTY_TARGET_GIVENS[difficulty]
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


async def test_cors_exposes_session_id_header() -> None:
    """The CORS middleware run() attaches must expose Mcp-Session-Id to browser JS.

    Browsers only grant JS access to response headers listed in Access-Control-Expose-Headers;
    Mcp-Session-Id isn't one of the handful of headers exposed by default. Without explicitly
    exposing it, a browser-based client can't read the session id off the initialize response to
    echo back on later requests, and those later requests then fail with 400 Missing session ID.

    This drives real HTTP through the CORS middleware and asserts on actual response headers,
    rather than mocking FastMCP.run() the way test_entrypoints.py does - the bug is in what the
    middleware stack puts on the wire, which a mocked run() call can't observe.

    Session ids are only assigned by the legacy (2025-06-18) streamable-HTTP handshake; the
    2026-07-28 protocol this project otherwise negotiates by default has no session concept at
    all, so this test pins the client to 2025-06-18 to exercise the code path the header actually
    matters for.
    """
    app = _cors_app()
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-06-18",
                        "capabilities": {},
                        "clientInfo": {"name": "test", "version": "1.0"},
                    },
                },
                headers={
                    "Accept": "application/json, text/event-stream",
                    "Content-Type": "application/json",
                    "MCP-Protocol-Version": "2025-06-18",
                    "Origin": _CORS_ALLOWED_ORIGIN,
                },
            )
    assert response.headers["mcp-session-id"]
    assert response.headers["access-control-expose-headers"] == "Mcp-Session-Id"


async def test_cors_preflight_allowed_origin() -> None:
    """A preflight OPTIONS request from the configured allowed origin should be approved."""
    app = _cors_app()
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.options(
                "/mcp",
                headers={
                    "Origin": _CORS_ALLOWED_ORIGIN,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == _CORS_ALLOWED_ORIGIN


async def test_cors_preflight_disallowed_origin() -> None:
    """A preflight OPTIONS request from an origin not in allow_origins should be rejected.

    Starlette's CORSMiddleware responds 400 and omits Access-Control-Allow-Origin for a
    disallowed origin's preflight, which is what stops a browser from letting the follow-up
    actual request through.
    """
    app = _cors_app()
    async with app.router.lifespan_context(app):
        transport = httpx2.ASGITransport(app=app)
        async with httpx2.AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.options(
                "/mcp",
                headers={
                    "Origin": "http://evil.example",
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
