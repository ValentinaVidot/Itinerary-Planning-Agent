"""Offline tool practice using the real SDK callback and an isolated folder."""

import asyncio
from contextlib import contextmanager
import json
import shutil
import tempfile
from pathlib import Path

from agents.tool_context import ToolContext

from ._provider import RunError
from ._runtime import ROOT
from file_access._workspace import Workspace
from file_access import files
from . import web
from ._tool_runtime import prepare_tool


class _OfflineWeb:
    def search(self, query):
        raise RunError("try_tool is offline. Use the live agent to search the web.")


def try_tool(selected_tool, **arguments):
    """Call a local tool once, display its result/files, then remove the test folder.

Copies the supplied data only. Does not read .env, construct an API client, use
normal runtime files, or reset the student's accounting. Returns the tool result.
"""
    with tempfile.TemporaryDirectory(prefix="haid-tool-") as directory:
        root = Path(directory)
        shutil.copytree(ROOT / "data", root / "data")
        workspace = Workspace(root)
        encoded = json.dumps(arguments)
        ctx = ToolContext(context=None, tool_name=selected_tool.name,
                          tool_call_id="offline-practice", tool_arguments=encoded)
        print("OFFLINE TOOL PRACTICE - no model calls; temporary files only.")
        print("Tool:", selected_tool.name)
        print("Arguments:", encoded)
        with files.use(workspace), web.use(_OfflineWeb()):
            result = asyncio.run(prepare_tool(selected_tool).on_invoke_tool(ctx, encoded))
        print("Result returned to the agent:", result)
        for path in sorted(set(workspace.changed)):
            print("\nSaved file:", path)
            if path == "runtime/plan.json":
                print(json.dumps(workspace.read_plan_data(), indent=2))
            else:
                print(workspace.read_file(path)["content"])
        print("\nPractice finished. Temporary files removed after this call.")
        return result


@contextmanager
def offline_lab(responses, *, emit=None):
    """Scripted SDK runs in temporary files: no credentials, network, or live ledger.

    Responses are fixtures, not agent judgments. One connection can create several
    sessions with independent histories and a shared test ledger.
    """
    from .connection import LabConnection
    from ._provider import Ledger
    from ._demo import ScriptedClient
    with tempfile.TemporaryDirectory(prefix="haid-project-") as directory:
        root = Path(directory)
        shutil.copytree(ROOT / "data", root / "data")
        connection = LabConnection(ScriptedClient(responses), Ledger(root / ".lab-state"), root, emit)
        try:
            yield connection
        finally:
            connection.close()


def scripted_reply(text=None, *, calls=()):
    """Create a fake model reply; calls is a list of (tool_name, arguments) pairs."""
    from ._demo import reply
    return reply(calls=calls, content=text)
