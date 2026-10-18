"""Application error reporting and search availability for standard SDK tools.

This configures copies for a lab run. It does not replace the SDK decorator,
change student function signatures, or mutate their original tool definitions.
"""

from copy import copy
import json

from agents.tool import FunctionTool, set_function_tool_failure_error_function

from . import web
from file_access import files
from file_access._workspace import ToolError, terminal_text
from .events import emit_event, tool_scope


def tool_error(_context, error):
    """Display safe errors without exposing raw arguments or implementation details."""
    message = str(error) if isinstance(error, ToolError) else "Invalid arguments or file operation failed; check the tool's allowed inputs."
    files._workspace.emit_tool("error", "Tool failed: " + terminal_text(message))
    return json.dumps({"ok": False, "error": message})


def prepare_tool(tool):
    if not isinstance(tool, FunctionTool):
        return tool
    prepared = copy(tool)
    set_function_tool_failure_error_function(
        prepared, None if tool.name == "search_web" else tool_error)
    if tool.name == "search_web":
        prepared.is_enabled = lambda _context, _agent: (
            web._service.get() is not None and web._service.get().ledger.remaining_searches > 0)
    invoke = prepared.on_invoke_tool

    async def observed(context, arguments):
        identity = {"tool": prepared.name, "tool_call_id": context.tool_call_id}
        if getattr(context, "agent", None) is not None:
            identity["agent"] = context.agent.name
        with tool_scope(**identity):
            emit_event("tool_started", arguments=arguments)
            try:
                result = await invoke(context, arguments)
            except Exception:
                emit_event("tool_failed", error="Tool execution stopped.")
                raise
            value = result
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    pass
            failed = isinstance(value, dict) and value.get("ok") is False
            emit_event("tool_failed" if failed else "tool_completed", result=value)
            return result

    prepared.on_invoke_tool = observed
    return prepared
