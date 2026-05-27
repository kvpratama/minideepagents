# Stage 01 — single shot

## Stage summary

* **Current limitation:** none yet — this is the baseline.
* **What's here:** one `create_deep_agent(...)` call with the default
  `StateBackend`. The agent lives entirely inside the LangGraph run.
* **What this stage demonstrates:** what "no architecture" looks like.

## What changed vs. previous stage

There is no previous stage. This is the null hypothesis: take a model,
hand it a system prompt, invoke it, throw the result away.

## Failure to come

Run the script. Note what *isn't* there:

* Nothing is written to disk.
* There is no `wiki/`, no `raw/`, no `log.md`.
* There is no concept of "the same research topic, two days later".

Two runs of the same question pay the entire reasoning cost twice and
produce two independent, possibly inconsistent answers. The model has
nowhere to *put* anything for next time. Everything the agent learns
during a single graph execution is garbage-collected when the run ends.

This is fine for a chatbot. It is fatal for "build a long-lived topic
corpus" — which is the entire purpose of the original [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki).

## LangChain + LangGraph mapping

* The agent is a compiled LangGraph state graph from `create_deep_agent`.
* `StateBackend` (the default when `backend=` is unspecified) keeps any
  files the agent creates inside the graph's mutable state dict for the
  duration of the run. State is discarded unless a `Checkpointer` is
  configured — and even then it's per-thread, not a shared corpus.
* No graph orchestration pressure exists yet. A single `Runnable` would do.

## Mentor mode

* **Aha:** the choice of *where* the agent's filesystem lives — graph
  state vs. real disk vs. shared remote store — is the first
  architectural choice. The rest of the walkthrough is consequences of
  that choice.
* **Common mistake:** reaching for a checkpointer too early. Checkpoints
  give you "resume this conversation", not "build a corpus across
  unrelated runs". They solve persistence-of-trajectory, not
  persistence-of-knowledge.
* **Tempting alternative:** just put the answer in a vector store and
  call it a day. That works until you need to *edit* the corpus
  (reconcile a contradiction, supersede a stale claim, merge two
  fragments) — at which point you discover you've built a write-once
  knowledge base.
