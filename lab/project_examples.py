"""Optional offline project examples. Run: python project_examples.py

Responses are scripted: these examples test wiring, not model quality.
"""

import json
import shutil

from agent import create_agent
from lab_support.testing import offline_lab, scripted_reply


def researcher(model):
    agent = create_agent(model)
    agent.name = "Researcher"
    agent.instructions = "Read the supplied evidence and propose one improvement."
    return agent


def critic(model):
    agent = create_agent(model)
    agent.name = "Critic"
    agent.instructions = "Identify one limitation in the supplied recommendation."
    return agent


def workflow_example():
    replies = [scripted_reply("Try an import preview."),
               scripted_reply("Validate whether the preview reduces setup errors.")]
    with offline_lab(replies) as lab:
        research = lab.session(agent_factory=researcher)
        review = lab.session(agent_factory=critic)
        draft = research.run("Suggest one improvement.")
        if draft.status != "completed":
            return
        # Separate histories; deliberately pass only the answer. Files are shared.
        critique = review.run("Review this recommendation: " + draft.answer)
        print("Draft:", draft.answer)
        print("Critique:", critique.answer)


def evaluation_example():
    replies = [scripted_reply("Try an import preview."),
               scripted_reply("Interview users about confusing setup steps.")]
    tasks = ["Suggest one improvement.", "Suggest one research activity."]
    with offline_lab(replies) as lab:
        for index, task in enumerate(tasks):
            # Fresh files and history; both trials keep the connection's ledger.
            root = lab.root / f"trial-{index}"
            shutil.copytree(lab.root / "data", root / "data")
            session = lab.session(root=root)
            initial_data = session.files.read_texts("data")
            result = session.run(task)
            record = {"trial": index, "task": task, "condition": "baseline",
                      "model": lab.model.model,
                      "instructions": session.agent.instructions,
                      "tools": [tool.name for tool in session.agent.tools],
                      "initial_state": "fresh supplied data; empty history and runtime",
                      "initial_data": initial_data,
                      "result": result.to_dict()}
            # Inspect or save this record, then assess it with your own rubric.
            print(json.dumps(record, indent=2))


if __name__ == "__main__":
    print("OFFLINE SCRIPTED EXAMPLES — no model calls; no quality evaluation.")
    workflow_example()
    evaluation_example()
