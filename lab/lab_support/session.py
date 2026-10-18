"""Public session: ordinary inputs and structured results, independent of a UI."""

import asyncio
from copy import deepcopy
from dataclasses import dataclass, field
from threading import get_ident
from uuid import uuid4

from agents import MaxTurnsExceeded, AgentsException
from openai import APIError
from pydantic import ValidationError

from file_access import files, ToolError
from . import web
from ._provider import RunError
from ._tool_runtime import prepare_tool
from ._web_search import WebSearch
from .events import clean, emit_event, event_scope, record_event


@dataclass
class TurnResult:
    run_id: str
    agent_id: str
    answer: str
    status: str
    artifacts: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    error: str | None = None
    sdk_result: object = field(default=None, repr=False)

    def to_dict(self):
        """Serializable application record; raw SDK history is intentionally separate."""
        return deepcopy({name: getattr(self, name) for name in
                         ("run_id", "agent_id", "answer", "status", "artifacts", "events", "usage", "error")})


class Session:
    def __init__(self, connection, access, *, agent_factory=None, runner=None,
                 input_builder=None, on_event=None, agent_id=None):
        from agent import create_agent, run_agent, prepare_input
        self.connection = connection
        self.files = access
        self.agent = (agent_factory or create_agent)(connection.model)
        self.agent.tools = [prepare_tool(tool) for tool in self.agent.tools]
        self.runner = runner or run_agent
        self.input_builder = input_builder or prepare_input
        self.on_event = on_event
        self.agent_id = agent_id or uuid4().hex
        self.history = []
        self.last_result = None
        self._last_error = None
        self.search = WebSearch(connection.client, connection.ledger, connection.emit)

    def run(self, user_input):
        """Run one turn; expected execution failures are returned with saved artifacts."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RunError("Use await session.run_async(...) inside an event loop.")
        if not isinstance(user_input, str) or len(user_input) > 6000:
            raise RunError("Please supply text under 6,000 characters.")
        if self.connection.closed:
            raise RunError("This lab connection is closed.")
        if not self.connection.guard.acquire(blocking=False):
            raise RunError("This connection is already running a turn. Run shared-budget sessions sequentially.")
        try:
            if self.connection.closed:
                raise RunError("This lab connection is closed.")
            self.connection.run_thread = get_ident()
            return self._run(user_input)
        finally:
            self.connection.run_thread = None
            self.connection.guard.release()

    def _run(self, user_input):
        connection = self.connection
        workspace = self.files._workspace
        result = TurnResult(uuid4().hex, self.agent_id, "", "empty")
        identity = {"run_id": result.run_id, "agent_id": self.agent_id, "agent": self.agent.name}
        def observe(event):
            record_event(result.events, self.on_event, identity, event, connection.key)
        before = dict(connection.ledger.data)
        changed_start = len(workspace.changed)
        connection.transport.error = None
        self._last_error = None
        inputs = deepcopy(self.history) + [{"role": "user", "content": user_input}]
        with event_scope(observe), files.use(self.files), web.use(self.search):
            if user_input.strip():
                emit_event("turn_started")
                try:
                    inputs = self.input_builder(deepcopy(self.history), user_input, self.files)
                    with asyncio.Runner() as loop:
                        loop.get_loop()
                        sdk_result = self.runner(self.agent, inputs, connection.run_config)
                    result.sdk_result = sdk_result
                    self.history = sdk_result.to_input_list()
                    result.answer = str(sdk_result.final_output or "")
                    if not result.answer.strip():
                        raise RunError("Model returned no final text; inspect the saved plan and retry a focused task.")
                    result.status = "completed"
                except MaxTurnsExceeded as exc:
                    self.history = inputs
                    if exc.run_data:
                        self.history = inputs + [item.to_input_item() for item in exc.run_data.new_items]
                    result.status = "incomplete"
                    result.answer = "Stopped at the 12-request turn limit. Work may be incomplete; inspect the saved plan and continue with a focused request."
                    self.history.append({"role": "assistant", "content": result.answer})
                except (APIError, AgentsException, RunError, ValidationError, ToolError, OSError) as exc:
                    self.history = inputs + [{"role": "assistant", "content":
                        "This turn stopped before completion. Reread the saved plan/report before continuing; some tools may have completed."}]
                    result.status = "failed"
                    result.answer = ""
                    error = connection.transport.error or exc
                    result.error = str(error) if isinstance(error, (RunError, ToolError)) else "SDK run stopped. Saved files remain; no automatic retry was made."
                    self._last_error = error if isinstance(error, RunError) else RunError(result.error)
            result.artifacts = sorted(set(workspace.changed[changed_start:]))
            after = connection.ledger.data
            result.usage = {name: after[name] - before[name] for name in
                            ("requests", "searches", "reserved_searches")}
            result.usage["cost_usd"] = None if after["unknown_cost"] or after["pending"] else after["cost"] - before["cost"]
            for name in ("prompt_tokens", "completion_tokens"):
                result.usage[name] = None if after["unknown_tokens"] or after["pending"] else after[name] - before[name]
            result.answer = clean(result.answer, connection.key)
            result.error = clean(result.error, connection.key)
            emit_event("turn_completed", status=result.status, answer=result.answer,
                       artifacts=result.artifacts, usage=result.usage, error=result.error)
        self.last_result = result
        return result

    async def run_async(self, user_input):
        """UI adapter for the same sync execution. Callbacks run on a worker thread.

        Cancellation waits for the turn to settle; it is not a pause/resume API.
        This keeps callers from releasing the spending lock during paid work.
        """
        task = asyncio.create_task(asyncio.to_thread(self.run, user_input))
        cancelled = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            # Retrieve any exception before honoring cancellation.
            task.result()
            raise asyncio.CancelledError
        return task.result()
