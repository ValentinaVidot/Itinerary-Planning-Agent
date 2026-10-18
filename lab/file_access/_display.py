"""Plain terminal tables and optional colors; no agent-framework dependency."""
import textwrap
import os
import sys


def clean(value):
    return "".join(c for c in str(value) if c in "\n\t" or (ord(c) >= 32 and ord(c) != 127))


def shorten(value, limit):
    text = " ".join(clean(value).split())
    return text if len(text) <= limit else text[:limit - 1] + "…"


def table(headers, rows, widths):
    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"
    def render(row):
        cells = [textwrap.wrap(" ".join(clean(cell).split()), width=width) or [""]
                 for cell, width in zip(row, widths)]
        return ["| " + " | ".join((cell[i] if i < len(cell) else "").ljust(width)
                for cell, width in zip(cells, widths)) + " |"
                for i in range(max(map(len, cells)))]
    lines = [border, *render(headers), border]
    for row in rows:
        lines.extend(render(row))
        lines.append(border)
    return "\n".join(lines)


# SUPPLIED PRESENTATION: assign one consistent color to each tool.
TOOL_COLORS = {
    "list_files": "90",     # gray
    "read_file": "36",      # cyan
    "write_file": "32",     # green
    "update_plan": "35",    # magenta
    "search_local": "33",   # yellow
    "search_web": "94",     # bright blue
    "error": "31",          # red
}


class ToolOutput(str):
    """Attach a trusted display label without inserting terminal escape codes."""

    # SUPPLIED PRESENTATION: keep callbacks and captured transcripts plain strings.
    def __new__(cls, text, tool):
        message = super().__new__(cls, text)
        message.tool = tool
        return message


# SUPPLIED PRESENTATION: respect redirected output, NO_COLOR, and basic terminals.
def supports_color():
    if not sys.stdout.isatty() or "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    if os.name == "nt":
        # Windows Terminal and common ANSI-aware terminal hosts.
        return bool(os.environ.get("WT_SESSION") or os.environ.get("ANSICON") or
                    os.environ.get("TERM_PROGRAM") or os.environ.get("TERM", "").startswith("xterm"))
    return True


# PROTECTIVE PRESENTATION: clean content first, then add only our trusted colors.
def print_output(message, *, cleaned=None):
    text = clean(message if cleaned is None else cleaned)
    color = TOOL_COLORS.get(message.tool) if isinstance(message, ToolOutput) else None
    if color and supports_color():
        text = f"\033[{color}m{text}\033[0m"
    print(text, flush=True)
