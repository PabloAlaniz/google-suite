"""MCP tools, one module per service.

Each module has ``register(tool, svc)``; ``build_server`` calls them in this
order, which is the order clients list the tools in.
"""

from collections.abc import Callable

from gsuite_mcp.services import Services
from gsuite_mcp.tools import (
    analytics,
    auth,
    calendar,
    contacts,
    drive,
    gmail,
    searchconsole,
    sheets,
    tagmanager,
    tasks,
)
from gsuite_mcp.tools._common import ToolDecorator

REGISTRARS: tuple[Callable[[ToolDecorator, Services], None], ...] = (
    auth.register,
    gmail.register,
    calendar.register,
    drive.register,
    sheets.register,
    tasks.register,
    contacts.register,
    searchconsole.register,
    analytics.register,
    tagmanager.register,
)
