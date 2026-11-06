"""MCP server for gsuite-sdk: Gmail, Calendar, Drive, Sheets, Tasks and Contacts tools,
plus read-only Search Console, Google Analytics 4 and Tag Manager tools.

Runs over stdio (``gsuite-mcp``) and reuses the login of ``gsuite auth login``
(GSUITE_TOKEN_DB_PATH / GSUITE_CREDENTIALS_FILE). Tools are annotated so
clients can tell read-only ones from those that send, share or delete.
"""

from __future__ import annotations

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from gsuite_core import __version__
from gsuite_mcp.services import Services
from gsuite_mcp.tools import REGISTRARS
from gsuite_mcp.tools._common import F, Register, sdk_errors

INSTRUCTIONS = """\
Google Workspace for the signed-in user: Gmail, Calendar, Drive, Sheets, Tasks
and Contacts, plus read-only Search Console, Google Analytics 4 and Tag Manager.
Read tools are safe to call freely. Ask the user before tools
that send or forward email, invite attendees, share files, or trash or delete
anything. Dates are
ISO 8601 (2026-03-01 or 2026-03-01T10:00); times without an offset use the
server's GSUITE_DEFAULT_TIMEZONE (UTC by default). If a tool says there is no
login, tell the user to run `gsuite auth login`. Search Console, Analytics and
Tag Manager need the opt-in read-only scopes:
`gsuite auth login --force --scopes default,marketing`."""


def build_server(services: Services | None = None) -> MCPServer:
    """The MCP server; tests pass Services built on mocked clients."""
    svc = services or Services()
    server = MCPServer(
        "gsuite-sdk",
        title="Google Workspace (gsuite-sdk)",
        instructions=INSTRUCTIONS,
        version=__version__,
        website_url="https://pabloalaniz.github.io/google-suite/",
    )

    def tool(annotations: ToolAnnotations) -> Register:
        def register(func: F) -> F:
            server.tool(annotations=annotations)(sdk_errors(func))
            return func

        return register

    for register in REGISTRARS:
        register(tool, svc)

    return server


def main() -> None:
    """Console entry point: `gsuite-mcp` serves over stdio."""
    build_server().run("stdio")


if __name__ == "__main__":
    main()
