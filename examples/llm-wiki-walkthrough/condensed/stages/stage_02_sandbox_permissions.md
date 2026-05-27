# Stage 2: Sandbox Isolation and Failsafe Permissions

## Stage Summary

* **Current Limitation**: In Stage 1, the agent had raw, unconstrained access to write to any file in the workspace directory. If the model hallucinated or was subjected to a prompt injection, it could modify system rules (`AGENTS.md`) or corrupt the source data (`/raw/`). Additionally, as the wiki grew, the agent could not easily navigate what pages existed.
* **Why the previous design breaks**: The agent has no enforcement layer outside its own system prompt. It can write to read-only zones (`/raw/`) and modify files like `AGENTS.md` to hijack future operations.
* **Why simpler fixes fail**: Asking the LLM to manage file index paths in its system prompt is flaky. The LLM might write broken links, forget pages, or use inconsistent summary formats.
* **What new abstraction is introduced**: 
  1. **Strict Filesystem Boundary Enforcement**: We run the agent inside a `CompositeBackend` that maps path segments to virtual filesystems with granular access policies: `/wiki/**` is `allow` write, `/raw/**` is `deny` write, and `/AGENTS.md` is `deny` write.
  2. **Automated Indexing**: We write a Python-native catalog generator (`index.py`) that extracts page titles, one-line summaries, and metadata (e.g. dates, source count) from the markdown pages. The runner regenerates `/wiki/index.md` after every agent execution.

---

## Full Working Code

See the runnable script: [stage_02_sandbox_permissions.py](file:///home/openclaw/deepagents/llm_wiki_walkthrough/stages/stage_02_sandbox_permissions.py).

Run the initialization:
```bash
uv run python stages/stage_02_sandbox_permissions.py --mode init --repo adacomp
```

Run an ingest on a source file:
```bash
uv run python stages/stage_02_sandbox_permissions.py --mode ingest --repo adacomp --source ./notes/ada.md
```

---

## Detailed Explanation

### What Changed & Why It Matters
We have split the workspace into distinct virtual directories:
* `/raw/`: Read-only storage for immutable source data.
* `/wiki/`: Read-write sandbox where the agent can create and update files.
* `/AGENTS.md`: Read-only instruction sheet defining rules the agent must obey.

We also introduced an automated catalog `wiki/index.md`. The runner, not the agent, manages this file. The runner parses the generated markdown files under `/wiki/` to extract categories, metadata (like `date:` and `sources:` counts), and descriptions, building a consistent navigation index.

### Tradeoffs Introduced
* **Rigidity vs. Control**: The agent can no longer organize the wiki outside the `/wiki/` folder structure, which prevents arbitrary directory creation but ensures clean separation.
* **Runner Overhead**: Every run incurs a filesystem scan by the Python runner to rebuild `wiki/index.md`. This is extremely fast for standard scale but becomes a bottleneck if the wiki contains thousands of pages.

### Failure Demonstration
If a prompt injection attempts to write a file to `/raw/malicious.md` or overwrite `/AGENTS.md`, the underlying `CompositeBackend` intercepts the write operation and rejects it before it interacts with the actual system workspace.

---

## LangChain + LangGraph Mapping

* **LangChain**: The permissions mapping maps to a custom `BaseTool` filesystem interceptor. In LangChain, this would resemble a custom file tool wrapper that validates input paths against a regex/prefix checklist before executing the native OS file call.
* **LangGraph**: A graph is still **not required**. The orchestration remains linear: scaffold local space, copy sources, run agent, rebuild index catalog.

---

## Mentor Mode

* **Aha Insight**: Use the right tool for the job. Do not ask the LLM to format and build lists (indexes) if a basic Python script can extract the metadata and render the markdown deterministically. Keep the LLM focused on synthesis and translation.
* **Common Mistake**: Believing that virtualized paths (like `/wiki/`) in the agent prompt are enough to isolate the agent. Without a virtualized `FilesystemBackend` that validates absolute vs. relative paths, the agent can use relative navigation (`../raw/note.md`) to bypass prefix limits.
* **Tempting Simpler Alternative**: Simply using standard Python `os.chmod` on the local workspace folders.
* **Why it fails**: When executing tasks inside remote serverless containers (like `langsmith.sandbox`), the runner does not run on the same machine as the agent process. Filesystem virtualization and path-routing over network channels (the Agent Context Protocol) are required.
