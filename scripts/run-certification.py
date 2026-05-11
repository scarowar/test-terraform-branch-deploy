#!/usr/bin/env python3
"""Run release certification checks in severity order."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Stage:
    """A certification stage."""

    name: str
    command: list[str]
    mutates_github: bool = False


LOCAL_STAGES = [
    Stage(
        name="local-contract",
        command=[
            "uv",
            "run",
            "pytest",
            "tests/test_release_contract.py",
            "tests/test_runner_mocked.py",
        ],
    ),
]

LIVE_STAGES = [
    Stage(
        name="critical",
        command=["uv", "run", "pytest", "tests/e2e", "-m", "critical", "--maxfail=1"],
        mutates_github=True,
    ),
    Stage(
        name="core",
        command=[
            "uv",
            "run",
            "pytest",
            "tests/e2e",
            "-m",
            "core and not critical and not stateful and not args and not edge",
            "--maxfail=1",
        ],
        mutates_github=True,
    ),
    Stage(
        name="stateful",
        command=[
            "uv",
            "run",
            "pytest",
            "tests/e2e",
            "-m",
            "stateful and not slow",
            "--maxfail=1",
        ],
        mutates_github=True,
    ),
    Stage(
        name="args",
        command=["uv", "run", "pytest", "tests/e2e", "-m", "args", "--maxfail=1"],
        mutates_github=True,
    ),
    Stage(
        name="edge",
        command=[
            "uv",
            "run",
            "pytest",
            "tests/e2e",
            "-m",
            "edge and not slow",
            "--maxfail=1",
        ],
        mutates_github=True,
    ),
    Stage(
        name="slow",
        command=[
            "uv",
            "run",
            "pytest",
            "tests/e2e",
            "-m",
            "slow",
            "--maxfail=1",
        ],
        mutates_github=True,
    ),
]

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run terraform-branch-deploy certification checks."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Run live E2E stages that create GitHub PRs, branches, comments, and workflow runs.",
    )
    parser.add_argument(
        "--cleanup-first",
        action="store_true",
        help="Run scripts/cleanup-e2e.py --execute before live stages.",
    )
    return parser.parse_args()


def run_stage(stage: Stage) -> None:
    """Run one stage and stop on failure."""
    print(f"\n==> {stage.name}", flush=True)
    print(" ".join(stage.command), flush=True)
    result = subprocess.run(stage.command, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def main() -> int:
    """Run certification stages."""
    args = parse_args()

    stages = list(LOCAL_STAGES)
    if args.live:
        if not os.environ.get("GITHUB_TOKEN"):
            print("GITHUB_TOKEN is required for --live certification.", file=sys.stderr)
            return 2

        if args.cleanup_first:
            run_stage(
                Stage(
                    name="cleanup",
                    command=[sys.executable, "scripts/cleanup-e2e.py", "--execute"],
                    mutates_github=True,
                )
            )
        stages.extend(LIVE_STAGES)
    elif args.cleanup_first:
        print("--cleanup-first requires --live.", file=sys.stderr)
        return 2

    for stage in stages:
        run_stage(stage)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
