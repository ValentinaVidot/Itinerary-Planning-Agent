"""Supplied model/search/accounting setup, shared by terminal and project callers."""

import asyncio
from contextlib import contextmanager
import logging
from pathlib import Path
from threading import Lock, get_ident

from agents import RunConfig, ModelSettings, OpenAIChatCompletionsModel, ToolExecutionConfig, set_tracing_disabled
from openai import AsyncOpenAI
import httpx2

from file_access import FileAccess
from ._provider import API_BASE, MODEL, MAX_TOKENS, Ledger, OpenRouter, load_config, RunError
from ._sdk_transport import BudgetTransport
from .events import clean

ROOT = Path(__file__).resolve().parent.parent


class LabConnection:
    """One shared budget and configured model; create separate sessions on it."""

    def __init__(self, client, ledger, root=ROOT, emit=None):
        set_tracing_disabled(True)
        logging.getLogger("openai.agents").disabled = True
        self.client, self.ledger, self.root = client, ledger, Path(root)
        self.emit = emit or (lambda _text: None)
        self.key = getattr(client, "key", "")
        self.guard = Lock()
        self.run_thread = None
        self.closed = False
        self.transport = BudgetTransport(client, ledger, self.emit)
        self.openai_client = AsyncOpenAI(
            api_key=self.key or "offline-demo", base_url=API_BASE, max_retries=0,
            http_client=httpx2.AsyncClient(transport=self.transport, follow_redirects=False))
        self.model = OpenAIChatCompletionsModel(model=MODEL, openai_client=self.openai_client)
        self.run_config = RunConfig(
            model_settings=ModelSettings(max_tokens=MAX_TOKENS,
                extra_body={"reasoning": {"effort": "low"},
                            "provider": {"sort": "throughput", "require_parameters": True}}),
            tracing_disabled=True,
            tool_execution=ToolExecutionConfig(max_function_tool_concurrency=1))

    def session(self, *, root=None, agent_factory=None, runner=None, input_builder=None,
                on_event=None, agent_id=None):
        from .session import Session
        if self.closed:
            raise RunError("This lab connection is closed.")
        return Session(self, FileAccess(root or self.root, self.emit),
                       agent_factory=agent_factory, runner=runner, input_builder=input_builder,
                       on_event=on_event, agent_id=agent_id)

    def close(self):
        # A synchronous owner must retain the ledger lock until worker runs finish.
        if self.run_thread == get_ident():
            raise RunError("Close the connection after the current turn, not inside a tool or callback.")
        with self.guard:
            if not self.closed:
                asyncio.run(self.openai_client.close())
                self.closed = True


@contextmanager
def open_lab(root=ROOT, *, emit=None):
    """Open the configured lab and hold its spending lock across all sessions.

    root locates .env and .lab-state. session(root=...) changes only task files.
    No paid call occurs until a session runs. Use in a synchronous owner thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:
        raise RunError("Open the lab in synchronous setup code, then call session.run_async from your event loop.")
    root = Path(root)
    key, _ = load_config(root)
    client = OpenRouter(key)
    client.check_key()
    ledger = Ledger(root / ".lab-state", key)
    with ledger.lock():
        ledger = Ledger(root / ".lab-state", key)
        output = (lambda text: emit(clean(text, key))) if emit else None
        connection = LabConnection(client, ledger, root, output)
        try:
            yield connection
        finally:
            connection.close()
