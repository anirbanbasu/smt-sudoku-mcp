"""Tests for the process entry points.

Covers the console script's main() and server.run()'s transport dispatch. These stub out
FastMCP's actual run() (which would block starting a real server/binding a port) and just verify
the env-var-to-transport wiring is correct.
"""

from unittest.mock import MagicMock

from starlette.middleware.cors import CORSMiddleware

import smt_sudoku_mcp
from smt_sudoku_mcp import EnvVars, server as server_module


def test_main_delegates_to_server_run(monkeypatch) -> None:
    """main() should call server.run() with no arguments."""
    run_mock = MagicMock()
    monkeypatch.setattr(server_module, "run", run_mock)
    smt_sudoku_mcp.main()
    run_mock.assert_called_once_with()


def test_run_uses_stdio_transport(monkeypatch) -> None:
    """run() should call FastMCP.run(transport='stdio') when configured for stdio."""
    monkeypatch.setattr(EnvVars, "SMT_SUDOKU_MCP_TRANSPORT", "stdio")
    fake_mcp = MagicMock()
    monkeypatch.setattr(server_module, "build_server", lambda: fake_mcp)
    server_module.run()
    fake_mcp.run.assert_called_once_with(transport="stdio", show_banner=False)


def test_run_uses_streamable_http_transport(monkeypatch) -> None:
    """run() should forward host/port/allowed_origins, plus a CORSMiddleware, for streamable-http."""
    monkeypatch.setattr(EnvVars, "SMT_SUDOKU_MCP_TRANSPORT", "streamable-http")
    monkeypatch.setattr(EnvVars, "SMT_SUDOKU_MCP_HOST", "0.0.0.0")
    monkeypatch.setattr(EnvVars, "SMT_SUDOKU_MCP_PORT", 9000)
    monkeypatch.setattr(EnvVars, "SMT_SUDOKU_MCP_ALLOWED_ORIGINS", ["http://localhost:6274"])
    fake_mcp = MagicMock()
    monkeypatch.setattr(server_module, "build_server", lambda: fake_mcp)
    server_module.run()

    call_kwargs = fake_mcp.run.call_args.kwargs
    middleware = call_kwargs.pop("middleware")
    assert call_kwargs == {
        "transport": "streamable-http",
        "host": "0.0.0.0",
        "port": 9000,
        "allowed_origins": ["http://localhost:6274"],
        "show_banner": False,
    }
    assert len(middleware) == 1
    cors_cls, _cors_args, cors_kwargs = middleware[0]
    assert cors_cls is CORSMiddleware
    assert cors_kwargs == {
        "allow_origins": ["http://localhost:6274"],
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def test_run_exits_quietly_on_keyboard_interrupt(monkeypatch, capsys) -> None:
    """run() should not let KeyboardInterrupt propagate as an unhandled traceback.

    FastMCP's own run() already performs a graceful async shutdown before re-raising
    KeyboardInterrupt (confirmed by manually sending SIGINT to a running server) - this only
    needs to stop that re-raise from reaching the top of the process as a raw traceback.
    """
    monkeypatch.setattr(EnvVars, "SMT_SUDOKU_MCP_TRANSPORT", "stdio")
    fake_mcp = MagicMock()
    fake_mcp.run.side_effect = KeyboardInterrupt
    monkeypatch.setattr(server_module, "build_server", lambda: fake_mcp)

    server_module.run()  # should return normally, not raise

    assert "shut" in capsys.readouterr().err.lower()
