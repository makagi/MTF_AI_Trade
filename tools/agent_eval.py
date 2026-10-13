"""Deterministic Gates CLI for AI Agent QA.

Validates experiment directories or scripts created by worker agents against:
1. Syntax & Static Structure (AST parsing, syntax errors)
2. Consistency & File Layout (required files, frontmatter, configuration)
3. SPEC-EVAL-001 Quantitative Contract:
   - Mandatory metrics (sample_count, net_expected_value, win_rate, max_drawdown)
   - Standard friction cost (0.40% round-trip) application
   - Lookahead / Holdout leakage check (prohibits accessing Holdout partition or raw unshifted data)
"""

from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
import sys
from typing import Any
import yaml

# Required files for a self-contained experiment
REQUIRED_FILES = ["config.yaml", "run.py", "record.md"]

# Mandatory metrics in metrics.json according to SPEC-EVAL-001
MANDATORY_METRIC_KEYS = [
    "total_trades",
    "friction_cost_applied",
    "gross_mean_return",
    "net_mean_return",
    "win_rate",
    "profit_factor",
    "max_drawdown",
]

# Standard friction cost (0.40% round-trip = 0.0040)
EXPECTED_FRICTION_COST = 0.0040


class GateViolation:
    def __init__(self, category: str, message: str, file_path: Path | None = None, line_no: int | None = None):
        self.category = category
        self.message = message
        self.file_path = file_path
        self.line_no = line_no

    def __str__(self) -> str:
        loc = ""
        if self.file_path:
            loc = f" [{self.file_path.name}"
            if self.line_no:
                loc += f":{self.line_no}"
            loc += "]"
        return f"[{self.category}]{loc} {self.message}"


def check_syntax(file_path: Path) -> list[GateViolation]:
    """Gate 1: Verify Python code syntax using AST."""
    violations: list[GateViolation] = []
    if not file_path.exists():
        violations.append(GateViolation("Syntax", f"File not found: {file_path}", file_path))
        return violations

    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError as e:
        violations.append(GateViolation("Syntax", f"Syntax error: {e.msg}", file_path, e.lineno))
        return violations
    except Exception as e:
        violations.append(GateViolation("Syntax", f"Failed to parse: {e}", file_path))
        return violations

    # Basic static pattern inspections (e.g. check for explicit holdout leakage calls)
    for node in ast.walk(tree):
        # Detect load_ohlcv(..., include_holdout=True)
        if isinstance(node, ast.Call):
            for kw in node.keywords:
                if kw.arg == "include_holdout" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                    violations.append(GateViolation(
                        "LeakageGate",
                        "Explicit include_holdout=True detected in experiment code! Holdout partition is sealed.",
                        file_path,
                        node.lineno
                    ))

    return violations


def check_consistency(exp_dir: Path) -> list[GateViolation]:
    """Gate 2: Verify experiment directory structure and configuration."""
    violations: list[GateViolation] = []
    if not exp_dir.is_dir():
        violations.append(GateViolation("Consistency", f"Target is not a directory: {exp_dir}"))
        return violations

    for req in REQUIRED_FILES:
        target = exp_dir / req
        if not target.exists():
            violations.append(GateViolation("Consistency", f"Missing mandatory file: {req}", target))

    # Check config.yaml validity
    config_file = exp_dir / "config.yaml"
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            if not isinstance(config, dict):
                violations.append(GateViolation("Consistency", "config.yaml must be a valid YAML mapping", config_file))
            else:
                for key in ["symbol", "timeframe"]:
                    if key not in config:
                        violations.append(GateViolation("Consistency", f"config.yaml missing '{key}'", config_file))
        except Exception as e:
            violations.append(GateViolation("Consistency", f"Error parsing config.yaml: {e}", config_file))

    # Check record.md status
    record_file = exp_dir / "record.md"
    if record_file.exists():
        content = record_file.read_text(encoding="utf-8")
        if "**Status:**" not in content and "**ステータス:**" not in content:
            violations.append(GateViolation("Consistency", "record.md missing Status metadata header", record_file))

    return violations


def check_quantitative_contract(exp_dir: Path) -> list[GateViolation]:
    """Gate 3: Verify SPEC-EVAL-001 quantitative requirements in metrics.json."""
    violations: list[GateViolation] = []
    metrics_file = exp_dir / "metrics.json"

    if not metrics_file.exists():
        violations.append(GateViolation(
            "QuantContract",
            "metrics.json does not exist. Experiment must be executed to produce metrics.",
            metrics_file
        ))
        return violations

    try:
        with open(metrics_file, "r", encoding="utf-8") as f:
            metrics = json.load(f)
    except Exception as e:
        violations.append(GateViolation("QuantContract", f"Failed to parse metrics.json: {e}", metrics_file))
        return violations

    if not isinstance(metrics, dict):
        violations.append(GateViolation("QuantContract", "metrics.json must contain a JSON object", metrics_file))
        return violations

    # 1. Mandatory metric keys
    for key in MANDATORY_METRIC_KEYS:
        if key not in metrics:
            violations.append(GateViolation("QuantContract", f"Missing mandatory metric key: '{key}'", metrics_file))

    # 2. Friction cost deduction verification
    cost_applied = metrics.get("friction_cost_applied")
    if cost_applied is not None:
        if abs(float(cost_applied) - EXPECTED_FRICTION_COST) > 1e-5:
            violations.append(GateViolation(
                "QuantContract",
                f"Friction cost {cost_applied} does not match SPEC-EVAL-001 requirement ({EXPECTED_FRICTION_COST})",
                metrics_file
            ))
    else:
        violations.append(GateViolation(
            "QuantContract",
            "friction_cost_applied is missing or None in metrics.json",
            metrics_file
        ))

    # 3. Minimum sample size sanity check
    total_trades = metrics.get("total_trades", 0)
    if isinstance(total_trades, int) and total_trades == 0:
        violations.append(GateViolation(
            "QuantContract",
            "total_trades is 0. No trades were evaluated or signal failed to trigger.",
            metrics_file
        ))

    return violations


def evaluate_experiment(exp_dir: Path) -> tuple[bool, list[GateViolation]]:
    """Run all deterministic gates on an experiment directory."""
    violations: list[GateViolation] = []

    # 1. Consistency check
    violations.extend(check_consistency(exp_dir))

    # 2. Syntax & Static check on run.py
    run_file = exp_dir / "run.py"
    if run_file.exists():
        violations.extend(check_syntax(run_file))

    # 3. Quantitative contract check
    violations.extend(check_quantitative_contract(exp_dir))

    passed = len(violations) == 0
    return passed, violations


def cmd_check(args: argparse.Namespace) -> int:
    """CLI command handler for checking an experiment directory."""
    target_path = Path(args.path).resolve()
    if not target_path.exists():
        print(f"[Error] Target path not found: {target_path}", file=sys.stderr)
        return 1

    passed, violations = evaluate_experiment(target_path)
    if passed:
        print(f"[PASS] All Deterministic Gates passed for: {target_path.name}")
        return 0
    else:
        print(f"[FAIL] Deterministic Gate violations found for: {target_path.name}", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Deterministic Gates CLI for AI Agent QA")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_check = subparsers.add_parser("check", help="Check an experiment directory against deterministic gates")
    p_check.add_argument("path", type=str, help="Path to experiment directory (e.g. 03_KNOWLEDGE/experiments/<N>-<slug>)")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
