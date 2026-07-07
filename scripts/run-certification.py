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
        command=[
            "uv",
            "run",
            "pytest",
            "tests/e2e",
            "-m",
            "args and not critical",
            "--maxfail=1",
        ],
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


LIVE_STAGE_NAMES = tuple(stage.name for stage in LIVE_STAGES)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run terraform-branch-deploy certification checks."
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Run live E2E stages that create GitHub PRs, branches, comments, "
            "and workflow runs."
        ),
    )
    parser.add_argument(
        "--cleanup-first",
        action="store_true",
        help="Run scripts/cleanup-e2e.py --execute before live stages.",
    )
    parser.add_argument(
        "--stage",
        choices=["all", *LIVE_STAGE_NAMES],
        default="all",
        help="Live stage to run. Local contract checks always run first.",
    )
    return parser.parse_args()


def stage_command(stage: Stage) -> list[str]:
    """Return the stage command with shared pytest reporting/retry flags."""
    command = list(stage.command)
    if "pytest" not in command:
        return command
    command.append(f"--junitxml=results/{stage.name}.xml")
    # Retry only workflow-wait timeouts (runner queue spikes), never real
    # assertion failures. Each E2E test posts its own commands, so a retried
    # test is self-contained.
    command.extend(["--reruns", "1", "--only-rerun", "TimeoutError"])
    return command


def run_stage(stage: Stage) -> int:
    """Run one stage and return its exit code."""
    command = stage_command(stage)
    print(f"\n==> {stage.name}", flush=True)
    print(" ".join(command), flush=True)
    return subprocess.run(command, check=False).returncode


def main() -> int:
    """Run certification stages."""
    args = parse_args()

    if args.stage != "all" and not args.live:
        print("--stage requires --live.", file=sys.stderr)
        return 2

    stages = list(LOCAL_STAGES)
    if args.live:
        if not os.environ.get("GITHUB_TOKEN"):
            print("GITHUB_TOKEN is required for --live certification.", file=sys.stderr)
            return 2

        if args.cleanup_first:
            cleanup_rc = run_stage(
                Stage(
                    name="cleanup",
                    command=[sys.executable, "scripts/cleanup-e2e.py", "--execute"],
                    mutates_github=True,
                )
            )
            if cleanup_rc != 0:
                # Later stages would run against dirty state; stop here.
                return cleanup_rc
        stages.extend(
            stage
            for stage in LIVE_STAGES
            if args.stage == "all" or stage.name == args.stage
        )
    elif args.cleanup_first:
        print("--cleanup-first requires --live.", file=sys.stderr)
        return 2

    # Run every stage even after a failure so one transient failure does not
    # hide the results of the remaining stages, then fail with a summary.
    executed: list[str] = []
    failed: list[str] = []
    for stage in stages:
        executed.append(stage.name)
        if run_stage(stage) != 0:
            failed.append(stage.name)
            if stage.name == "local-contract":
                # The test harness itself is broken; live results would be
                # meaningless and expensive.
                break

    print("\n==> certification summary", flush=True)
    for name in executed:
        outcome = "FAILED" if name in failed else "passed"
        print(f"  {name}: {outcome}", flush=True)

    if failed:
        print(f"\n{len(failed)} stage(s) failed: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
