"""Knowledge Base CLI Tool for MTF_AI_Trade.

Supports creating new self-contained experiment records in
03_KNOWLEDGE/experiments/<N>-<slug>/ and validating their completeness.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from datetime import datetime
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXP_ROOT = PROJECT_ROOT / "03_KNOWLEDGE" / "experiments"
KNOW_ROOT = PROJECT_ROOT / "03_KNOWLEDGE" / "knowledge"


def cmd_new(args: argparse.Namespace) -> int:
    """Create a new experiment record skeleton."""
    issue_no = args.issue
    slug = args.slug.lower().replace("_", "-")
    exp_dir_name = f"{issue_no}-{slug}"
    exp_dir = EXP_ROOT / exp_dir_name

    if exp_dir.exists():
        print(f"[Error] Experiment directory already exists: {exp_dir}", file=sys.stderr)
        return 1

    exp_dir.mkdir(parents=True, exist_ok=True)
    (exp_dir / "artifacts").mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    title = args.title or slug.replace("-", " ").title()

    # 1. config.yaml
    config_data = {
        "issue": issue_no,
        "title": title,
        "created_at": today,
        "symbol": "BTCUSD",
        "timeframe": "1h",
        "dataset_partition": "Discovery (2020-2023)",
        "cost_model": "SPEC-EVAL-001 (0.40% round-trip)",
        "parameters": {},
    }
    with open(exp_dir / "config.yaml", "w", encoding="utf-8") as f:
        yaml.dump(config_data, f, default_flow_style=False, sort_keys=False, allow_unicode=True)

    # 2. run.py
    run_code = f'''"""Experiment simulation script for Issue #{issue_no}: {title}."""

from __future__ import annotations

import json
from pathlib import Path
import yaml
from src.data_loader import load_discovery_data
from src.evaluation import evaluate_returns, evaluate_yearly_breakdown

EXP_DIR = Path(__file__).resolve().parent

def main() -> None:
    # 1. Load config
    with open(EXP_DIR / "config.yaml", "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    symbol = config.get("symbol", "BTCUSD")
    timeframe = config.get("timeframe", "1h")

    # 2. Load Discovery data
    print(f"Loading {{symbol}} {{timeframe}} data...")
    df = load_discovery_data(symbol, timeframe)
    print(f"Data range: {{df.index.min()}} to {{df.index.max()}} ({{len(df)}} bars)")

    # 3. Execute strategy / analysis logic
    # TODO: Implement experiment logic here
    # Example dummy forward returns for illustration:
    returns = df["Close"].pct_change().dropna()

    # 4. Evaluate metrics (SPEC-EVAL-001)
    metrics = evaluate_returns(returns)
    yearly = evaluate_yearly_breakdown(returns)

    print("\\nEvaluation Metrics:")
    for k, v in metrics.items():
        print(f"  {{k}}: {{v}}")

    print("\\nYearly Breakdown:")
    print(yearly)

    # 5. Save metrics
    with open(EXP_DIR / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\\nSaved metrics to {{EXP_DIR / 'metrics.json'}}")

if __name__ == "__main__":
    main()
'''
    with open(exp_dir / "run.py", "w", encoding="utf-8") as f:
        f.write(run_code)

    # 3. record.md
    record_md = f"""# 実験記録: {title}

**Issue:** [#{issue_no}](https://github.com/makagi/MTF_AI_Trade/issues/{issue_no})  
**Date:** {today}  
**Status:** In Progress <!-- Supported | Refuted | Inconclusive -->  

---

## 1. 事前登録仮説 & 判定基準（Analysis Issue より転記）

### 仮説
<!-- Issue の仮説を記載 -->

### 事前登録判定基準 (SPEC-EVAL-001 準拠)
<!-- 往復 0.40% コスト控除後期待値、年別安定性などの基準を記載 -->

---

## 2. 実験結果

* **サンプル数 ($N$):** 
* **コスト控除後期待値 (Net Mean Return):** 
* **勝率 (Win Rate):** 
* **最大ドローダウン (Max Drawdown):** 

### 年別パフォーマンス推移
<!-- 年別オーバーレイ結果の考察 -->

---

## 3. 考察と結論

<!-- 支持 / 反証の判定根拠 -->

## 4. 知識系譜への登録要否

* **知識 ID 候補:** `K-xxx`
* **仕様への昇格提案:** 
"""
    with open(exp_dir / "record.md", "w", encoding="utf-8") as f:
        f.write(record_md)

    print(f"[Success] Created experiment directory: {exp_dir}")
    print(f"  - {exp_dir / 'config.yaml'}")
    print(f"  - {exp_dir / 'run.py'}")
    print(f"  - {exp_dir / 'record.md'}")
    print(f"  - {exp_dir / 'artifacts'}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    """List all registered experiments."""
    if not EXP_ROOT.exists():
        print("No experiments found.")
        return 0

    exp_dirs = [d for d in sorted(EXP_ROOT.iterdir()) if d.is_dir()]
    if not exp_dirs:
        print("No experiments found.")
        return 0

    print(f"Registered Experiments ({len(exp_dirs)}):")
    for d in exp_dirs:
        record_file = d / "record.md"
        status = "Unknown"
        if record_file.exists():
            for line in record_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("**Status:**"):
                    status = line.replace("**Status:**", "").strip()
                    break
        print(f"  - {d.name} [Status: {status}]")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate all experiment directories for required files."""
    if not EXP_ROOT.exists():
        print("[Pass] No experiments to validate.")
        return 0

    exp_dirs = [d for d in sorted(EXP_ROOT.iterdir()) if d.is_dir()]
    errors = 0
    for d in exp_dirs:
        required = ["config.yaml", "run.py", "record.md"]
        for req in required:
            if not (d / req).exists():
                print(f"[Error] {d.name} is missing {req}", file=sys.stderr)
                errors += 1

    if errors == 0:
        print(f"[Pass] All {len(exp_dirs)} experiments are valid.")
        return 0
    else:
        print(f"[Fail] Found {errors} validation errors.", file=sys.stderr)
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Knowledge Base CLI for MTF_AI_Trade")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # new
    p_new = subparsers.add_parser("new", help="Create a new experiment skeleton")
    p_new.add_argument("issue", type=int, help="Analysis Issue number")
    p_new.add_argument("slug", type=str, help="Short slug for the experiment (e.g. sma-mean-reversion)")
    p_new.add_argument("--title", type=str, default="", help="Experiment title")
    p_new.set_defaults(func=cmd_new)

    # list
    p_list = subparsers.add_parser("list", help="List experiments")
    p_list.set_defaults(func=cmd_list)

    # validate
    p_val = subparsers.add_parser("validate", help="Validate experiments")
    p_val.set_defaults(func=cmd_validate)

    args = parser.parse_args()
    code = args.func(args)
    sys.exit(code)


if __name__ == "__main__":
    main()
