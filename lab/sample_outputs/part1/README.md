# Reference outputs

`offline-transcript.txt` is an explicitly scripted, no-network walkthrough through
the real OpenAI Agents SDK and file tools. It is not evidence of live model
behavior or costs.

`live-initial-plan.md`, `live-revised-plan.md`, and `live-report.md` are actual
GLM 5.3 Flash outputs from the successful 2026-09-17 **OpenAI Agents SDK 0.22.2**
integration test through OpenRouter. These live artifacts predate the generalized
standing instructions and `list_files`; the updated offline transcript exercises
the direct SDK tools and compact tables. The startup budget line in the offline
transcript is illustrative; no credits are spent. The test covered initial product analysis,
a small-business follow-up, and an explanatory question. All structural checks
passed; see `live-validation.json`.

Reported cost: **$0.01500853 (about 1.5 cents)**, including two explicit
`search_web` calls. Exact server-side search counts were not returned, so both
one-search reservations were retained. This is one measured run, not a guaranteed
cost or latency. This recorded run used the former provider price ceiling; the
current code omits that ceiling and can route to providers with different rates.

Instructor review: the report references local interview IDs and public sources,
separates synthetic evidence, preserves interview disagreements, and flags the
dated Productboard PDF. It also provides useful errors for class discussion:
- The 6–15-person segment is a proposal extrapolated from the interviews.
- Ten total setup hours versus four support hours per week does not by itself
  prove the pilot infeasible; the setup schedule and other support demands matter.
- Integrations in competitor excerpts do not establish fully automated onboarding.
- An import preview's effects on setup time and support remain hypotheses.

Treat these model outputs as discussion material, not a grading answer key.

The full live transcript and per-request billing metadata stay in the gitignored
`.lab-state/instructor-tests/` folder. Shared samples omit raw web-excerpt dumps
and contain no API keys or private reasoning.
