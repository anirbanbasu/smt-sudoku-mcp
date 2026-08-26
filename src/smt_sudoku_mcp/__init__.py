"""smt-sudoku-mcp: an MCP server demonstrating SMT/Z3 constraint solving via Sudoku."""

from environs import Env
from marshmallow.validate import OneOf, Range

PACKAGE_NAME = "smt-sudoku-mcp"

_env = Env()
_env.read_env()


class EnvVars:
    """Typed, validated environment variables for this server."""

    SMT_SUDOKU_MCP_TRANSPORT: str = _env.str(
        "SMT_SUDOKU_MCP_TRANSPORT", default="stdio", validate=OneOf(["stdio", "streamable-http"])
    )
    SMT_SUDOKU_MCP_HOST: str = _env.str("SMT_SUDOKU_MCP_HOST", default="127.0.0.1")
    SMT_SUDOKU_MCP_PORT: int = _env.int("SMT_SUDOKU_MCP_PORT", default=8000, validate=Range(min=1, max=65535))
    SMT_SUDOKU_MCP_ALLOWED_ORIGINS: list[str] = _env.list("SMT_SUDOKU_MCP_ALLOWED_ORIGINS", default=[])


def main() -> None:
    """Entry point for the `smt-sudoku-mcp` console script."""
    from smt_sudoku_mcp.server import run

    run()
