#!/usr/bin/env python
"""
Lightweight Web Server for System Trade Knowledge Base
------------------------------------------------------
Serves the Knowledge Base Web UI and REST API without heavy external dependencies.
Supports Floorp Browser Web Panels and Extensions via CORS.
"""

import os
import sys
import json
import urllib.parse
import subprocess
from pathlib import Path
from http.server import HTTPServer, SimpleHTTPRequestHandler

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KB_ROOT = PROJECT_ROOT / "knowledge"
WEB_DIR = KB_ROOT / "web"
INDEX_FILE = KB_ROOT / "index.json"
LINEAGE_FILE = KB_ROOT / "LINEAGE.md"

class KnowledgeRequestHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        # Enable CORS for browser extensions and external panels (e.g. Floorp)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        # REST API routing
        if path == "/api/status":
            self.send_json({"status": "ok", "project": "SakanaAISystemTrade Knowledge Base"})
            return

        if path == "/api/records":
            self.handle_api_records()
            return

        if path.startswith("/api/records/"):
            analysis_id = path.replace("/api/records/", "").strip()
            self.handle_api_record_detail(analysis_id)
            return

        if path == "/api/lineage":
            self.handle_api_lineage()
            return

        # Static assets routing:
        # 1. /records/... -> serve directly from knowledge/records/...
        if path.startswith("/records/"):
            rel_path = path.lstrip("/")
            target_file = KB_ROOT / rel_path
            if target_file.exists() and target_file.is_file():
                self.serve_file(target_file)
                return

        # 2. Everything else -> serve from knowledge/web/ (SPA)
        if path == "/" or path == "/index.html":
            self.serve_file(WEB_DIR / "index.html", content_type="text/html")
            return

        target = WEB_DIR / path.lstrip("/")
        if target.exists() and target.is_file():
            self.serve_file(target)
            return

        # Fallback to index.html for SPA routing
        self.serve_file(WEB_DIR / "index.html", content_type="text/html")

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        path = url.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            data = json.loads(body)
        except Exception:
            data = {}

        if path == "/api/records/new":
            self.handle_post_new_record(data)
            return

        if path == "/api/index":
            self.handle_post_reindex()
            return

        if path.startswith("/api/records/") and path.endswith("/run"):
            # /api/records/<id>/run
            parts = path.split("/")
            analysis_id = parts[3]
            self.handle_post_run_record(analysis_id)
            return

        self.send_error(404, "Endpoint not found")

    # ==========================================================================
    # API Handlers
    # ==========================================================================

    def send_json(self, data: dict, status_code: int = 200):
        res_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(res_bytes)))
        self.end_headers()
        self.wfile.write(res_bytes)

    def serve_file(self, file_path: Path, content_type: str = None):
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404, "File not found")
            return

        suffix = file_path.suffix.lower()
        content_type_map = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".svg": "image/svg+xml",
            ".md": "text/markdown; charset=utf-8",
        }
        ct = content_type or content_type_map.get(suffix, "application/octet-stream")

        file_bytes = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(file_bytes)))
        self.end_headers()
        self.wfile.write(file_bytes)

    def handle_api_records(self):
        if INDEX_FILE.exists():
            try:
                data = json.loads(INDEX_FILE.read_text(encoding="utf-8"))
                self.send_json(data)
                return
            except Exception as e:
                self.send_json({"error": f"Failed to read index: {e}"}, 500)
                return
        self.send_json({"version": 1, "total_records": 0, "records": []})

    def handle_api_record_detail(self, analysis_id: str):
        # Search record directory
        found_dir = None
        for rdir in (KB_ROOT / "records").glob(f"*/{analysis_id}_*"):
            if rdir.is_dir():
                found_dir = rdir
                break
        if not found_dir:
            # Try exact id match
            for rdir in (KB_ROOT / "records").glob(f"*/{analysis_id}"):
                if rdir.is_dir():
                    found_dir = rdir
                    break

        if not found_dir:
            self.send_json({"error": f"Record {analysis_id} not found"}, 404)
            return

        record_md = (found_dir / "record.md").read_text(encoding="utf-8") if (found_dir / "record.md").exists() else ""
        config_yaml = (found_dir / "config.yaml").read_text(encoding="utf-8") if (found_dir / "config.yaml").exists() else ""
        metrics_json = {}
        if (found_dir / "metrics.json").exists():
            try:
                metrics_json = json.loads((found_dir / "metrics.json").read_text(encoding="utf-8"))
            except Exception:
                pass

        artifacts = []
        art_dir = found_dir / "artifacts"
        if art_dir.exists():
            rel_art_base = art_dir.relative_to(KB_ROOT).as_posix()
            for f in sorted(art_dir.glob("*.*")):
                artifacts.append({
                    "name": f.name,
                    "url": f"/{rel_art_base}/{f.name}",
                    "size": f.stat().st_size
                })

        detail = {
            "analysis_id": analysis_id,
            "path": found_dir.relative_to(KB_ROOT).as_posix(),
            "record_md": record_md,
            "config_yaml": config_yaml,
            "metrics": metrics_json,
            "artifacts": artifacts,
        }
        self.send_json(detail)

    def handle_api_lineage(self):
        if LINEAGE_FILE.exists():
            content = LINEAGE_FILE.read_text(encoding="utf-8")
            # Extract mermaid block
            import re
            m = re.search(r"```mermaid\n(.*?)\n```", content, re.DOTALL)
            mermaid_code = m.group(1) if m else content
            self.send_json({"mermaid": mermaid_code, "raw": content})
        else:
            self.send_json({"mermaid": "graph TD\n    NoRecords[No Records Yet]", "raw": ""})

    def handle_post_new_record(self, data: dict):
        title = data.get("title", "New Analysis")
        symbol = data.get("symbol", "BTCUSD")
        timeframe = data.get("timeframe", "1h")
        slug = data.get("slug", "analysis")
        derived_from = data.get("derived_from")

        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "tools" / "kb.py"),
            "new",
            "--title", title,
            "--symbol", symbol,
            "--timeframe", timeframe,
            "--slug", slug,
        ]
        if derived_from:
            cmd.extend(["--derived-from", derived_from])

        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if proc.returncode == 0:
            # Rebuild index automatically
            subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "kb.py"), "index"], cwd=str(PROJECT_ROOT))
            self.send_json({"status": "success", "message": proc.stdout})
        else:
            self.send_json({"status": "error", "message": proc.stderr}, 500)

    def handle_post_reindex(self):
        proc = subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "kb.py"), "index"],
                              capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if proc.returncode == 0:
            self.send_json({"status": "success", "message": proc.stdout})
        else:
            self.send_json({"status": "error", "message": proc.stderr}, 500)

    def handle_post_run_record(self, analysis_id: str):
        found_dir = None
        for rdir in (KB_ROOT / "records").glob(f"*/{analysis_id}_*"):
            if rdir.is_dir():
                found_dir = rdir
                break
        if not found_dir:
            self.send_json({"error": f"Record {analysis_id} not found"}, 404)
            return

        run_py = found_dir / "run.py"
        if not run_py.exists():
            self.send_json({"error": f"run.py not found in {analysis_id}"}, 400)
            return

        # Execute using uv or python
        proc = subprocess.run(["uv", "run", "python", str(run_py)],
                              capture_output=True, text=True, cwd=str(PROJECT_ROOT))
        if proc.returncode == 0:
            # Reindex
            subprocess.run([sys.executable, str(PROJECT_ROOT / "tools" / "kb.py"), "index"], cwd=str(PROJECT_ROOT))
            self.send_json({"status": "success", "output": proc.stdout})
        else:
            self.send_json({"status": "error", "output": proc.stderr or proc.stdout}, 500)


def run_server(port: int = 8765):
    server_address = ("", port)
    httpd = HTTPServer(server_address, KnowledgeRequestHandler)
    print(f"==================================================")
    print(f" Knowledge Base Web Server is running!")
    print(f" URL: http://localhost:{port}")
    print(f" Floorp Web Panel: Add 'http://localhost:{port}' to sidebar")
    print(f"==================================================")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        httpd.server_close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8765
    run_server(port)
