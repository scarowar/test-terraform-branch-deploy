"""
Comprehensive E2E Test Scenarios for terraform-branch-deploy.

Derived from source code analysis of:
- cli.py: Modes, commands, operations, environment validation
- executor.py: init/plan/apply, tfcmt, exit codes, var-files
- action.yml: All inputs and configuration options
- config.py: Config parsing, inheritance, resolution

This file defines all test scenarios organized by feature area.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


class Category(str, Enum):
    """Test categories derived from source code modules."""

    # From cli.py
    CLI_MODES = "cli_modes"                    # parse, execute, dispatch
    CLI_OPERATIONS = "cli_operations"          # plan, apply
    CLI_ENVIRONMENT = "cli_environment"        # validation, resolution
    CLI_EXTRA_ARGS = "cli_extra_args"          # shlex parsing
    CLI_ROLLBACK = "cli_rollback"              # TF_BD_IS_ROLLBACK
    CLI_CHECKSUM = "cli_checksum"              # TF_BD_PLAN_CHECKSUM

    # From executor.py
    EXECUTOR_INIT = "executor_init"            # terraform init
    EXECUTOR_PLAN = "executor_plan"            # terraform plan with exit codes
    EXECUTOR_APPLY = "executor_apply"          # terraform apply
    EXECUTOR_TFCMT = "executor_tfcmt"          # PR comment integration
    EXECUTOR_VAR_FILES = "executor_var_files"  # -var-file handling
    EXECUTOR_BACKEND = "executor_backend"       # -backend-config handling

    # From action.yml
    ACTION_DISPATCH = "action_dispatch"        # Full dispatch mode
    ACTION_EXECUTE = "action_execute"          # Execute mode
    ACTION_TRIGGERS = "action_triggers"        # .plan, .apply, .lock, etc.
    ACTION_LOCKING = "action_locking"          # Lock/unlock/wcid
    ACTION_HOOKS = "action_hooks"              # pre-terraform-hook
    ACTION_CACHING = "action_caching"          # Plan file caching
    ACTION_SAFETY = "action_safety"            # checks, permissions, rollback

    # From config.py
    CONFIG_PARSING = "config_parsing"          # YAML loading
    CONFIG_INHERITANCE = "config_inheritance"  # defaults inheritance
    CONFIG_VALIDATION = "config_validation"    # schema validation

    # Edge cases
    EDGE_CASES = "edge_cases"                  # Boundary conditions
    CHAOS = "chaos"                            # Failure recovery


@dataclass
class TestScenario:
    """A test scenario derived from source code."""

    name: str
    category: TestCategory
    description: str
    source_file: str                           # Source file this tests
    source_lines: str                          # Line numbers in source
    command: str                               # PR comment or CLI command
    expect_success: bool = True
    expect_in_logs: list[str] = field(default_factory=list)
    expect_in_comment: list[str] = field(default_factory=list)
    setup: str | None = None                   # Setup steps
    edge_case: bool = False


# =============================================================================
# CLI.PY TESTS - Derived from cli.py source code
# =============================================================================

CLI_MODE_TESTS = [
    # From cli.py lines 35-41: Mode enum
    TestScenario(
        name="dispatch_mode_default",
        category=TestCategory.CLI_MODES,
        description="Dispatch mode is default and handles full flow",
        source_file="cli.py",
        source_lines="35-41",
        command=".plan to dev",
        expect_success=True,
    ),
    TestScenario(
        name="execute_mode_explicit",
        category=TestCategory.CLI_MODES,
        description="Execute mode runs terraform only",
        source_file="cli.py",
        source_lines="109-126",
        command="tf-branch-deploy execute --environment dev --operation plan --sha abc123",
        expect_success=True,
    ),
    TestScenario(
        name="parse_mode_outputs_config",
        category=TestCategory.CLI_MODES,
        description="Parse mode outputs config without running TF",
        source_file="cli.py",
        source_lines="57-106",
        command="tf-branch-deploy parse --environment dev",
        expect_success=True,
        expect_in_logs=["working_directory", "var_files"],
    ),
]

CLI_OPERATION_TESTS = [
    # From cli.py lines 224-276: Plan and Apply operations
    TestScenario(
        name="plan_operation",
        category=TestCategory.CLI_OPERATIONS,
        description="Plan operation runs terraform plan",
        source_file="cli.py",
        source_lines="225-234",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["Terraform Plan"],
    ),
    TestScenario(
        name="apply_operation_with_plan",
        category=TestCategory.CLI_OPERATIONS,
        description="Apply uses cached plan file",
        source_file="cli.py",
        source_lines="235-271",
        command=".apply to dev",
        expect_success=True,
        expect_in_logs=["Found plan file"],
        setup="Run .plan to dev first",
    ),
    TestScenario(
        name="apply_without_plan_fails",
        category=TestCategory.CLI_OPERATIONS,
        description="Apply fails without prior plan",
        source_file="cli.py",
        source_lines="260-264",
        command=".apply to dev",
        expect_success=False,
        expect_in_logs=["No plan file found"],
    ),
    TestScenario(
        name="unknown_operation_fails",
        category=TestCategory.CLI_OPERATIONS,
        description="Unknown operation name fails",
        source_file="cli.py",
        source_lines="272-274",
        command="--operation invalid",
        expect_success=False,
        expect_in_logs=["Unknown operation"],
    ),
]

CLI_ENVIRONMENT_TESTS = [
    # From cli.py lines 84-86, 150-152: Environment validation
    TestScenario(
        name="valid_environment",
        category=TestCategory.CLI_ENVIRONMENT,
        description="Valid environment name works",
        source_file="cli.py",
        source_lines="84-86",
        command=".plan to dev",
        expect_success=True,
    ),
    TestScenario(
        name="invalid_environment_fails",
        category=TestCategory.CLI_ENVIRONMENT,
        description="Invalid environment name fails with error",
        source_file="cli.py",
        source_lines="150-152",
        command=".plan to nonexistent",
        expect_success=False,
        expect_in_logs=["not found"],
    ),
    TestScenario(
        name="production_environment_detection",
        category=TestCategory.CLI_ENVIRONMENT,
        description="Production environments are detected",
        source_file="cli.py",
        source_lines="104",
        command=".plan to prod",
        expect_success=True,
        expect_in_logs=["is_production=true"],
    ),
]

CLI_EXTRA_ARGS_TESTS = [
    # From cli.py lines 157-166: Extra args parsing
    TestScenario(
        name="extra_args_target",
        category=TestCategory.CLI_EXTRA_ARGS,
        description="-target argument passed through",
        source_file="cli.py",
        source_lines="157-166",
        command=".plan to dev | -target=local_file.test",
        expect_success=True,
        expect_in_logs=["Extra args"],
    ),
    TestScenario(
        name="extra_args_var",
        category=TestCategory.CLI_EXTRA_ARGS,
        description="-var argument passed through",
        source_file="cli.py",
        source_lines="157-166",
        command=".plan to dev | -var='key=value'",
        expect_success=True,
    ),
    TestScenario(
        name="extra_args_multiple",
        category=TestCategory.CLI_EXTRA_ARGS,
        description="Multiple extra args work",
        source_file="cli.py",
        source_lines="185-186",
        command=".plan to dev | -refresh=false -parallelism=5",
        expect_success=True,
    ),
    TestScenario(
        name="extra_args_with_quotes",
        category=TestCategory.CLI_EXTRA_ARGS,
        description="Quoted args handled by shlex",
        source_file="cli.py",
        source_lines="162-165",
        command=".plan to dev | -var='message=hello world'",
        expect_success=True,
        edge_case=True,
    ),
]

CLI_ROLLBACK_TESTS = [
    # From cli.py lines 241-259: Rollback detection
    TestScenario(
        name="rollback_bypasses_plan",
        category=TestCategory.CLI_ROLLBACK,
        description="Rollback applies without plan file",
        source_file="cli.py",
        source_lines="241-259",
        command=".apply main to dev",
        expect_success=True,
        expect_in_logs=["Rollback detected"],
    ),
    TestScenario(
        name="rollback_env_var",
        category=TestCategory.CLI_ROLLBACK,
        description="TF_BD_IS_ROLLBACK env var triggers rollback",
        source_file="cli.py",
        source_lines="243",
        command=".apply to dev",  # With TF_BD_IS_ROLLBACK=true
        expect_success=True,
        setup="Set TF_BD_IS_ROLLBACK=true",
    ),
]

CLI_CHECKSUM_TESTS = [
    # From cli.py lines 247-254: Checksum verification
    TestScenario(
        name="checksum_verified",
        category=TestCategory.CLI_CHECKSUM,
        description="Plan checksum is verified before apply",
        source_file="cli.py",
        source_lines="247-254",
        command=".apply to dev",
        expect_success=True,
        expect_in_logs=["checksum verified"],
        setup="Run .plan first, checksum is stored",
    ),
    TestScenario(
        name="checksum_mismatch_fails",
        category=TestCategory.CLI_CHECKSUM,
        description="Checksum mismatch fails apply",
        source_file="cli.py",
        source_lines="251-253",
        command=".apply to dev",
        expect_success=False,
        expect_in_logs=["checksum mismatch"],
        setup="Tamper with plan file after planning",
        edge_case=True,
    ),
]

# =============================================================================
# EXECUTOR.PY TESTS - Derived from executor.py source code
# =============================================================================

EXECUTOR_INIT_TESTS = [
    # From executor.py lines 108-129: terraform init
    TestScenario(
        name="init_success",
        category=TestCategory.EXECUTOR_INIT,
        description="Terraform init succeeds",
        source_file="executor.py",
        source_lines="108-129",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["Init successful"],
    ),
    TestScenario(
        name="init_with_backend_config",
        category=TestCategory.EXECUTOR_INIT,
        description="Backend configs passed to init",
        source_file="executor.py",
        source_lines="114-116",
        command=".plan to dev",
        expect_success=True,
    ),
    TestScenario(
        name="init_failure_stops_execution",
        category=TestCategory.EXECUTOR_INIT,
        description="Init failure prevents plan/apply",
        source_file="executor.py",
        source_lines="125-127",
        command=".plan to dev",  # With broken backend
        expect_success=False,
        expect_in_logs=["Init failed"],
        edge_case=True,
    ),
]

EXECUTOR_PLAN_TESTS = [
    # From executor.py lines 131-192: terraform plan
    TestScenario(
        name="plan_no_changes",
        category=TestCategory.EXECUTOR_PLAN,
        description="Plan with no changes (exit code 0)",
        source_file="executor.py",
        source_lines="164-169",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["no changes"],
    ),
    TestScenario(
        name="plan_with_changes",
        category=TestCategory.EXECUTOR_PLAN,
        description="Plan with changes (exit code 2)",
        source_file="executor.py",
        source_lines="164-169",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["with changes"],
    ),
    TestScenario(
        name="plan_error",
        category=TestCategory.EXECUTOR_PLAN,
        description="Plan error (exit code 1)",
        source_file="executor.py",
        source_lines="174-176",
        command=".plan to dev",  # With TF syntax error
        expect_success=False,
        expect_in_logs=["Plan failed"],
    ),
    TestScenario(
        name="plan_creates_checksum",
        category=TestCategory.EXECUTOR_PLAN,
        description="Plan file checksum is calculated",
        source_file="executor.py",
        source_lines="178-182",
        command=".plan to dev",
        expect_success=True,
    ),
    TestScenario(
        name="plan_with_var_files",
        category=TestCategory.EXECUTOR_VAR_FILES,
        description="Var files passed to plan",
        source_file="executor.py",
        source_lines="148-150",
        command=".plan to dev",
        expect_success=True,
    ),
]

EXECUTOR_APPLY_TESTS = [
    # From executor.py lines 194-234: terraform apply
    TestScenario(
        name="apply_with_plan_file",
        category=TestCategory.EXECUTOR_APPLY,
        description="Apply uses plan file",
        source_file="executor.py",
        source_lines="208-209",
        command=".apply to dev",
        expect_success=True,
        setup="Run .plan first",
    ),
    TestScenario(
        name="apply_direct",
        category=TestCategory.EXECUTOR_APPLY,
        description="Direct apply without plan file (rollback)",
        source_file="executor.py",
        source_lines="210-215",
        command=".apply main to dev",
        expect_success=True,
    ),
    TestScenario(
        name="apply_success",
        category=TestCategory.EXECUTOR_APPLY,
        description="Apply succeeds",
        source_file="executor.py",
        source_lines="223-224",
        command=".apply to dev",
        expect_success=True,
        expect_in_logs=["Apply successful"],
        setup="Run .plan first",
    ),
    TestScenario(
        name="apply_failure",
        category=TestCategory.EXECUTOR_APPLY,
        description="Apply fails with error",
        source_file="executor.py",
        source_lines="225-227",
        command=".apply to dev",
        expect_success=False,
        expect_in_logs=["Apply failed"],
        edge_case=True,
    ),
]

EXECUTOR_TFCMT_TESTS = [
    # From executor.py lines 236-265: tfcmt integration
    TestScenario(
        name="tfcmt_posts_comment",
        category=TestCategory.EXECUTOR_TFCMT,
        description="tfcmt posts plan output to PR",
        source_file="executor.py",
        source_lines="248-265",
        command=".plan to dev",
        expect_success=True,
        expect_in_comment=["Plan", "to add", "to change"],
    ),
    TestScenario(
        name="tfcmt_fallback",
        category=TestCategory.EXECUTOR_TFCMT,
        description="Falls back to direct execution without tfcmt",
        source_file="executor.py",
        source_lines="250-252",
        command=".plan to dev",
        expect_success=True,
    ),
]

# =============================================================================
# ACTION.YML TESTS - Derived from action.yml inputs
# =============================================================================

ACTION_TRIGGER_TESTS = [
    # From action.yml lines 62-79: Trigger commands
    TestScenario(
        name="plan_trigger",
        category=TestCategory.ACTION_TRIGGERS,
        description=".plan command triggers plan",
        source_file="action.yml",
        source_lines="65-66",
        command=".plan to dev",
        expect_success=True,
    ),
    TestScenario(
        name="apply_trigger",
        category=TestCategory.ACTION_TRIGGERS,
        description=".apply command triggers apply",
        source_file="action.yml",
        source_lines="62-64",
        command=".apply to dev",
        expect_success=True,
        setup="Run .plan first",
    ),
    TestScenario(
        name="help_trigger",
        category=TestCategory.ACTION_TRIGGERS,
        description=".help shows available commands",
        source_file="action.yml",
        source_lines="74-75",
        command=".help",
        expect_success=True,
    ),
]

ACTION_LOCKING_TESTS = [
    # From action.yml lines 68-79: Lock commands
    TestScenario(
        name="lock_command",
        category=TestCategory.ACTION_LOCKING,
        description=".lock locks environment",
        source_file="action.yml",
        source_lines="68-70",
        command=".lock dev",
        expect_success=True,
        expect_in_comment=["lock"],
    ),
    TestScenario(
        name="unlock_command",
        category=TestCategory.ACTION_LOCKING,
        description=".unlock releases lock",
        source_file="action.yml",
        source_lines="71-73",
        command=".unlock dev",
        expect_success=True,
    ),
    TestScenario(
        name="wcid_command",
        category=TestCategory.ACTION_LOCKING,
        description=".wcid shows who is deploying",
        source_file="action.yml",
        source_lines="77-79",
        command=".wcid",
        expect_success=True,
    ),
]

ACTION_HOOK_TESTS = [
    # From action.yml lines 48-53: Pre-terraform hook
    TestScenario(
        name="hook_executes",
        category=TestCategory.ACTION_HOOKS,
        description="Pre-terraform hook runs before TF",
        source_file="action.yml",
        source_lines="48-53",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["Pre-Terraform Hook"],
    ),
    TestScenario(
        name="hook_has_env_vars",
        category=TestCategory.ACTION_HOOKS,
        description="Hook has TF_BD_* env vars",
        source_file="action.yml",
        source_lines="52",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["TF_BD_ENVIRONMENT"],
    ),
    TestScenario(
        name="hook_failure_stops_execution",
        category=TestCategory.ACTION_HOOKS,
        description="Hook failure prevents terraform",
        source_file="action.yml",
        source_lines="48-53",
        command=".plan to dev",  # With failing hook
        expect_success=False,
        edge_case=True,
    ),
]

ACTION_CACHING_TESTS = [
    # From action.yml: Plan file caching
    TestScenario(
        name="plan_file_cached",
        category=TestCategory.ACTION_CACHING,
        description="Plan file is cached after plan",
        source_file="action.yml",
        source_lines="375-380",
        command=".plan to dev",
        expect_success=True,
        expect_in_logs=["Cache"],
    ),
    TestScenario(
        name="plan_file_restored",
        category=TestCategory.ACTION_CACHING,
        description="Plan file restored for apply",
        source_file="action.yml",
        source_lines="375-380",
        command=".apply to dev",
        expect_success=True,
        expect_in_logs=["Cache hit"],
        setup="Run .plan first",
    ),
]

# =============================================================================
# EDGE CASES - Boundary conditions and error scenarios
# =============================================================================

EDGE_CASE_TESTS = [
    TestScenario(
        name="empty_config_file",
        category=TestCategory.EDGE_CASES,
        description="Empty config file fails gracefully",
        source_file="config.py",
        source_lines="260-261",
        command=".plan to dev",  # With empty config
        expect_success=False,
        edge_case=True,
    ),
    TestScenario(
        name="missing_config_file",
        category=TestCategory.EDGE_CASES,
        description="Missing config file fails with clear error",
        source_file="cli.py",
        source_lines="77-79, 143-145",
        command=".plan to dev",  # Without config
        expect_success=False,
        expect_in_logs=["not found"],
        edge_case=True,
    ),
    TestScenario(
        name="sha_change_invalidates_plan",
        category=TestCategory.EDGE_CASES,
        description="New commit requires new plan",
        source_file="cli.py",
        source_lines="238-240",
        command=".apply to dev",  # After new commit
        expect_success=False,
        expect_in_logs=["No plan file found"],
        edge_case=True,
    ),
    TestScenario(
        name="concurrent_deployments",
        category=TestCategory.EDGE_CASES,
        description="Concurrent deploys handled safely",
        source_file="action.yml",
        source_lines="68-70",  # Locking
        command=".plan to dev",
        expect_success=True,
        edge_case=True,
    ),
    TestScenario(
        name="very_long_plan_output",
        category=TestCategory.EDGE_CASES,
        description="Long plan output handled",
        source_file="executor.py",
        source_lines="158-162",
        command=".plan to dev",  # With many resources
        expect_success=True,
        edge_case=True,
    ),
    TestScenario(
        name="unicode_in_terraform",
        category=TestCategory.EDGE_CASES,
        description="Unicode in TF output handled",
        source_file="executor.py",
        source_lines="101-105",
        command=".plan to dev",
        expect_success=True,
        edge_case=True,
    ),
    TestScenario(
        name="special_chars_in_env_name",
        category=TestCategory.EDGE_CASES,
        description="Environment names with special chars",
        source_file="config.py",
        source_lines="142-159",
        command=".plan to dev-us-east-1",
        expect_success=True,
        edge_case=True,
    ),
    TestScenario(
        name="symlinks_in_working_dir",
        category=TestCategory.EDGE_CASES,
        description="Symlinks resolved correctly",
        source_file="cli.py",
        source_lines="155",
        command=".plan to dev",
        expect_success=True,
        edge_case=True,
    ),
]


# =============================================================================
# ALL SCENARIOS
# =============================================================================

ALL_SCENARIOS = (
    CLI_MODE_TESTS +
    CLI_OPERATION_TESTS +
    CLI_ENVIRONMENT_TESTS +
    CLI_EXTRA_ARGS_TESTS +
    CLI_ROLLBACK_TESTS +
    CLI_CHECKSUM_TESTS +
    EXECUTOR_INIT_TESTS +
    EXECUTOR_PLAN_TESTS +
    EXECUTOR_APPLY_TESTS +
    EXECUTOR_TFCMT_TESTS +
    ACTION_TRIGGER_TESTS +
    ACTION_LOCKING_TESTS +
    ACTION_HOOK_TESTS +
    ACTION_CACHING_TESTS +
    EDGE_CASE_TESTS
)


def get_scenarios_by_category(category: TestCategory) -> list[TestScenario]:
    """Get all scenarios for a specific category."""
    return [s for s in ALL_SCENARIOS if s.category == category]


def get_edge_case_scenarios() -> list[TestScenario]:
    """Get all edge case scenarios."""
    return [s for s in ALL_SCENARIOS if s.edge_case]


def print_coverage_summary() -> None:
    """Print test coverage summary."""
    from collections import Counter
    categories = Counter(s.category.value for s in ALL_SCENARIOS)

    print("=" * 60)
    print("E2E TEST COVERAGE SUMMARY")
    print("=" * 60)
    print(f"Total scenarios: {len(ALL_SCENARIOS)}")
    print(f"Edge cases: {len(get_edge_case_scenarios())}")
    print()
    print("By Category:")
    for cat, count in sorted(categories.items()):
        print(f"  {cat}: {count}")
    print("=" * 60)


if __name__ == "__main__":
    print_coverage_summary()
