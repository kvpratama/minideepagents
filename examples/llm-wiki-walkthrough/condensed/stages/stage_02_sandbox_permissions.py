"""Stage 2: Sandbox Isolation and Failsafe Permissions.

This stage wraps the agent with a CompositeBackend, FilesystemBackend, and strict
FilesystemPermission rules, preventing unauthorized edits. It also introduces
automated index catalog building.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Sequence

# Add deepagents repo path to sys.path
sys.path.append(str(Path(__file__).parent.parent.parent))

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, FilesystemBackend, LangSmithSandbox
from deepagents.middleware.filesystem import FilesystemPermission

from shared.models import RunnerConfig, RunResult
import shared.index as index_helpers

_BASE_SYSTEM_PROMPT = """You are a research synthesizer.
Your task is to read files in `/raw/` and synthesize them into knowledge pages in `/wiki/`.

Writing and organization rules:
- Write only under `/wiki/`.
- Never write to `/raw/`.
- Keep `/wiki/index.md` updated as a content catalog.
"""

def parse_config(argv: Sequence[str] | None = None) -> RunnerConfig:
    parser = argparse.ArgumentParser(description="Stage 2: Sandbox Permissions")
    parser.add_argument("--mode", required=True, choices=["init", "ingest"])
    parser.add_argument("--repo", required=True, help="Wiki repository name")
    parser.add_argument("--owner", default=None, help="Owner name")
    parser.add_argument("--topic-dir", default=None, help="Local directory")
    parser.add_argument("--source", action="append", default=[], help="Source note files")
    parser.add_argument("--note", default=None, help="Operator note")
    parser.add_argument("--model", default=None, help="Model override")
    
    args = parser.parse_args(argv)
    topic = args.repo.replace("-", " ").title()
    topic_dir = Path(args.topic_dir or f"./wikis/{args.repo}").resolve()
    
    return RunnerConfig(
        mode=args.mode,
        topic=topic,
        repo=args.repo,
        owner=args.owner,
        topic_dir=topic_dir,
        sources=tuple(Path(s).resolve() for s in args.source),
        note=args.note,
        question=None,
        model=args.model,
        description=None,
        review=False,
    )

def _permissions() -> list[FilesystemPermission]:
    """Define failsafe filesystem write policy."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]

def run_agent_stage2(workspace_dir: Path, topic: str, prompt: str, model: str | None) -> str:
    """Run agent inside virtualized sandbox backend with restricted permissions."""
    env_key = os.getenv("LANGSMITH_API_KEY")
    if not env_key:
        raise RuntimeError("LANGSMITH_API_KEY is required for sandbox execution.")

    from langsmith.sandbox import SandboxClient
    client = SandboxClient(api_key=env_key)
    
    snapshots = client.list_snapshots(name_contains="deepagents-wiki")
    if not any(s.name == "deepagents-wiki" and s.status == "ready" for s in snapshots):
        client.create_snapshot(
            name="deepagents-wiki",
            docker_image="python:3",
            fs_capacity_bytes=16 * 1024**3,
        )

    sandbox = client.create_sandbox(snapshot_name="deepagents-wiki")
    try:
        sandbox_backend = LangSmithSandbox(sandbox=sandbox)
        workspace_backend = FilesystemBackend(root_dir=workspace_dir, virtual_mode=True)
        
        # Virtual filesystem mapping
        backend = CompositeBackend(
            default=sandbox_backend,
            routes={
                "/raw/": workspace_backend,
                "/wiki/": workspace_backend,
                "/AGENTS.md": workspace_backend,
            },
        )
        
        agent = create_deep_agent(
            model=model,
            backend=backend,
            permissions=_permissions(),
            system_prompt=_BASE_SYSTEM_PROMPT,
        )
        
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if getattr(msg, "type", None) in {"ai", "assistant"}:
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    return content
        return "Completed stage 2 agent run."
    finally:
        client.delete_sandbox(sandbox.name)

def run(config: RunnerConfig) -> RunResult:
    if config.mode == "init":
        config.topic_dir.mkdir(parents=True, exist_ok=True)
        (config.topic_dir / "raw").mkdir(exist_ok=True)
        (config.topic_dir / "wiki").mkdir(exist_ok=True)
        (config.topic_dir / "AGENTS.md").write_text(f"# {config.topic} rules\nRead raw, write wiki.\n")
        # Initialize default empty index
        index_helpers.refresh_index(config.topic, config.topic_dir)
        return RunResult(answer="Initialized wiki with sandbox structure.", hub_url=None)
        
    elif config.mode == "ingest":
        if not config.sources:
            raise ValueError("No sources specified for ingest.")
            
        raw_dir = config.topic_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        staged = []
        for src in config.sources:
            dest = raw_dir / src.name
            shutil.copy2(src, dest)
            staged.append(f"/raw/{src.name}")
            
        prompt = (
            f"Read the following new files: {', '.join(staged)}.\n"
            f"Write synthesized markdown summaries directly into `/wiki/`.\n"
            f"Operator note: {config.note or 'none'}"
        )
        
        answer = run_agent_stage2(config.topic_dir, config.topic, prompt, config.model)
        
        # Automatically rebuild/refresh index.md
        index_helpers.refresh_index(config.topic, config.topic_dir)
        
        return RunResult(answer=answer, hub_url=None)
        
    raise ValueError(f"Unsupported mode: {config.mode}")

def main() -> int:
    try:
        config = parse_config()
        result = run(config)
        if result.answer:
            print(result.answer)
        return 0
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
