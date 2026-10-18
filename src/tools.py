"""Agent tools: ordinary Python functions exposed by the standard SDK decorator."""

from agents import function_tool
from file_access import files, text_arg
from lab_support import web
from plans import Plan, PlanStep, save_plan, display_plan


@function_tool
def list_files(path: str) -> dict:
    """List accessible names in a folder. Use '.' to discover data/ and runtime/."""
    return files.list_files(path)


@function_tool
def read_file(path: str) -> str:
    """Read a .md/.txt file in data/ or runtime/. Returns its text."""
    return files.read_text(path)


@function_tool
def write_file(path: str, content: str) -> str:
    """Save notes or reports under runtime/. Only update_plan can change the plan."""
    files.write_text(path, content)
    return "Saved " + path


@function_tool
def save_recommendation(recommendation: str) -> str:
    """Save the recommendation after the user has agreed to it."""
    files.write_text("runtime/recommendation.md", recommendation)
    return "Recommendation saved to runtime/recommendation.md."


@function_tool
def search_local(query: str, path: str) -> list[str]:
    """Search .md/.txt files recursively in a data/ or runtime/ folder.

    Match the entire query as one substring, ignoring case. Spaces, line breaks,
    and punctuation must match exactly; partial words can match. Empty or
    whitespace-only queries return []. Return up to five filenames in
    alphabetical order; use read_file to read a matching file.
    """
    text_arg(query, "query", 200, empty=True)
    documents = files.read_texts(path)  # {"data/brief.md": "file contents", ...}
    files.display("search_local", f"Search query: {query!r}")
    files.display("search_local", f"Search path: {path} (including subfolders)")
    # For students: lower() ignores case; in searches for the entire query.
    # "import preview" must appear together, with that space between the words.
    # "import" also matches "imported". strip() below only checks for a blank query.

    # ADD YOUR CODE HERE: comment out the reference implementation below when running your own code
    lowered_query = query.lower()              # step 1: one lowercase string
    matches = []                               # start with no matches
    if query.strip():                          # step 5: skip blank queries
        for filename in sorted(documents):     # step 2: alphabetical filenames
            text = documents[filename].lower() # that file's text, lowercased
            if lowered_query in text:          # step 3: whole query appears?
                matches.append(filename)       # keep the filename
        matches = matches[:5]                  # step 4: at most five


    # REFERENCE IMPLEMENTATION: comment it out when trying your own solution.
    # query = query.lower()
    # matches = []
    # if query.strip():
    #     for filename, content in sorted(documents.items()):
    #         if query in content.lower():
    #             matches.append(filename)
    #         if len(matches) == 5:
    #             break
    # files.show_result("search_local", matches)
    # return matches


@function_tool
def search_web(query: str) -> dict:
    """Search public sources. Use public queries, never secrets or internal text."""
    return web.search(query)


# Follow save_plan into plans.py to inspect the shared validation and storage.
# The agent and a future plan editor can call the same ordinary Python function.
@function_tool
def update_plan(goal: str, steps: list[PlanStep], revision_note: str) -> dict:
    """Replace the plan with 1–8 steps. Mark done only after work succeeds."""
    plan = Plan(goal=goal, steps=steps, revision_note=revision_note)
    result = save_plan(plan)
    display_plan(plan)
    return result
