"""Plan data and rules shared by tools, scripts, and future interfaces."""

import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, ValidationError
from file_access import files, ToolError, text_arg
from lab_support.events import emit_event


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    id: str
    description: str
    status: Literal["pending", "in_progress", "done", "blocked"]


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    goal: str
    steps: list[PlanStep]
    revision_note: str


def validate_plan(plan):
    """Return a fresh validated Plan, or reject it before saving anything."""
    try:
        plan = Plan.model_validate(plan.model_dump() if isinstance(plan, Plan) else plan)
    except ValidationError:
        raise ToolError("A plan needs goal, steps (id, description, status), and revision_note.") from None
    text_arg(plan.goal, "goal", 600)
    text_arg(plan.revision_note, "revision_note", 600)
    if not 1 <= len(plan.steps) <= 8:
        raise ToolError("Supply 1–8 plan steps.")
    ids = set()
    for step in plan.steps:
        sid = text_arg(step.id, "step id", 24)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", sid) or sid in ids:
            raise ToolError("Step IDs must be unique short identifiers.")
        ids.add(sid)
        text_arg(step.description, "description", 400)
    if sum(step.status == "in_progress" for step in plan.steps) > 1:
        raise ToolError("Keep at most one step in progress.")
    return plan


def plan_markdown(plan):
    lines = ["# Plan", "", f"Goal: {plan.goal}", "", f"Update: {plan.revision_note}", ""]
    lines.extend(f"- [{step.status}] {step.id}: {step.description}" for step in plan.steps)
    return "\n".join(lines) + "\n"


def save_plan(plan, access=files):
    """Validate and save the whole plan. Call between turns when editing by hand."""
    plan = validate_plan(plan)
    content = plan_markdown(plan)
    result = access.write_plan_data(plan.model_dump(), content)
    emit_event("plan_changed", plan=plan.model_dump(), path=result["path"])
    return {**result, "content": content, "plan": plan.model_dump()}


def load_plan(access=files):
    """Return the saved Plan or None; detect legacy or inconsistent files."""
    data = access.read_plan_data()
    if data is None:
        return None
    plan = validate_plan(data)
    if access.read_text("runtime/plan.md") != plan_markdown(plan):
        raise ToolError("Plan view differs from plan.json. Inspect both; use save_plan with the chosen plan to repair them.")
    return plan


def display_plan(plan, access=files):
    """Optional terminal view; saving and validation do not depend on this."""
    access.display("update_plan", "\nUpdated plan — runtime/plan.md")
    access.display("update_plan", "Goal: " + plan.goal)
    access.display("update_plan", "Update: " + plan.revision_note)
    access.display_table("update_plan", ["ID", "Status", "Step"],
                         [(s.id, s.status, s.description) for s in plan.steps], [24, 12, 58])
