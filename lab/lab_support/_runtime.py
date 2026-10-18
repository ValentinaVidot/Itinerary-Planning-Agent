"""Terminal entry point and compatibility adapter for the public session API."""

import argparse
import re
import sys
from pathlib import Path

from file_access._display import print_output

from ._provider import BUDGET_USD, Ledger, MODEL, OpenRouter, RunError, load_config
from file_access._workspace import Workspace, terminal_text
from file_access import FileAccess
from .connection import LabConnection
from .session import Session

ROOT = Path(__file__).resolve().parent.parent

def safe_output(text: str, key: str = "") -> str:
    if key:
        text = text.replace(key, "[REDACTED]")
    text = re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", text)
    return terminal_text(text)


class LabSession(Session):
    """Compatibility terminal adapter; projects use connection.session()."""

    def __init__(self, workspace, client, ledger, emit=print_output,
                 *, instructions=None, tools=None, agent_factory=None, runner=None):
        from agent import create_agent
        factory = agent_factory or create_agent
        def configured(model):
            agent = factory(model)
            if instructions is not None:
                agent.instructions = instructions
            if tools is not None:
                agent.tools = tools
            return agent
        connection = LabConnection(client, ledger, workspace.root, emit)
        access = FileAccess(workspace.root, emit)
        access._default = workspace
        super().__init__(connection, access, agent_factory=configured, runner=runner)
        self.workspace, self.ledger, self.emit = workspace, ledger, emit
        self.transport = connection.transport
        self.openai_client = connection.openai_client
        self.run_config = connection.run_config
        self.web_sources = self.search.web_sources

    def run_turn(self, user_input):
        result = self.run(user_input)
        if result.status == "failed":
            raise self._last_error from None
        if result.status != "empty":
            self.emit("\nAssistant:\n" + result.answer)
            self.emit("Files changed this turn: " + (", ".join(result.artifacts) or "none"))
        return result.answer


def interact(agent: LabSession, input_fn=input):
    """The outer loop is deliberately small and independent of the model loop."""
    while True:
        try:
            user_input = input_fn("\nYou> ").strip()
        except (EOFError, KeyboardInterrupt):
            agent.emit("\nSession ended. Saved files remain in runtime/.")
            return
        if user_input.casefold() in {"/quit", "/exit"}:
            agent.emit("Session ended. Saved files remain in runtime/.")
            return
        if not user_input:
            continue
        if user_input.startswith("/"):
            agent.emit("Commands: /quit or /exit. Otherwise enter a task.")
            continue
        try:
            agent.run_turn(user_input)
        except RunError as exc:
            agent.emit(f"Stopped: {exc}")


def startup_budget(allowance, ledger):
    remaining = max(0.0, BUDGET_USD - ledger.data["cost"])
    remote = allowance.get("remaining")
    if isinstance(remote, (int, float)):
        remaining = min(remaining, max(0.0, remote))
    if ledger.data["pending"] or ledger.data["unknown_cost"]:
        return "Remaining lab budget: unknown — instructor reconciliation needed."
    return f"Remaining lab budget: ${remaining:.2f}"


def main(*, agent_factory=None, runner=None, instructions=None, tools=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo", action="store_true", help="offline scripted walkthrough; no API calls")
    parser.add_argument("--check", action="store_true", help="verify configuration and key allowance without a model call")
    parser.add_argument("--prompt", help="run one user turn, then exit")
    args = parser.parse_args()
    try:
        if args.demo:
            from ._demo import run_demo
            run_demo(instructions=instructions, tools=tools,
                     agent_factory=agent_factory, runner=runner)
            return 0
        key, _ = load_config(ROOT)
        emit = lambda text: print_output(text, cleaned=safe_output(text, key))
        client = OpenRouter(key)
        allowance = client.check_key()
        if args.check:
            emit(startup_budget(allowance, Ledger(ROOT / ".lab-state", key)))
            emit(f"Configuration OK for {MODEL}. Model/tool execution has not been tested by --check.")
            return 0
        ledger = Ledger(ROOT / ".lab-state", key)
        with ledger.lock():
            # Reload after taking the lock so concurrent startups cannot use stale totals.
            ledger = Ledger(ROOT / ".lab-state", key)
            agent = LabSession(Workspace(ROOT, emit), client, ledger, emit,
                               instructions=instructions, tools=tools,
                               agent_factory=agent_factory, runner=runner)
            emit(f"Product-analysis lab — {MODEL}\nEnter a task or follow-up. /quit, /exit.")
            emit("Try: Explore the available materials and suggest three product questions we could investigate.")
            emit(startup_budget(allowance, ledger))
            try:
                if args.prompt:
                    agent.run_turn(args.prompt)
                else:
                    interact(agent)
            finally:
                agent.connection.close()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted. Saved files remain; an in-flight request may have unknown cost.")
        return 130
    except (RunError, OSError) as exc:
        print(f"Stopped: {exc}" if isinstance(exc, RunError) else "Stopped: local file access failed.", file=sys.stderr)
        return 1
