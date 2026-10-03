#!/usr/bin/env python
"""
Knowledge Base Management CLI for System Trade
----------------------------------------------
Provides commands to manage Analysis Records, maintain Knowledge Lineage,
and build AI-searchable indexes.
"""

import os
import sys
import re
import json
import glob
import argparse
from datetime import datetime
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

# Root paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = PROJECT_ROOT / "knowledge"
RECORDS_ROOT = KB_ROOT / "records"
DATASETS_ROOT = KB_ROOT / "datasets"
TEMPLATES_ROOT = KB_ROOT / "templates"
INDEX_FILE = KB_ROOT / "index.json"
LINEAGE_FILE = KB_ROOT / "LINEAGE.md"


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter from markdown content."""
    pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(pattern, content, re.DOTALL)
    if not match:
        return {}
    yaml_text = match.group(1)
    if yaml:
        try:
            return yaml.safe_load(yaml_text) or {}
        except Exception as e:
            print(f"[Warning] Failed to parse YAML frontmatter: {e}", file=sys.stderr)
            return {}
    else:
        # Fallback simple parser
        data = {}
        for line in yaml_text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                k, v = line.split(":", 1)
                data[k.strip()] = v.strip().strip('"').strip("'")
        return data


def get_all_records() -> list[dict]:
    """Scan all record.md files and return parsed metadata and paths."""
    records = []
    if not RECORDS_ROOT.exists():
        return records

    for md_path in sorted(RECORDS_ROOT.glob("*/*/record.md")):
        record_dir = md_path.parent
        content = md_path.read_text(encoding="utf-8")
        fm = parse_frontmatter(content)
        if not fm:
            continue

        rel_path = record_dir.relative_to(KB_ROOT).as_posix()
        fm["path"] = rel_path
        fm["_abs_dir"] = str(record_dir)
        records.append(fm)

    return records


def get_all_datasets() -> dict:
    """Load all dataset definition yaml files."""
    datasets = {}
    if not DATASETS_ROOT.exists():
        return datasets

    for yaml_path in sorted(DATASETS_ROOT.glob("*.yaml")):
        if yaml:
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
                ds_id = data.get("dataset_id", yaml_path.stem)
                datasets[ds_id] = data
            except Exception as e:
                print(f"[Warning] Failed to load dataset {yaml_path}: {e}", file=sys.stderr)
    return datasets


# ==============================================================================
# Commands
# ==============================================================================

def cmd_new(args):
    """Create a new Analysis Record directory from template."""
    now = datetime.now()
    today_str = now.strftime("%Y%m%d")
    month_dir = RECORDS_ROOT / now.strftime("%Y-%m")
    month_dir.mkdir(parents=True, exist_ok=True)

    # Find next sequence number for today
    existing = list(RECORDS_ROOT.glob(f"*/ANL-{today_str}-*"))
    seq = len(existing) + 1
    analysis_id = f"ANL-{today_str}-{seq:03d}"

    slug = args.slug.strip().lower().replace(" ", "_")
    slug = re.sub(r"[^a-z0-9_]", "", slug)
    if not slug:
        slug = "analysis"

    target_dir = month_dir / f"{analysis_id}_{slug}"
    if target_dir.exists():
        print(f"Error: Target directory already exists: {target_dir}", file=sys.stderr)
        sys.exit(1)

    target_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir = target_dir / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)

    # Load template
    template_file = TEMPLATES_ROOT / "record_template.md"
    if template_file.exists():
        tpl = template_file.read_text(encoding="utf-8")
    else:
        tpl = "---\nanalysis_id: {analysis_id}\ntitle: \"{title}\"\n---\n# {title}\n"

    # Fill template variables
    derived_from_list = f"[{args.derived_from}]" if args.derived_from else "[]"
    doc = tpl.format(
        analysis_id=analysis_id,
        title=args.title,
        symbol=args.symbol,
        timeframe=args.timeframe,
        dataset_id=args.dataset,
        start_date=args.start_date,
        end_date=args.end_date,
        finding_id=f"FIND-{analysis_id.replace('ANL-', '')}-01",
        hypothesis_id=f"HYP-{analysis_id.replace('ANL-', '')}-01",
    )
    if args.derived_from:
        doc = doc.replace("derived_from: []", f"derived_from:\n  - {args.derived_from}")

    (target_dir / "record.md").write_text(doc, encoding="utf-8")

    # Generate initial config.yaml
    config_content = {
        "analysis_id": analysis_id,
        "symbol": args.symbol,
        "timeframe": args.timeframe,
        "dataset_id": args.dataset,
        "period": {
            "start": args.start_date,
            "end": args.end_date,
        },
        "parameters": {},
    }
    if yaml:
        with open(target_dir / "config.yaml", "w", encoding="utf-8") as f:
            yaml.dump(config_content, f, sort_keys=False)
    else:
        (target_dir / "config.yaml").write_text(json.dumps(config_content, indent=2), encoding="utf-8")

    # Generate initial run.py stub
    run_py_code = f'''"""
