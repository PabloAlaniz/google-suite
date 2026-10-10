"""Google Suite MCP - Model Context Protocol server for gsuite-sdk."""

__version__ = "0.1.0"

from gsuite_mcp.server import build_server, main
from gsuite_mcp.services import Services

__all__ = [
    "build_server",
    "main",
    "Services",
]
