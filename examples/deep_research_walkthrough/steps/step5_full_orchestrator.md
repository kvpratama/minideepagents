# Step 5 — The full orchestrator

## What changed from Step 4
| | Step 4 | Step 5 |
|---|---|---|
| Architecture | orchestrator + 1 sub-agent | **same** |
| Orchestrator prompt | minimal (~10 lines) | full `RESEARCH_WORKFLOW_INSTRUCTIONS` + `SUBAGENT_DELEGATION_INSTRUCTIONS` |
| Sub-agent prompt | minimal | full `RESEARCHER_INSTRUCTIONS` |
| Limits | implicit | explicit `max_concurrent_research_units` and `max_researcher_iterations` |
| Output file | `/final_report.md` | **same**, plus `/research_request.md` |

## This file mirrors `examples/deep_research/agent.py`

Diff them. The only meaningful differences are:

- `model = get_model()` instead of a hardcoded `init_chat_model(...)`. Our
  `config.py` reads model + provider + base URL from `.env`.
- The three prompt blocks are vendored inline here for self-containment.
  In the real example they live in `research_agent/prompts.py`.

That's it. **Step 5 is the example.**

## What the prompts contribute

| Prompt | What it adds |
|---|---|
| `RESEARCH_WORKFLOW_INSTRUCTIONS` | the 6-step workflow (plan → save request → delegate → synthesize → write report → verify), report-structure recipes (comparison / list / overview), and citation rules |
| `SUBAGENT_DELEGATION_INSTRUCTIONS` | when to use 1 vs N sub-agents, parallelization limits, iteration cap |
| `RESEARCHER_INSTRUCTIONS` | per-sub-agent search budget, reflection-after-search rule, stopping criteria, response format |

These are *purely prompt engineering* — no new code is needed in this step.
That's the whole pitch of Deep Agents: most of the "intelligence" comes from
prompts on top of a small, fixed middleware stack.

## Try it
```bash
uv run python steps/step5_full_orchestrator.py "What are the top 5 LLM coding agents in 2025?"
```

After the run, the agent should have written both `/research_request.md`
(the original question) and `/final_report.md` (the synthesized report with
consolidated citations).

## Where to go from here
- **Trace it in Studio:** `langgraph dev` from the walkthrough root and pick
  any of the 5 graphs from the dropdown.
- **Swap models:** edit `.env` to point `MODEL` / `MODEL_PROVIDER` /
  `BASE_URL` at any LangChain provider — no code changes.
- **Add skills, persistent memory, or human-in-the-loop:** see the
  `deep-agents-memory` and `deep-agents-orchestration` skills.
