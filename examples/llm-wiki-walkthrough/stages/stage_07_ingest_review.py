"""Stage 07 — two-phase ingest with operator approval.

By stage 06 query has a conditional second phase. Ingest is still
single-phase write-immediately. Bad ingests are expensive: a
misread source can corrupt half a dozen canonical wiki pages
before anyone sees the change. The pressure isn't model
correctness in the abstract — it's *recoverability* for the
operator who has to review wiki updates.

Fix: a *review*-then-*apply* shape, mirroring query but with a
human in the middle. The review phase uses a fully-read-only
permission profile so the planning step cannot accidentally write.
On approval, the runner re-invokes with the normal apply
permission set and the review summary in-context.

The two-phase shape is opt-in via `--review`. Direct apply is
still the default for trusted ingests.
"""

from __future__ import annotations

import shutil
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemPermission

from shared.model import model_or_skip

WORKSPACE = Path(__file__).resolve().parent / "_stage07_workspace"
SAMPLE_SRC = Path(__file__).resolve().parents[1] / "shared" / "sample_source.md"


def ensure_scaffold(workspace: Path) -> None:
    (workspace / "raw").mkdir(parents=True, exist_ok=True)
    (workspace / "wiki").mkdir(parents=True, exist_ok=True)
    shutil.copy(SAMPLE_SRC, workspace / "raw" / "ada.md")


def apply_permissions() -> list[FilesystemPermission]:
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="allow"),
    ]


def review_permissions() -> list[FilesystemPermission]:
    """Review pass cannot write anywhere — pure planning."""
    return [
        FilesystemPermission(operations=["write"], paths=["/raw/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/wiki/**"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/log.md"], mode="deny"),
        FilesystemPermission(operations=["write"], paths=["/AGENTS.md"], mode="deny"),
    ]


def ingest_review_prompt(source_names: list[str]) -> str:
    sources = "\n".join(f"- /raw/{name}" for name in source_names)
    return (
        "Plan an ingest. Review-only — do not write any files.\n"
        "Required sections in your reply:\n"
        "## 1) Source extraction\n## 2) Proposed wiki change set\n"
        "## 3) Contradictions and unresolved claims\n"
        f"Staged sources:\n{sources}\n"
    )


def ingest_apply_prompt(source_names: list[str], review_summary: str) -> str:
    sources = "\n".join(f"- /raw/{name}" for name in source_names)
    return (
        "Apply the approved ingest plan below. Update canonical /wiki/ "
        "pages. Never write /raw/ or /log.md.\n\n"
        f"Approved review plan:\n{review_summary}\n\nStaged sources:\n{sources}\n"
    )


def confirm(review_summary: str, ask: Callable[[str], str]) -> bool:
    prompt = (
        "Ingest review summary:\n\n"
        f"{review_summary.strip()}\n\n"
        "Apply these wiki updates now? [y/N]: "
    )
    return ask(prompt).strip().lower() in {"y", "yes"}


def run_ingest(
    workspace: Path,
    source_names: list[str],
    *,
    review: bool,
    ask: Callable[[str], str] = input,
) -> str:
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)

    if review:
        review_agent = create_deep_agent(
            model=model_or_skip("stage 07 review-phase wiring"),
            backend=backend,
            permissions=review_permissions(),
            system_prompt="You are a research synthesizer planning an ingest.",
        )
        _ = review_agent
        # Wiring-only canned plan:
        review_summary = (
            "## 1) Source extraction\nKey claim: Note G (1843).\n\n"
            "## 2) Proposed wiki change set\n- update /wiki/ada-lovelace.md\n\n"
            "## 3) Contradictions and unresolved claims\nNone.\n"
        )
        print("[stage 07][review] plan generated; requesting operator approval...")  # noqa: T201
        approved = confirm(review_summary, ask)
        if not approved:
            print("[stage 07][apply] operator declined; no wiki writes.")  # noqa: T201
            return "canceled"
    else:
        review_summary = "(no explicit review phase)"

    apply_agent = create_deep_agent(
        model=model_or_skip("stage 07 apply-phase wiring"),
        backend=backend,
        permissions=apply_permissions(),
        system_prompt="You are a research synthesizer applying an ingest.",
    )
    _ = apply_agent
    # Wiring-only: simulate the page the agent would write.
    (workspace / "wiki" / "ada-lovelace.md").write_text(
        "# Ada Lovelace\n\n- Wrote Note G in 1843.\n- Predicted general-purpose computing.\n"
    )
    print("[stage 07][apply] wrote /wiki/ada-lovelace.md")  # noqa: T201
    return "applied"


def main() -> None:
    ensure_scaffold(WORKSPACE)
    # Default: apply directly, trusting the source.
    run_ingest(WORKSPACE, ["ada.md"], review=False)
    # Opt-in: --review. Auto-approve so the demo is non-interactive.
    run_ingest(WORKSPACE, ["ada.md"], review=True, ask=lambda _prompt: "y")


if __name__ == "__main__":
    main()
