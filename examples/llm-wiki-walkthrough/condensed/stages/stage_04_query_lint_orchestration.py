"""Stage 4: Self-Filing Queries and Self-Healing Linting.

This stage completes the evolutionary journey by implementing query answering with auto-filing decisions
and automated linting maintenance, representing the final architectural state.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import re
from pathlib import Path
from dataclasses import dataclass
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

_QUERY_DECISION_PATTERN = re.compile(
    r"^FILING_DECISION:\s*(file|skip)\s*$", re.IGNORECASE | re.MULTILINE
)
_QUERY_REASON_PATTERN = re.compile(
    r"^FILING_REASON:\s*(.+)$", re.IGNORECASE | re.MULTILINE
)

@dataclass(frozen=True)
class QueryDecision:
    answer: str
    should_file: bool
    reason: str

def parse_config(argv: Sequence[str] | None = None) -> RunnerConfig:
    parser = argparse.ArgumentParser(description="Stage 4: Query & Lint Orchestration")
    parser.add_argument("--mode", required=True, choices=["init", "ingest", "query", "lint"])
    parser.add_argument("--repo", required=True, help="Wiki repository name")
    parser.add_argument("--owner", default=None, help="Owner name")
    parser.add_argument("--topic-dir", default=None, help="Local directory")
    parser.add_argument("--source", action="append", default=[], help="Source note files")
    parser.add_argument("--note", default=None, help="Operator note")
    parser.add_argument("--question", default=None, help="Question for query mode")
    parser.add_argument("--model", default=None, help="Model override")
    parser.add_argument("--review", action="store_true", help="Enable review phase for ingest")
    
    args = parser.parse_args(argv)
    
    if args.mode == "ingest" and not args.source:
        parser.error("--source is required in ingest mode")
    if args.mode == "query" and not args.question:
        parser.error("--question is required in query mode")
        
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
        question=args.question,
        model=args.model,
        description=None,
        review=args.review,
    )

def _permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
    ]

def _review_permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
    ]

def run_agent_stage4(
    workspace_dir: Path,
    topic: str,
    prompt: str,
    model: str | None,
    permissions: list[FilesystemPermission]
) -> str:
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
        return "Completed stage 4 agent run."
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

def build_query_prompt(topic: str, question: str) -> str:
    return (
        f"Answer this question about '{topic}': {question}\n\n"
        "This is analysis-only. Do not create, edit, move, or delete files.\n\n"
        "Required workflow:\n"
        "1) Read `/wiki/index.md` first to identify candidate pages.\n"
        "2) Read recent `/log.md` entries for recency context.\n"
        "3) Prefer checking relevant prior `/wiki/query/*.md` pages first.\n"
        "4) Read the canonical wiki pages before final synthesis.\n"
        "5) Provide a grounded answer with wiki file path citations.\n"
        "6) Decide whether this answer should be filed as a durable wiki page.\n\n"
        "Output format (exact keys):\n"
        "ANSWER:\n"
        "<markdown answer with citations>\n\n"
        "FILING_DECISION: file|skip\n"
        "FILING_REASON: <one sentence>\n"
    )

def parse_query_decision(raw_response: str) -> QueryDecision:
    response = raw_response.strip()
    decision_match = _QUERY_DECISION_PATTERN.search(response)
    reason_match = _QUERY_REASON_PATTERN.search(response)

    should_file = (
        decision_match is not None and decision_match.group(1).lower() == "file"
    )
    reason = (
        reason_match.group(1).strip()
        if reason_match is not None
        else "Decision marker missing; defaulted to skip."
    )

    answer_text = response
    if decision_match is not None:
        answer_text = response[: decision_match.start()].strip()
    if answer_text.upper().startswith("ANSWER:"):
        answer_text = answer_text[len("ANSWER:") :].strip()
    if not answer_text:
        answer_text = response or "No answer returned."

    return QueryDecision(answer=answer_text, should_file=should_file, reason=reason)

def build_query_apply_prompt(topic: str, question: str, answer_draft: str, filing_reason: str, target_path: str) -> str:
    return (
        f"File a durable query answer for topic '{topic}'.\n\n"
        f"Create or overwrite exactly: `{target_path}`\n\n"
        "Requirements:\n"
        "1) Write a clean, scannable markdown page at the target path.\n"
        "2) Include these sections: `Question`, `Answer`, and `Sources`.\n\n"
        f"Filing reason: {filing_reason}\n\n"
        f"Question: {question}\n\n"
        f"Answer draft:\n{answer_draft}\n"
    )

def build_lint_prompt(topic: str, note: str | None) -> str:
    return (
        f"Run a single-pass lint reconciliation for the '{topic}' wiki under `/wiki/`.\n\n"
        "Execution mode:\n"
        "- Read recent `/log.md` entries first to account for recent work.\n"
        "- Apply updates immediately in this run (no review/confirm phase).\n"
        "- Reconcile contradictions across wiki pages.\n"
        "- Detect orphan pages and fix cross-links.\n"
        "- Suggest gaps and follow-up sources.\n\n"
        "After edits, return a concise markdown report with sections:\n"
        "## Reconciled Changes\n"
        "## Remaining Gaps\n"
        "## Suggested Next Questions and Sources\n\n"
        f"Operator note: {note or '(none)'}\n"
    )

def slugify(text: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return slug.strip("-")[:80] or "query"

def run(config: RunnerConfig) -> RunResult:
    if config.mode == "init":
        config.topic_dir.mkdir(parents=True, exist_ok=True)
        (config.topic_dir / "raw").mkdir(exist_ok=True)
        (config.topic_dir / "wiki").mkdir(exist_ok=True)
        (config.topic_dir / "AGENTS.md").write_text(f"# {config.topic} rules\nRead raw, write wiki.\n")
        index_helpers.refresh_index(config.topic, config.topic_dir)
        log_helpers.append_log_entry(config.topic_dir, "init", "completed", summary="Initialized topic workspace.")
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
            staged.append(dest)
            
        source_count = len(staged)
        source_hint = f"{staged[0].name}, +{source_count - 1} more" if source_count > 1 else staged[0].name
        
        if config.review:
            review_prompt = build_ingest_review_prompt(config.topic, staged, config.note)
            review_summary = run_agent_stage4(config.topic_dir, config.topic, review_prompt, config.model, _review_permissions())
            
            log_helpers.append_log_entry(
                config.topic_dir,
                "ingest.review",
                "completed",
                metadata={"source_count": source_count, "source_hint": source_hint},
                summary=review_summary
            )
            
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
            apply_prompt = build_ingest_apply_prompt(
                config.topic,
                staged,
                "No explicit review phase was run. Perform review-quality analysis and apply updates directly.",
                config.note
            )
            
        apply_answer = run_agent_stage4(config.topic_dir, config.topic, apply_prompt, config.model, _permissions())
        index_helpers.refresh_index(config.topic, config.topic_dir)
        
        log_helpers.append_log_entry(
            config.topic_dir,
            "ingest.apply",
            "applied",
            metadata={"source_count": source_count, "source_hint": source_hint},
            summary=apply_answer
        )
        return RunResult(answer=apply_answer, hub_url=None)
        
    elif config.mode == "query":
        question = config.question or ""
        review_prompt = build_query_prompt(config.topic, question)
        review_response = run_agent_stage4(config.topic_dir, config.topic, review_prompt, config.model, _review_permissions())
        decision = parse_query_decision(review_response)
        
        log_helpers.append_log_entry(
            config.topic_dir,
            "query.review",
            "file" if decision.should_file else "skip",
            metadata={"question": question, "decision": "file" if decision.should_file else "skip"},
            summary=decision.answer
        )
        
        if not decision.should_file:
            return RunResult(answer=decision.answer, hub_url=None)
            
        # Filing phase
        target_path = f"/wiki/query/{slugify(question)}.md"
        apply_prompt = build_query_apply_prompt(config.topic, question, decision.answer, decision.reason, target_path)
        run_agent_stage4(config.topic_dir, config.topic, apply_prompt, config.model, _permissions())
        
        index_helpers.refresh_index(config.topic, config.topic_dir)
        log_helpers.append_log_entry(
            config.topic_dir,
            "query.apply",
            "filed",
            metadata={"question": question, "path": target_path},
            summary=decision.answer
        )
        return RunResult(answer=decision.answer, hub_url=None)
        
    elif config.mode == "lint":
        prompt = build_lint_prompt(config.topic, config.note)
        lint_summary = run_agent_stage4(config.topic_dir, config.topic, prompt, config.model, _permissions())
        
        index_helpers.refresh_index(config.topic, config.topic_dir)
        log_helpers.append_log_entry(
            config.topic_dir,
            "lint.apply",
            "applied",
            metadata={"note": config.note} if config.note else None,
            summary=lint_summary
        )
        return RunResult(answer=lint_summary, hub_url=None)
        
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
