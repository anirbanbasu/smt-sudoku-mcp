"""FastMCP server exposing Sudoku generation, validation, and solving as MCP tools."""

import sys

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

from smt_sudoku_mcp import PACKAGE_NAME, EnvVars
from smt_sudoku_mcp.sudoku import (
    DifficultyName,
    GeneratePuzzleResult,
    SolvePuzzleResult,
    SudokuGrid,
    ValidateFullResult,
    ValidatePartialResult,
    generate_puzzle,
    solve_puzzle,
    validate_full,
    validate_partial,
)

LOGO = r"""
╭─╮╭┬╮╶┬╴   ╭─╮╷ ╷╶┬╮╭─╮╷╭ ╷ ╷
╰─╮│││ │    ╰─╮│ │ │││ │├┴╮│ │
╰─╯╵ ╵ ╵    ╰─╯╰─╯╶┴╯╰─╯╵ ╵╰─╯
""".strip("\n")


def build_server() -> FastMCP:
    """Build the FastMCP server instance with its four Sudoku tools registered."""
    mcp = FastMCP(name=PACKAGE_NAME)

    @mcp.tool
    def generate_sudoku_puzzle(difficulty: DifficultyName = "medium") -> GeneratePuzzleResult:
        """Generate a new, uniquely-solvable Sudoku puzzle at the given difficulty."""
        return generate_puzzle(difficulty)

    @mcp.tool
    def validate_partial_sudoku_solution(grid: SudokuGrid) -> ValidatePartialResult:
        """Check whether a partially-filled Sudoku grid is conflict-free and still completable."""
        return validate_partial(grid)

    @mcp.tool
    def validate_full_sudoku_solution(grid: SudokuGrid) -> ValidateFullResult:
        """Check whether a fully-filled Sudoku grid is a correct solution."""
        return validate_full(grid)

    @mcp.tool
    def solve_sudoku_puzzle(grid: SudokuGrid) -> SolvePuzzleResult:
        """Solve an unsolved Sudoku grid, or report why it cannot be solved."""
        return solve_puzzle(grid)

    return mcp


def run() -> None:
    """Run the server using the transport configured via EnvVars."""
    # Printed to stderr, not stdout: stdio transport uses stdout for the MCP JSON-RPC stream
    # itself, so anything else written there would corrupt it. show_banner=False replaces
    # FastMCP's own banner with this one, rather than showing both.
    print(LOGO, file=sys.stderr)
    mcp = build_server()
    try:
        if EnvVars.SMT_SUDOKU_MCP_TRANSPORT == "stdio":
            mcp.run(transport="stdio", show_banner=False)
        else:
            # allowed_origins/host_origin_protection is a server-side request guard against
            # spoofed Origin/Host headers - it is not CORS and never emits
            # Access-Control-Allow-Origin, so browser JS cannot read cross-origin responses
            # without CORSMiddleware added explicitly below.
            mcp.run(
                transport=EnvVars.SMT_SUDOKU_MCP_TRANSPORT,
                host=EnvVars.SMT_SUDOKU_MCP_HOST,
                port=EnvVars.SMT_SUDOKU_MCP_PORT,
                allowed_origins=EnvVars.SMT_SUDOKU_MCP_ALLOWED_ORIGINS or None,
                host_origin_protection="auto",
                middleware=[
                    Middleware(
                        CORSMiddleware,
                        allow_origins=EnvVars.SMT_SUDOKU_MCP_ALLOWED_ORIGINS,
                        allow_methods=["*"],
                        allow_headers=["*"],
                        # Streamable HTTP returns the session ID as a response header on
                        # initialization; without exposing it, browser JS can't read it to send
                        # back on subsequent requests, which then fail with 400 Missing session ID.
                        expose_headers=["Mcp-Session-Id"],
                    )
                ],
                show_banner=False,
            )
    except KeyboardInterrupt:
        # mcp.run() already performs its own graceful async shutdown on SIGINT before its
        # underlying anyio runner re-raises KeyboardInterrupt here - this only stops that
        # re-raise from printing an unhandled traceback on top of an already-clean shutdown.
        print("Shutting down.", file=sys.stderr)
