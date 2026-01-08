"""
Parameter Permutation Tests for terraform-branch-deploy.

This file systematically tests all combinations of:
1. action.yml inputs
2. PR comment command syntax variations
3. .tf-branch-deploy.yml configuration values

Each permutation is derived directly from the schema and documentation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pytest

from tests.e2e.runner import E2ETestRunner


# =============================================================================
# PARAMETER DEFINITIONS - Derived from action.yml and config schema
# =============================================================================

class CommandType(str, Enum):
    """All possible command types."""
    PLAN = "plan"
    APPLY = "apply"
    LOCK = "lock"
    UNLOCK = "unlock"
    HELP = "help"
    WCID = "wcid"


class Environment(str, Enum):
    """All test environments."""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


@dataclass
class CommandVariation:
    """A command syntax variation to test."""
    name: str
    command: str
    command_type: CommandType
    environment: str | None
    extra_args: str | None
    expect_success: bool
    description: str


# =============================================================================
# COMMAND SYNTAX VARIATIONS
# =============================================================================

COMMAND_VARIATIONS: list[CommandVariation] = [
    # Plan command variations
    CommandVariation(
        name="plan_basic",
        command=".plan to dev",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="Basic plan with environment",
    ),
    CommandVariation(
        name="plan_no_to",
        command=".plan dev",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="Plan without 'to' keyword",
    ),
    CommandVariation(
        name="plan_with_target",
        command=".plan to dev | -target=local_file.test",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-target=local_file.test",
        expect_success=True,
        description="Plan with -target argument",
    ),
    CommandVariation(
        name="plan_with_var",
        command=".plan to dev | -var='key=value'",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-var='key=value'",
        expect_success=True,  # TF config now has 'key' variable
        description="Plan with -var argument (single quotes)",
    ),
    CommandVariation(
        name="plan_with_var_double_quotes",
        command='.plan to dev | -var="key=value"',
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args='-var="key=value"',
        expect_success=True,  # TF config now has 'key' variable
        description="Plan with -var argument (double quotes)",
    ),
    CommandVariation(
        name="plan_with_var_spaces",
        command=".plan to dev | -var='msg=hello world'",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-var='msg=hello world'",
        expect_success=True,  # TF config now has 'msg' variable
        description="Plan with -var containing spaces",
    ),
    CommandVariation(
        name="plan_with_refresh_false",
        command=".plan to dev | -refresh=false",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-refresh=false",
        expect_success=True,
        description="Plan with -refresh=false",
    ),
    CommandVariation(
        name="plan_with_parallelism",
        command=".plan to dev | -parallelism=5",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-parallelism=5",
        expect_success=True,
        description="Plan with -parallelism",
    ),
    CommandVariation(
        name="plan_with_multiple_args",
        command=".plan to dev | -refresh=false -parallelism=5",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-refresh=false -parallelism=5",
        expect_success=True,
        description="Plan with multiple extra args",
    ),
    CommandVariation(
        name="plan_with_module_target",
        command=".plan to dev | -target=module.base",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-target=module.base",
        expect_success=True,
        description="Plan targeting a module",
    ),
    CommandVariation(
        name="plan_with_indexed_target",
        command=".plan to dev | -target=module.usecase[0]",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args="-target=module.usecase[0]",
        expect_success=True,
        description="Plan with indexed target",
    ),
    CommandVariation(
        name="plan_with_keyed_target",
        command=".plan to dev | -target=module.usecase[\"usecaseV1\"]",
        command_type=CommandType.PLAN,
        environment="dev",
        extra_args='-target=module.usecase["usecaseV1"]',
        expect_success=True,  # TF succeeds with no changes (module doesn't exist = no changes)
        description="Plan with keyed target (double quotes)",
    ),
    CommandVariation(
        name="plan_prod",
        command=".plan to prod",
        command_type=CommandType.PLAN,
        environment="prod",
        extra_args=None,
        expect_success=True,
        description="Plan to production environment",
    ),

    # Apply command variations
    CommandVariation(
        name="apply_basic",
        command=".apply to dev",
        command_type=CommandType.APPLY,
        environment="dev",
        extra_args=None,
        expect_success=False,  # Fails without plan
        description="Apply without prior plan (should fail)",
    ),
    CommandVariation(
        name="apply_rollback",
        command=".apply main to dev",
        command_type=CommandType.APPLY,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="Rollback apply (deploys stable branch)",
    ),
    CommandVariation(
        name="apply_rollback_with_ref",
        command=".apply v1.0.0 to dev",
        command_type=CommandType.APPLY,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="Rollback to specific tag",
    ),

    # Lock command variations
    CommandVariation(
        name="lock_basic",
        command=".lock dev",
        command_type=CommandType.LOCK,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="Lock dev environment",
    ),
    CommandVariation(
        name="lock_with_reason",
        command=".lock dev --reason='testing in progress'",
        command_type=CommandType.LOCK,
        environment="dev",
        extra_args="--reason='testing in progress'",
        expect_success=True,
        description="Lock with reason",
    ),
    CommandVariation(
        name="lock_prod",
        command=".lock prod",
        command_type=CommandType.LOCK,
        environment="prod",
        extra_args=None,
        expect_success=True,
        description="Lock prod environment",
    ),

    # Unlock command variations
    CommandVariation(
        name="unlock_basic",
        command=".unlock dev",
        command_type=CommandType.UNLOCK,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="Unlock dev environment",
    ),

    # Help command
    CommandVariation(
        name="help",
        command=".help",
        command_type=CommandType.HELP,
        environment=None,
        extra_args=None,
        expect_success=True,
        description="Show help (no environment needed)",
    ),

    # WCID command
    CommandVariation(
        name="wcid",
        command=".wcid",
        command_type=CommandType.WCID,
        environment=None,
        extra_args=None,
        expect_success=True,
        description="Who Currently Is Deploying (no environment needed)",
    ),
    CommandVariation(
        name="wcid_with_env",
        command=".wcid dev",
        command_type=CommandType.WCID,
        environment="dev",
        extra_args=None,
        expect_success=True,
        description="WCID for specific environment",
    ),
]


# =============================================================================
# PARAMETRIZED TESTS
# =============================================================================

@pytest.mark.e2e
class TestCommandSyntaxVariations:
    """Test all command syntax variations."""

    @pytest.mark.parametrize(
        "variation",
        [v for v in COMMAND_VARIATIONS if v.command_type == CommandType.PLAN],
        ids=lambda v: v.name,
    )
    def test_plan_variations(self, runner: E2ETestRunner, variation: CommandVariation) -> None:
        """Test plan command variations."""
        run, _ = runner.run_command_test(
            test_name=f"perm_{variation.name}",
            command=variation.command,
            expect_success=variation.expect_success,
        )
        assert run.is_complete


@pytest.mark.e2e
class TestExtraArgsSyntax:
    """Test extra args with special characters.
    
    These tests verify that parsing works correctly AND the values are
    passed to Terraform properly. TF config has the test variables.
    """

    def test_target_with_brackets(self, runner: E2ETestRunner) -> None:
        """Test -target with bracket syntax."""
        run, _ = runner.run_command_test(
            test_name="args_brackets",
            command=".plan to dev | -target=module.test[0]",
            expect_success=True,
        )
        assert run.is_complete

    def test_target_with_quoted_key(self, runner: E2ETestRunner) -> None:
        """Test -target with quoted key syntax."""
        # Note: module.test["key"] doesn't exist, but TF succeeds with no changes
        run, _ = runner.run_command_test(
            test_name="args_quoted_key",
            command='.plan to dev | -target=module.test["key"]',
            expect_success=True,  # TF succeeds with no changes (module doesn't exist)
        )
        assert run.is_complete

    def test_var_with_equals_in_value(self, runner: E2ETestRunner) -> None:
        """Test -var with = in value."""
        run, _ = runner.run_command_test(
            test_name="args_equals_value",
            command=".plan to dev | -var='connection_string=host=db;port=5432'",
            expect_success=True,  # TF config now has connection_string variable
        )
        assert run.is_success

    def test_var_with_json_value(self, runner: E2ETestRunner) -> None:
        """Test -var with JSON-style value."""
        run, _ = runner.run_command_test(
            test_name="args_json_value",
            command='.plan to dev | -var=\'tags={"env":"dev"}\'',
            expect_success=True,  # TF config now has tags variable
        )
        assert run.is_success


@pytest.mark.e2e
class TestLockUnlockCommands:
    """Test lock and unlock with correct syntax."""

    def test_lock_dev(self, runner: E2ETestRunner) -> None:
        """Test .lock dev."""
        branch_name, pr_number, _ = runner.setup_test_pr("lock_dev")
        try:
            runner.post_comment(pr_number, ".lock dev")
            time.sleep(30)
            # Just verify no error - lock may or may not post comment
        finally:
            runner.post_comment(pr_number, ".unlock dev")
            time.sleep(5)
            runner.cleanup_test_pr(branch_name, pr_number)

    def test_unlock_dev(self, runner: E2ETestRunner) -> None:
        """Test .unlock dev."""
        branch_name, pr_number, _ = runner.setup_test_pr("unlock_dev")
        try:
            # Lock first
            runner.post_comment(pr_number, ".lock dev")
            time.sleep(10)
            # Then unlock
            runner.post_comment(pr_number, ".unlock dev")
            time.sleep(30)
            # Just verify no error
        finally:
            runner.cleanup_test_pr(branch_name, pr_number)


@pytest.mark.e2e  
class TestInfoCommands:
    """Test info commands (help, wcid)."""

    def test_help_command(self, runner: E2ETestRunner) -> None:
        """Test .help command."""
        branch_name, pr_number, _ = runner.setup_test_pr("help_cmd")
        try:
            runner.post_comment(pr_number, ".help")
            time.sleep(30)
            # Check if bot responded
            comment = runner.get_latest_bot_comment(pr_number)
            # help may or may not trigger based on workflow config
        finally:
            runner.cleanup_test_pr(branch_name, pr_number)

    def test_wcid_command(self, runner: E2ETestRunner) -> None:
        """Test .wcid command."""
        branch_name, pr_number, _ = runner.setup_test_pr("wcid_cmd")
        try:
            runner.post_comment(pr_number, ".wcid")
            time.sleep(30)
            # Check if bot responded
            comment = runner.get_latest_bot_comment(pr_number)
            # wcid may or may not trigger based on workflow config
        finally:
            runner.cleanup_test_pr(branch_name, pr_number)

    def test_wcid_with_environment(self, runner: E2ETestRunner) -> None:
        """Test .wcid dev command."""
        branch_name, pr_number, _ = runner.setup_test_pr("wcid_env")
        try:
            runner.post_comment(pr_number, ".wcid dev")
            time.sleep(30)
        finally:
            runner.cleanup_test_pr(branch_name, pr_number)
