"""Try tools without a model or API key. Run: python try_tools.py.

See README.md, 'Test different tools', for inputs and expected results.
"""

from lab_support.testing import try_tool
from tools import save_recommendation, search_local, list_files, read_file, write_file, search_local, update_plan


# Keep the call you want to test, change its arguments, and run this script again.
# Every call gets a fresh copy of data/ and an empty temporary output folder.
if __name__ == "__main__":
    try_tool(save_recommendation, recommendation="Test an import preview with three users.")

    # Uncomment a call to try another tool. Pass the tool itself, then its inputs.
    # try_tool(list_files, path="data")
    # try_tool(read_file, path="data/customer-interviews.md")
    # try_tool(write_file, path="runtime/question.md", content="Why is import difficult?")
    # try_tool(search_local, query="import", path="data")
    # try_tool(search_local, query="IMPORT", path="data")
    # try_tool(search_local, query="import preview", path="data")
    # try_tool(search_local, query="", path="data")
    # try_tool(search_local, query="zzznomatchzzz", path="data")
    # try_tool(update_plan, goal="Understand onboarding", steps=[
    #     {"id": "s1", "description": "Read interviews", "status": "in_progress"},
    #     {"id": "s2", "description": "Compare needs", "status": "pending"},
    # ], revision_note="Initial plan")

    # To test your own tool, import its name from tools and add a try_tool call.
    # search_web needs a live connection; try it through agent.py instead.
