"""Try itinerary tools offline in a temporary workspace."""

import asyncio
from datetime import date
import json
import shutil
import tempfile
from pathlib import Path

from agents.tool_context import ToolContext
from file_access import files
from file_access._workspace import Workspace
from itinerary import Hotel, Stop, create_trip
from lab_support import web
from lab_support._runtime import ROOT
from lab_support._tool_runtime import prepare_tool
from tools import check_day, find_places, propose_memory, save_itinerary


class _OfflineWeb:
    def search(self, _query):
        raise RuntimeError("This example does not use web search.")


def try_itinerary_tool(selected_tool, workspace, **arguments):
    """Invoke a tool in the same temporary workspace as the created trip."""
    encoded = json.dumps(arguments, default=str)
    context = ToolContext(
        context=None,
        tool_name=selected_tool.name,
        tool_call_id="offline-itinerary-example",
        tool_arguments=encoded,
    )
    with files.use(workspace), web.use(_OfflineWeb()):
        result = asyncio.run(
            prepare_tool(selected_tool).on_invoke_tool(context, encoded)
        )
    print(f"{selected_tool.name}: {result}")
    return result


def run_examples():
    """Create a temporary trip, then run find, check, save, and memory examples."""
    with tempfile.TemporaryDirectory(prefix="itinerary-tools-") as directory:
        root = Path(directory)
        shutil.copytree(ROOT / "data", root / "data")
        workspace = Workspace(root)
        hotel = Hotel(
            name="JB City Hotel",
            city="Johor Bahru",
            lat=1.465,
            lng=103.765,
            check_in=date(2026, 12, 1),
            check_out=date(2026, 12, 2),
        )
        with files.use(workspace):
            create_trip([hotel], ["animals", "food"], "relaxed")
        try_itinerary_tool(
            find_places,
            workspace,
            city="Johor Bahru",
            tags=["animals"],
            near_hotel="JB City Hotel",
        )
        stops = [
            Stop(
                place_id="jb-cat-cafe",
                date=date(2026, 12, 1),
                start="11:00",
                reason="You chose animals; a nearby cat cafe.",
            )
        ]
        stop_data = [stop.model_dump(mode="json") for stop in stops]
        try_itinerary_tool(check_day, workspace, stops=stop_data)
        try_itinerary_tool(save_itinerary, workspace, stops=stop_data, revision_note="Initial plan")
        locked_data = [dict(stop_data[0], locked=True)]
        try_itinerary_tool(save_itinerary, workspace, stops=locked_data, revision_note="Lock the stop")
        try_itinerary_tool(save_itinerary, workspace, stops=[], revision_note="Remove locked stop")
        try_itinerary_tool(
            propose_memory,
            workspace,
            preference="Prefers animal experiences",
            evidence="Selected animals as an interest.",
        )


if __name__ == "__main__":
    print("OFFLINE ITINERARY TOOL PRACTICE - no model calls.")
    run_examples()
