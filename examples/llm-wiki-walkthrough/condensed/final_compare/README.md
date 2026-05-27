# Architectural Comparison: Stage 4 vs. production [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki)

Now that we have reconstructed the architecture of `llm-wiki` from the ground up, let's compare our fully evolved Stage 4 codebase with the production code in [LLM Wiki](https://github.com/langchain-ai/deepagents/tree/main/examples/llm-wiki).

Our Stage 4 code preserves the exact naming, patterns, abstractions, and files of the original repository:
* **`helpers.py`**: Custom runner orchestration.
* **`index.py`**: Catalog index builder.
* **`log.py`**: Timeline ledger logger.
* **`init.py`**: Topic initialization.
* **`ingest.py`**: Stage-by-stage ingestion review/apply flow.
* **`query.py`**: Analysing queries and filing durable responses.
* **`lint.py`**: Reconciliation maintenance loop.

However, the production repository contains several critical production-grade additions that we simplified or omitted to keep the walkthrough focused on core engineering concepts.

---

## Key Production Differences

### 1. LangSmith Context Hub Synchronization
In our walkthrough stages, the runner operates strictly on local directory structures (`topic_dir`). 
In the production repository:
* The runner pulls the current workspace state from **LangSmith Context Hub** using the CLI (`langsmith hub pull`).
* The agent performs its calculations inside the virtual sandbox.
* The runner pushes the updated wiki directories back to the Hub using `langsmith hub push`.
* This sync cycle creates versioned snapshots of the knowledge base, enabling remote teams to review agent updates, comment, and collaborate.

### 2. Internal Source Verification (`init.py`)
To prevent data leaks, the production repository restricts hub push and pull operations to repositories marked as `source=internal` (i.e. hosted natively by LangSmith rather than external Git repositories).
* During `init`, the runner queries the `/api/v1/repos` endpoints using `langsmith api` to verify source metadata.
* It parses the API JSON payload to ensure the repo is indeed internal, refusing to operate on external source repositories.

### 3. File System Sanitization and Security
The production repository has strict security policies to prevent malicious source files or prompt-injected tool calls from escaping the sandbox:
* **Symlink Rejection** (`_ensure_no_symlinks`): The workspace scanner recursively walks files and immediately aborts if any symlinks are detected, blocking directory traversal attacks.
* **Text-only Enforcement** (`_validate_text_only_directory`): The runner verifies that all files are valid UTF-8 text with allowed text suffixes (`.md`, `.txt`, `.json`, `.yaml`, `.yml`, `.csv`) before pushing to the hub, preventing binary file exploits.
* **Safe Writers** (`_safe_write_text`): Uses `os.open` with specific flags (like `O_NOFOLLOW`) to ensure file writers do not write to target symlinks.

### 4. Sandbox Configurations
The production runner supports environment variable overrides to customize the LangSmith sandbox:
* `WIKI_SANDBOX_SNAPSHOT` (defaults to `"deepagents-wiki"`)
* `WIKI_SANDBOX_IMAGE` (defaults to `"python:3"`)
* `WIKI_SANDBOX_FS_CAPACITY_BYTES` (defaults to 16GB)

---

## Architectural Lessons

1. **State as a Filesystem**: By treating directories (`/raw/`, `/wiki/`) as input/output interfaces, the LLM can use standard file tools (like reading and writing) instead of custom API integrations. This keeps the agent tools simple and framework-agnostic.
2. **Ledgers Provide History**: The transaction log is a crucial engineering pattern. By forcing the host runner to maintain `/log.md`, the agent gets temporal continuity without context window bloat.
3. **Failsafe Permissions**: System prompts are not security barriers. Restricting model writes at the tool/backend layer (`CompositeBackend` routing with `FilesystemPermission` rules) is the only reliable way to prevent data corruption.
4. **Self-Filing Cache**: Saving answers to past queries as standard markdown files in the folder database creates a self-reinforcing knowledge loop where past work is naturally indexed and discoverable.
