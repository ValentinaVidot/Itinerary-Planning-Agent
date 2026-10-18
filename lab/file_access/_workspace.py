"""File boundaries and bounded text access; no dependency on an agent framework."""

import os
import json
import stat
import tempfile
from pathlib import Path
from typing import Callable

from ._display import table, ToolOutput, print_output

MAX_FILE_BYTES = 32_768
MAX_OUTPUT_BYTES = 262_144
MAX_FILES = 64
PLAN_PATH = "runtime/plan.md"
PLAN_DATA_PATH = "runtime/plan.json"


class ToolError(ValueError):
    """A safe, student-readable rejection (never include filesystem internals)."""


def terminal_text(text: str) -> str:
    """Don't let retrieved text emit terminal escape/control sequences."""
    return "".join(c for c in text if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))


def text_arg(value, label: str, limit: int, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ToolError(f"{label} must be a {'possibly empty ' if empty else 'nonempty '}string.")
    if len(value) > limit or any(ord(c) < 32 and c not in "\n\t\r" for c in value):
        raise ToolError(f"{label} is too long or contains control characters.")
    return value


class Workspace:
    """A sequential teaching workspace, not an OS sandbox against hostile code."""

    def __init__(self, root: Path, emit: Callable[[str], None] = print_output):
        self.root = root.resolve()
        self.emit = emit
        self.changed: list[str] = []
        self.events: list[dict] = []

    def _path(self, name: str, *, write: bool = False, plan: bool = False, directory: bool = False) -> Path:
        text_arg(name, "path", 240)
        path = Path(name)
        if path.is_absolute() or "\\" in name or any(
            part in (".", "..") or part.startswith(".") for part in name.split("/")
        ):
            raise ToolError("Use a relative path inside data/ or runtime/; no hidden paths or traversal.")
        if not path.parts or path.parts[0] not in ({"runtime"} if write else {"data", "runtime"}):
            raise ToolError("Reads are limited to data/ and runtime/; writes to runtime/.")
        if not directory and path.suffix.lower() not in {".md", ".txt"} and not (plan and name == PLAN_DATA_PATH):
            raise ToolError("Only .md and .txt files are allowed.")
        if write and path.as_posix().casefold() in {PLAN_PATH, PLAN_DATA_PATH} and not plan:
            raise ToolError("Use update_plan to change runtime/plan.md.")
        target = self.root / path
        current = self.root
        for part in path.parts:
            current = current / part
            if current.is_symlink():
                raise ToolError("Symbolic links are not allowed.")
            if current.exists():
                info = current.stat()
                if not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                    raise ToolError("Only regular files and directories are allowed.")
                if stat.S_ISREG(info.st_mode) and info.st_nlink != 1:
                    raise ToolError("Hard-linked files are not allowed.")
        if not target.resolve().is_relative_to(self.root / path.parts[0]):
            raise ToolError("Path is outside the allowed folder.")
        return target

    def list_files(self, path: str) -> dict:
        """List accessible entries only; '.' is a virtual root, not the process cwd."""
        entries = []
        if path == ".":
            candidates = [self.root / name for name in ("data", "runtime")]
        else:
            target = self._path(path, directory=True)
            if not target.is_dir():
                raise ToolError("NOT_FOUND: no directory at that allowed path.")
            candidates = target.iterdir()
        for child in candidates:
            relative = child.relative_to(self.root).as_posix()
            try:
                self._path(relative, directory=True)
                if child.is_dir():
                    kind = "directory"
                elif path != "." and child.is_file() and child.suffix.lower() in {".md", ".txt"}:
                    kind = "file"
                else:
                    continue
            except ToolError:
                continue
            entries.append({"path": relative, "type": kind})
            if len(entries) > MAX_FILES:
                break
        truncated = len(entries) > MAX_FILES
        return {"path": path, "entries": sorted(entries[:MAX_FILES], key=lambda e: e["path"]),
                "truncated": truncated,
                "message": "Listing limited to 64 entries." if truncated else "Accessible entries only; no file contents read."}

    def _files(self, directory: str) -> list[Path]:
        base = self.root / directory
        # Reject a linked root before enumeration. Never follow directory links.
        current = self.root
        for part in Path(directory).parts:
            current /= part
            if current.is_symlink():
                raise ToolError("Symbolic links are not allowed.")
        if not base.exists():
            return []
        files = []
        for parent, dirs, names in os.walk(base, followlinks=False):
            for name in dirs + names:
                if (Path(parent) / name).is_symlink():
                    raise ToolError("Symbolic links are not allowed in generated output.")
            files.extend(Path(parent) / name for name in names)
            if len(files) > MAX_FILES:
                raise ToolError("Output file-count limit reached.")
        return sorted(files)

    def read_file(self, path: str) -> dict:
        target = self._path(path)
        if not target.is_file():
            raise ToolError("NOT_FOUND: no readable file at that allowed path.")
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ToolError("File exceeds the 32 KiB read limit.")
        content = target.read_text(encoding="utf-8")
        if len(content.encode()) > MAX_FILE_BYTES:
            raise ToolError("File exceeds the 32 KiB read limit.")
        return {"path": path, "content": content}

    def _write(self, path: str, content: str, *, plan: bool = False) -> dict:
        text_arg(content, "content", MAX_FILE_BYTES, empty=True)
        data = content.encode("utf-8")
        if len(data) > MAX_FILE_BYTES:
            raise ToolError("File exceeds the 32 KiB write limit.")
        target = self._path(path, write=True, plan=plan)
        if target.exists() and not target.is_file():
            raise ToolError("Destination is not a regular file.")
        files = self._files("runtime")
        if target not in files and len(files) >= MAX_FILES:
            raise ToolError("Output file-count limit reached.")
        size = sum(item.stat().st_size for item in files if item != target)
        if size + len(data) > MAX_OUTPUT_BYTES:
            raise ToolError("Total output exceeds the 256 KiB limit.")
        target.parent.mkdir(parents=True, exist_ok=True)
        self._path(path, write=True, plan=plan)
        temp = None
        try:
            with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
                temp = Path(stream.name)
                stream.write(data)
            temp.replace(target)
        finally:
            if temp is not None and temp.exists():
                temp.unlink()
        self.changed.append(path)
        return {"path": path, "bytes": len(data), "status": "SAVED"}

    def write_file(self, path: str, content: str) -> dict:
        return self._write(path, content)

    def read_plan_data(self):
        """Read bounded structured state; ordinary file tools cannot write it."""
        target = self._path(PLAN_DATA_PATH, plan=True)
        if not target.exists():
            if self._path(PLAN_PATH).exists():
                raise ToolError("A Markdown-only plan exists. Read it, then explicitly save a structured plan with plans.save_plan.")
            return None
        if target.stat().st_size > MAX_FILE_BYTES:
            raise ToolError("Plan exceeds the 32 KiB read limit.")
        try:
            return json.loads(target.read_text(encoding="utf-8"))
        except (ValueError, UnicodeError):
            raise ToolError("Saved plan data is invalid; inspect it before replacing it.") from None

    def write_plan_data(self, data, markdown):
        """Publish the readable view, then commit JSON; roll back on write failure.

        Each file replacement is atomic. A process crash between replacements can
        leave a mismatched view; plans.load_plan detects it instead of trusting it.
        """
        encoded = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
        view = self._path(PLAN_PATH, write=True, plan=True)
        self._path(PLAN_DATA_PATH, write=True, plan=True)
        previous = self.read_file(PLAN_PATH)["content"] if view.exists() else None
        start = len(self.changed)
        result = self._write(PLAN_PATH, markdown, plan=True)
        try:
            self._write(PLAN_DATA_PATH, encoded, plan=True)
        except Exception:
            if previous is None:
                view.unlink()
            else:
                self._write(PLAN_PATH, previous, plan=True)
            del self.changed[start:]
            raise
        return result

    def read_texts(self, directory: str) -> dict[str, str]:
        """Read a bounded folder recursively; matching belongs to the caller."""
        base = self._path(directory, directory=True)
        if base.exists() and not base.is_dir():
            raise ToolError("NOT_FOUND: no directory at that allowed path.")
        documents = {}
        total = 0
        for path in self._files(directory):
            relative = path.relative_to(self.root).as_posix()
            if path.suffix.lower() in {".md", ".txt"}:
                content = self.read_file(relative)["content"]
                total += len(content.encode("utf-8"))
                if total > MAX_OUTPUT_BYTES:
                    raise ToolError("Folder contents exceed the 256 KiB read budget.")
                documents[relative] = content
        return documents

    # SUPPLIED PRESENTATION: label tool output; the terminal renderer chooses colors.
    def emit_tool(self, name: str, text: str):
        self.emit(ToolOutput(text, name))

    def show(self, name: str, result: dict | list[str]):
        """Display a successful tool result; file contents stay in the model result."""
        self.events.append({"tool": name, "ok": True,
                            "path": result.get("path") if isinstance(result, dict) else None})
        if name == "read_file":
            self.emit_tool(name, f"Read: {result['path']}")
        elif name == "write_file":
            self.emit_tool(name, f"Written: {result['path']} ({result['bytes']} bytes)")
        elif name == "list_files":
            self.emit_tool(name, f"Files in {result['path']}")
            self.emit_tool(name, table(["Path", "Type"], [(e["path"], e["type"]) for e in result["entries"]], [65, 12]))
            if result["truncated"]:
                self.emit_tool(name, result["message"])
        elif name == "search_local":
            self.emit_tool(name, "Local file search")
            self.emit_tool(name, table(["File"], [(filename,) for filename in result], [80]))
            if not result:
                self.emit_tool(name, "No matches.")
