# File access library

This folder provides bounded text-file operations for ordinary Python programs.
It imports no agent SDK and requires no model, API key, or SDK context.
It uses only the Python standard library. Search logic lives in `tools.py`; plan rules live in `plans.py`.

```python
from file_access import FileAccess

files = FileAccess("my_project")
files.write_text("runtime/question.md", "How could onboarding improve?")
print(files.read_text("runtime/question.md"))
```

Copy the `file_access/` folder into another project to use this interface there.
Use an explicit root when reusing the library; the convenience `files` instance
defaults to the directory containing this package.

| Method | Returns |
|---|---|
| `read_text(path)` | File contents as text |
| `write_text(path, text)` | Saves text; raises an error on rejection |
| `list_files(path=".")` | A dictionary with `entries` (path/type), `truncated`, and `message` |
| `read_texts(path)` | Dictionary of filenames to text, recursively; missing folder returns `{}` |
| `read_plan_data()` / `write_plan_data(data, markdown)` | Bounded storage primitives used by `plans.py` |
| `write_plan_text(content)` | Legacy Markdown-only storage; use `plans.save_plan` in new code |
| `show_result(name, result)` | Record and display a tool result |
| `display(name, text)` / `display_table(name, headers, rows, widths)` | Label and render terminal output |

Reads are limited to `.md`/`.txt` files within `data/` and `runtime/`. Writes are
limited to `runtime/`; plan storage reserves `runtime/plan.md` and
`runtime/plan.json`. Ordinary file tools cannot write either. The library
rejects hidden paths, traversal and symbolic/hard links, and bounds file sizes,
file counts, and total output. These checks protect its operations, not arbitrary
Python code running on the computer.

`read_texts` reads at most 64 files, 32 KiB per file and 256 KiB total.
It accepts folders under `data/` or `runtime/`, not the virtual `.` root.
Matching rules live in `tools.py`; `PlanStep` and plan validation/formatting live
in `plans.py`. Storage primitives do not validate the plan schema: application
code should use `plans.load_plan` and `plans.save_plan`. JSON access is limited to
the reserved plan path and has the same size/link/output limits. Each replacement
is atomic; a failed JSON commit rolls back the Markdown view. `load_plan` detects
mismatched files after an interrupted save. Call these operations between turns.
The `use(workspace)` context manager accepts a `FileAccess` instance or an
infrastructure workspace for isolated tests and lab runs.
It is not needed for ordinary file access or defining a tool.
