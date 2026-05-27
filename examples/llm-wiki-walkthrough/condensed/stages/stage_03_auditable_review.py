"""Stage 3: Two-Phase Ingestion & Temporal Audit Logs.

This stage introduces the review-apply split for ingestion, the read-only review permissions boundary,
and the runner-managed `log.md` transaction log to provide temporal recency context.
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
import shared.log as log_helpers

_BASE_SYSTEM_PROMPT = """You are an expert research synthesizer building a long-lived topic knowledge base.

Mission:
- Build an accurate, high-signal, source-grounded topic corpus in `/wiki/`.
- Treat `/raw/` as immutable evidence inputs.

Writing and organization rules:
- Write only under `/wiki/`.
- Never write to `/raw/` or `/log.md`.
- Keep `/wiki/index.md` updated.
- Use recent `/log.md` entries as operational recency context before major synthesis.
"""

def parse_config(argv: Sequence[str] | None = None) -> RunnerConfig:
    parser = argparse.ArgumentParser(description="Stage 3: Auditable Review")
    parser.add_argument("--mode", required=True, choices=["init", "ingest"])
    parser.add_argument("--repo", required=True, help="Wiki repository name")
    parser.add_argument("--owner", default=None, help="Owner name")
    parser.add_argument("--topic-dir", default=None, help="Local directory")
    parser.add_argument("--source", action="append", default=[], help="Source note files")
    parser.add_argument("--note", default=None, help="Operator note")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--review", action="store_true", help="Enable review phase")
    
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
        review=args.review,
    )

def _permissions() -> list[FilesystemPermission]:
    """Granular write permissions for the apply phase."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
    ]

def _review_permissions() -> list[FilesystemPermission]:
    """Strict read-only permissions for the review phase."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
    ]

def run_agent_stage3(
    workspace_dir: Path,
    topic: str,
    prompt: str,
    model: str | None,
    permissions: list[FilesystemPermission]
) -> str:
    """Run agent inside virtualized sandbox backend with designated permissions."""
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
        
        backend = CompositeBackend(
            default=sandbox_backend,
            routes={
                "/raw/": workspace_backend,
                "/wiki/": workspace_backend,
                "/log.md": workspace_backend,
                "/AGENTS.md": workspace_backend,
            },
        )
        
        agent = create_deep_agent(
            model=model,
            backend=backend,
            permissions=permissions,
            system_prompt=_BASE_SYSTEM_PROMPT,
        )
        
        result = agent.invoke({"messages": [{"role": "user", "content": prompt}]})
        
        messages = result.get("messages", [])
        for msg in reversed(messages):
            if getattr(msg, "type", None) in {"ai", "assistant"}:
                content = getattr(msg, "content", "")
                if isinstance(content, str):
                    return content
        return "Completed stage 3 agent run."
    finally:
        client.delete_sandbox(sandbox.name)

def build_ingest_review_prompt(topic: str, staged_paths: Sequence[Path], note: str | None) -> str:
    source_block = "\n".join(f"- /raw/{path.name}" for path in staged_paths)
    return (
        f"Review the staged sources for topic '{topic}' and prepare a deep ingest plan.\n\n"
        "Phase constraint: review-only. Do not create, edit, move, or delete files yet.\n\n"
        f"Staged sources:\n{source_block}\n\n"
        f"Operator note: {note or '(none)'}\n"
    )

def build_ingest_apply_prompt(topic: str, staged_paths: Sequence[Path], review_summary: str, note: str | None) -> str:
    source_block = "\n".join(f"- /raw/{path.name}" for path in staged_paths)
    return (
        f"Apply an approved ingest update for topic '{topic}'.\n\n"
        "Required workflow:\n"
        "1) Read all staged files in `/raw/` before editing wiki content.\n"
        "2) Update canonical concept/entity/theme pages with high-signal evidence.\n"
        "3) Update `/wiki/index.md`.\n\n"
        f"Approved review plan:\n{review_summary}\n\n"
        f"Staged sources:\n{source_block}\n\n"
        f"Operator note: {note or '(none)'}\n"
    )

def run(config: RunnerConfig) -> RunResult:
    if config.mode == "init":
        config.topic_dir.mkdir(parents=True, exist_ok=True)
        (config.topic_dir / "raw").mkdir(exist_ok=True)
        (config.topic_dir / "wiki").mkdir(exist_ok=True)
        (config.topic_dir / "AGENTS.md").write_text(f"# {config.topic} rules\nRead raw, write wiki.\n")
        index_helpers.refresh_index(config.topic, config.topic_dir)
        log_helpers.append_log_entry(config.topic_dir, "init", "completed", summary="Initialized topic workspace.")
        return RunResult(answer="Initialized wiki with auditable structure.", hub_url=None)
        
    elif config.mode == "ingest":
        if not config.sources:
            raise ValueError("No sources specified for ingest.")
            
        raw_dir = config.topic_dir / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        staged = []
        for src in config.sources:
            dest = raw_dir / src.name
            shutil.copy2(src, dest)
            staged.append(dest)
            
        source_count = len(staged)
        source_hint = f"{staged[0].name}, +{source_count - 1} more" if source_count > 1 else staged[0].name
        
        if config.review:
            # 1. Review Phase (read-only)
            review_prompt = build_ingest_review_prompt(config.topic, staged, config.note)
            review_summary = run_agent_stage3(config.topic_dir, config.topic, review_prompt, config.model, _review_permissions())
            
            # Log the review outcome
            log_helpers.append_log_entry(
                config.topic_dir,
                "ingest.review",
                "completed",
                metadata={"source_count": source_count, "source_hint": source_hint},
                summary=review_summary
            )
            
            # 2. Interactive user prompt
            print(f"\nIngest review summary:\n\n{review_summary}\n")
            response = input("Apply these wiki updates now? [y/N]: ").strip().lower()
            approved = response in {"y", "yes"}
            
            if not approved:
                cancel_summary = "Operator declined apply after ingest review."
                log_helpers.append_log_entry(
                    config.topic_dir,
                    "ingest.apply",
                    "canceled",
                    metadata={"source_count": source_count, "source_hint": source_hint},
                    summary=cancel_summary
                )
                return RunResult(answer="Ingest canceled. No wiki changes were applied.", hub_url=None)
                
            apply_prompt = build_ingest_apply_prompt(config.topic, staged, review_summary, config.note)
        else:
            # Running directly without explicit review phase
            apply_prompt = build_ingest_apply_prompt(
                config.topic,
                staged,
                "No explicit review phase was run. Perform review-quality analysis and apply updates directly.",
                config.note
            )
            
        # 3. Apply Phase (write-allowed)
        apply_answer = run_agent_stage3(config.topic_dir, config.topic, apply_prompt, config.model, _permissions())
        
        # Post-process: index refresh
        index_helpers.refresh_index(config.topic, config.topic_dir)
        
        # Log the apply outcome
        log_helpers.append_log_entry(
            config.topic_dir,
            "ingest.apply",
            "applied",
            metadata={"source_count": source_count, "source_hint": source_hint},
            summary=apply_answer
        )
        
        return RunResult(answer=apply_answer, hub_url=None)
        
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
