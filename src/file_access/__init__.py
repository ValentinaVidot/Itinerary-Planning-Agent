"""Safe text-file access, usable from ordinary Python or any agent framework.

files is configured for this lab folder. FileAccess(root) creates an independent
instance for another project folder with data/ inputs and runtime/ outputs.
No SDK context, decorator, model, API key, or running agent is required.
"""

from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path


from ._workspace import Workspace, ToolError, text_arg, terminal_text, PLAN_PATH
from ._display import table


class FileAccess:
    def __init__(self, root, emit=print):
        self._default = Workspace(Path(root), emit)
        self._override = ContextVar("file_access_override", default=None)

    @property
    def _workspace(self):
        return self._override.get() or self._default

    @contextmanager
    def use(self, workspace):
        """Infrastructure/testing: temporarily select isolated files for this run."""
        token = self._override.set(workspace._workspace if isinstance(workspace, FileAccess) else workspace)
        try:
            yield self
        finally:
            self._override.reset(token)

    def read_text(self, path: str) -> str:
        """Read a .md/.txt file under data/ or runtime/, returning its text."""
        result = self._workspace.read_file(path)
        self._workspace.show("read_file", result)
        return result["content"]

    def write_text(self, path: str, text: str) -> None:
        """Save text under runtime/. The plan is reserved for write_plan_text."""
        result = self._workspace.write_file(path, text)
        self._workspace.show("write_file", result)

    def list_files(self, path: str = ".") -> dict:
        """List names/types without contents, including a flag if truncated."""
        result = self._workspace.list_files(path)
        self._workspace.show("list_files", result)
        return result

    def read_texts(self, path: str) -> dict[str, str]:
        """Return {path: text} for a bounded folder, recursively; missing is empty."""
        return self._workspace.read_texts(path)

    def write_plan_text(self, content: str) -> dict:
        """Persist already validated/formatted text to the reserved plan path."""
        result = self._workspace._write(PLAN_PATH, content, plan=True)
        self._workspace.show("update_plan", result)
        return result

    def read_plan_data(self):
        """Storage primitive; use plans.load_plan for validated application data."""
        return self._workspace.read_plan_data()

    def write_plan_data(self, data: dict, markdown: str) -> dict:
        """Storage primitive; use plans.save_plan to validate and publish a plan."""
        result = self._workspace.write_plan_data(data, markdown)
        self._workspace.show("update_plan", result)
        return result

    def show_result(self, name: str, result: dict | list[str]) -> None:
        """Record and display a tool result using the supplied terminal renderer."""
        self._workspace.show(name, result)

    def display(self, name: str, text: str) -> None:
        """Label terminal output without changing the result returned to the model."""
        self._workspace.emit_tool(name, terminal_text(text))

    def display_table(self, name: str, headers: list, rows: list, widths: list) -> None:
        """Display rows using the supplied terminal layout."""
        self.display(name, table(headers, rows, widths))


files = FileAccess(Path(__file__).resolve().parent.parent)
