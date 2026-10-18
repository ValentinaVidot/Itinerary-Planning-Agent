# File access library

This folder provides bounded text-file operations for ordinary Python programs.
It imports no agent SDK and requires no model, API key, or SDK context.
It uses only the Python standard library. Search logic lives in `tools.py`; plan rules live in `plans.py`.

The Files API connects tools to source evidence and saved work. Reading returns
text your tool can process or pass to the agent; writing creates an artifact
you can inspect and reuse after the conversation ends. Centralizing these
operations keeps path handling, folder creation, and access rules consistent
across tools.

```python
from file_access import FileAccess

files = FileAccess("my_project")
files.write_text("runtime/question.md", "How could onboarding improve?")
print(files.read_text("runtime/question.md"))
```

Copy the `file_access/` folder into another project to use this interface there.
Use an explicit root when reusing the library; the convenience `files` instance
defaults to the directory containing this package (the lab root).

## Reading and writing text

All paths are strings relative to the selected root, with `/` separators on
every operating system. Text is read and written as UTF-8.

| Method | Input | Return value and effect |
|---|---|---|
| `read_text(path)` | Existing `.md` or `.txt` file under `data/` or `runtime/` | Complete contents as `str`; a missing file raises `ToolError` |
| `write_text(path, text)` | `.md` or `.txt` destination under `runtime/` and its new contents as `str` | `None`; creates parent folders and creates or replaces the file. Empty text is allowed |
| `list_files(path=".")` | Folder under `data/` or `runtime/`, or `"."` to discover those roots | Dictionary containing `path`, `entries`, `truncated`, and `message`; immediate children only |
| `read_texts(path)` | Folder under `data/` or `runtime/`, including nested folders | `dict[str, str]` mapping paths to complete file text, recursively; a missing or empty folder returns `{}` |

For example, in a new project folder:

```python
files.write_text("runtime/notes/question.md", "Why is import difficult?")
text = files.read_text("runtime/notes/question.md")
assert text == "Why is import difficult?"

documents = files.read_texts("runtime/notes")
assert documents == {"runtime/notes/question.md": "Why is import difficult?"}
```

`files.list_files("runtime/notes")` then returns:

```python
{
    "path": "runtime/notes",
    "entries": [{"path": "runtime/notes/question.md", "type": "file"}],
    "truncated": False,
    "message": "Accessible entries only; no file contents read."
}
```

Each entry has a `path` and a `type` of `"file"` or `"directory"`. A returned path
can be passed directly to another file call. Listings include up to 64 accessible
entries and set `truncated=True` when there are more. A missing listing folder
raises `ToolError`. `read_texts` accepts folders only, not a file path or `"."`.

`read_text`, `write_text`, and `list_files` also print a brief terminal summary.
That summary is separate from their return values. In particular, a successful
`write_text` returns `None`; your tool should return its own confirmation if the
agent needs one. `read_texts` returns its dictionary without printing it.

## Limits and errors

Reads are limited to `.md`/`.txt` files within `data/` and `runtime/`. Writes are
limited to `runtime/`; plan storage reserves `runtime/plan.md` and
`runtime/plan.json`. Ordinary file tools cannot write either. The library
rejects hidden paths, traversal and symbolic/hard links, and bounds file sizes,
file counts, and total output. These checks protect its operations, not arbitrary
Python code running on the computer.

`read_texts` reads at most 64 files, 32 KiB per file and 256 KiB total.
It accepts folders under `data/` or `runtime/`, not the virtual `.` root.
Individual reads and writes also have the 32 KiB limit. Generated output is
limited to 64 files and 256 KiB in total. Oversized reads raise an error instead
of returning shortened text. A rejected operation raises `ToolError` (a
`ValueError` subclass); the lab's tool runner presents it as a failed tool result.
For example, `files.write_text("data/question.md", "New question")` is rejected
because source files are read-only through this API.

## Plans and presentation

Most custom tools need only the four methods above. The following methods
support the supplied plan and terminal code:

| Method | Input | Return value and effect |
|---|---|---|
| `read_plan_data()` | No arguments | Parsed saved plan JSON, or `None` if no plan exists; errors on invalid or legacy-only storage |
| `write_plan_data(data, markdown)` | Plan dictionary and its Markdown text | Saves both plan files; returns a dictionary with `path`, `bytes`, and `status` for the Markdown write |
| `write_plan_text(content)` | Markdown string | Legacy Markdown-only storage; returns `path`, `bytes`, and `status`. Use `plans.save_plan` in new code |
| `show_result(name, result)` | Tool name and a result dictionary, or a filename list for `search_local` | `None`; records a successful result and displays it with a supported renderer |
| `display(name, text)` | Label and text string | `None`; labels and prints terminal output |
| `display_table(name, headers, rows, widths)` | Label, column headings, row values, and column widths as lists | `None`; renders a labeled table |

Matching rules live in `tools.py`; `PlanStep` and plan validation/formatting live
in `plans.py`. Storage primitives do not validate the plan schema: application
code should use `plans.load_plan` and `plans.save_plan`. JSON access is limited to
the reserved plan path and has the same size/link/output limits. Each replacement
is atomic; a failed JSON commit rolls back the Markdown view. `load_plan` detects
mismatched files after an interrupted save. Call these operations between turns.
The `use(workspace)` context manager accepts a `FileAccess` instance or an
infrastructure workspace for isolated tests and lab runs.
It is not needed for ordinary file access or defining a tool.