Reproduction script for {analysis_id}
Title: {args.title}
"""
import sys
import json
import platform
from pathlib import Path
from datetime import datetime

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[4]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# from src.data_loader import load_discovery_data

def main():
    print(f"Running analysis {analysis_id}...")
    
    # 1. Load configuration
    record_dir = Path(__file__).resolve().parent
    # with open(record_dir / "config.yaml") as f:
    #     config = yaml.safe_load(f)
    
    # 2. Execute analysis logic here
    # ...
    sample_count = 0
    metrics_result = {{
        "win_rate": 0.0,
        "expectancy": 0.0,
    }}
    
    # 3. Save metrics with execution info
    output = {{
        "analysis_id": "{analysis_id}",
        "dataset_id": "{args.dataset}",
        "sample_count": sample_count,
        "metrics": metrics_result,
        "execution": {{
            "python": platform.python_version(),
            "executed_at": datetime.now().astimezone().isoformat(),
        }}
    }}
    
    metrics_file = record_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"Metrics saved to {{metrics_file}}")

if __name__ == "__main__":
    main()
'''
    (target_dir / "run.py").write_text(run_py_code, encoding="utf-8")

    print(f"[Success] Created Analysis Record: {analysis_id}")
    print(f"  Path: {target_dir}")
    print(f"  Next step: Edit {target_dir / 'record.md'} and implement {target_dir / 'run.py'}")


def cmd_list(args):
    """List all registered Analysis Records."""
    records = get_all_records()
    if not records:
        print("No Analysis Records found.")
        return

    print(f"{'ID':<18} {'Symbol':<8} {'TF':<5} {'Status':<10} {'Derived From':<16} {'Title'}")
    print("-" * 80)
    for r in records:
        aid = r.get("analysis_id", "N/A")
        sym = r.get("symbol", "")
        tf = r.get("timeframe", "")
        status = r.get("status", "")
        derived = r.get("derived_from", [])
        derived_str = ",".join(derived) if isinstance(derived, list) and derived else "-"
        title = r.get("title", "")
        print(f"{aid:<18} {sym:<8} {tf:<5} {status:<10} {derived_str:<16} {title}")


def cmd_index(args):
    """Scan all records and generate index.json and LINEAGE.md."""
    records = get_all_records()
    datasets = get_all_datasets()

    # 1. Build index.json
    clean_records = []
    for r in records:
        clean = {
            "analysis_id": r.get("analysis_id"),
            "title": r.get("title"),
            "symbol": r.get("symbol"),
            "timeframe": r.get("timeframe"),
            "period": r.get("period", {}),
            "dataset_id": r.get("dataset_id"),
            "status": r.get("status"),
            "findings": r.get("findings", []),
            "hypotheses": r.get("hypotheses", []),
            "derived_from": r.get("derived_from", []),
            "related": r.get("related", []),
            "path": r.get("path"),
        }
        clean_records.append(clean)

    index_data = {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(),
        "total_records": len(clean_records),
        "records": clean_records,
    }

    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index_data, f, indent=2, ensure_ascii=False)
    print(f"[Success] Generated {INDEX_FILE} ({len(clean_records)} records)")

    # 2. Build LINEAGE.md
    lineage_lines = [
        "# Knowledge Lineage & Hypothesis Graph",
        "",
        "> This document is automatically generated by `tools/kb.py index`. Do not edit directly.",
        "",
        "```mermaid",
        "graph TD",
    ]

    for r in clean_records:
        aid = r["analysis_id"]
        title = (r["title"] or "").replace('"', "'")
        node_id = aid.replace("-", "_")
        lineage_lines.append(f'    {node_id}["{aid}<br/>{title}"]')

        # Connect derived_from
        for p in r.get("derived_from", []):
            parent_node = p.replace("-", "_")
            lineage_lines.append(f"    {parent_node} -->|derived| {node_id}")

        # Connect findings
        for f in r.get("findings", []):
            f_node = f.replace("-", "_")
            lineage_lines.append(f'    {f_node}["{f}"]')
            lineage_lines.append(f"    {node_id} -->|discovered| {f_node}")
            lineage_lines.append(f"    style {f_node} fill:#f9f,stroke:#333")

        # Connect hypotheses
        for h in r.get("hypotheses", []):
            h_node = h.replace("-", "_")
            lineage_lines.append(f'    {h_node}["{h}"]')
            lineage_lines.append(f"    {node_id} -->|leads_to| {h_node}")
            lineage_lines.append(f"    style {h_node} fill:#bbf,stroke:#333")

    lineage_lines.append("```")
    lineage_lines.append("")

    with open(LINEAGE_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lineage_lines))
    print(f"[Success] Generated {LINEAGE_FILE}")


def cmd_validate(args):
    """Validate all Analysis Records and report issues."""
    records = get_all_records()
    datasets = get_all_datasets()
    errors = 0
    warnings = 0

    known_ids = set()

    for r in records:
        aid = r.get("analysis_id")
        dir_path = Path(r["_abs_dir"])

        # Check ID format
        if not aid or not re.match(r"^ANL-\d{8}-\d{3}$", aid):
            print(f"[Error] Invalid analysis_id format '{aid}' in {dir_path}")
            errors += 1
        elif aid in known_ids:
            print(f"[Error] Duplicate analysis_id '{aid}' in {dir_path}")
            errors += 1
        else:
            known_ids.add(aid)

        # Check required fields
        for field in ["title", "symbol", "timeframe", "dataset_id", "status"]:
            if not r.get(field):
                print(f"[Error] Missing required field '{field}' in {aid}")
                errors += 1

        # Check required files
        for fname in ["record.md", "config.yaml", "run.py"]:
            if not (dir_path / fname).exists():
                print(f"[Error] Missing required file '{fname}' in {dir_path}")
                errors += 1

        # Check dataset reference
        ds_id = r.get("dataset_id")
        if ds_id and ds_id not in datasets:
            print(f"[Warning] dataset_id '{ds_id}' in {aid} not found in knowledge/datasets/")
            warnings += 1

        # Check metrics.json
        if not (dir_path / "metrics.json").exists():
            print(f"[Warning] metrics.json not yet generated in {aid} (run run.py to create)")
            warnings += 1

    # Check derived_from references
    for r in records:
        aid = r.get("analysis_id")
        for p in r.get("derived_from", []):
            if p not in known_ids:
                print(f"[Warning] derived_from '{p}' referenced by {aid} does not exist in records")
                warnings += 1

    print("-" * 50)
    print(f"Validation complete: {len(records)} records checked. Errors: {errors}, Warnings: {warnings}")
    if errors > 0:
        sys.exit(1)


def cmd_web(args):
    """Start local web server and open browser."""
    import webbrowser
    from tools.web_server import run_server

    port = args.port
    url = f"http://localhost:{port}"

    if not args.no_open:
        def _open():
            import time
            time.sleep(0.5)
            try:
                webbrowser.open(url)
            except Exception:
                pass
        import threading
        threading.Thread(target=_open, daemon=True).start()

    run_server(port)


def main():
    parser = argparse.ArgumentParser(description="System Trade Knowledge Base CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # new
    p_new = subparsers.add_parser("new", help="Create a new Analysis Record")
    p_new.add_argument("--title", required=True, help="Analysis title")
    p_new.add_argument("--symbol", default="BTCUSD", help="Symbol (e.g. BTCUSD)")
    p_new.add_argument("--timeframe", default="1h", help="Timeframe (e.g. 1h, 1m)")
    p_new.add_argument("--dataset", default="BTCUSD_1H_DISCOVERY", help="Dataset ID")
    p_new.add_argument("--start-date", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    p_new.add_argument("--end-date", default="2023-12-31", help="End date (YYYY-MM-DD)")
    p_new.add_argument("--derived-from", default=None, help="Parent analysis ID (e.g. ANL-20260920-001)")
    p_new.add_argument("--slug", default="analysis", help="Slug for directory name")
    p_new.set_defaults(func=cmd_new)

    # list
    p_list = subparsers.add_parser("list", help="List all Analysis Records")
    p_list.set_defaults(func=cmd_list)

    # index
    p_index = subparsers.add_parser("index", help="Rebuild index.json and LINEAGE.md")
    p_index.set_defaults(func=cmd_index)

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate records and references")
    p_validate.set_defaults(func=cmd_validate)

    # web
    p_web = subparsers.add_parser("web", help="Start Knowledge Base Web UI")
    p_web.add_argument("--port", type=int, default=8765, help="Port to listen on (default: 8765)")
    p_web.add_argument("--no-open", action="store_true", help="Do not automatically open browser")
    p_web.set_defaults(func=cmd_web)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
