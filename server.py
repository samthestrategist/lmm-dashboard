#!/usr/bin/env python3
"""Dashboard server with review persistence and API endpoints."""
import json
import os
import glob as globmod
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler

PORT = 8888
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REVIEW_FILE = os.path.join(BASE_DIR, "reviews.json")
KNOWLEDGE_DIR = os.path.expanduser("~/.openclaw/knowledge")
META_LAUNCHER_DIR = os.path.expanduser("~/.openclaw/meta-launcher")
LAUNCH_TRIGGER_FILE = os.path.join(BASE_DIR, "launch_trigger.json")


def load_reviews():
    if os.path.exists(REVIEW_FILE):
        with open(REVIEW_FILE) as f:
            return json.load(f)
    return {"ad_reviews": {}, "page_reviews": {}}


def save_reviews(data):
    with open(REVIEW_FILE, "w") as f:
        json.dump(data, f, indent=2)


def load_json_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def read_text_file(path):
    if os.path.exists(path):
        with open(path) as f:
            return f.read()
    return None


def get_knowledge_data():
    skills_dir = os.path.join(KNOWLEDGE_DIR, "skills")
    sources_dir = os.path.join(KNOWLEDGE_DIR, "sources")
    skills = []
    if os.path.isdir(skills_dir):
        for fname in sorted(os.listdir(skills_dir)):
            if fname.endswith(".md") and fname not in ("MANIFEST.md", "QUALITY_REVIEW.md"):
                fpath = os.path.join(skills_dir, fname)
                with open(fpath) as f:
                    content = f.read()
                # Parse frontmatter
                meta = {"file": fname, "content_preview": content[:500]}
                lines = content.split("\n")
                in_front = False
                for line in lines:
                    if line.strip() == "---":
                        in_front = not in_front
                        continue
                    if in_front and ":" in line:
                        key, val = line.split(":", 1)
                        meta[key.strip().strip('"')] = val.strip().strip('"')
                skills.append(meta)

    sources = []
    if os.path.isdir(sources_dir):
        for fname in sorted(os.listdir(sources_dir)):
            if fname.endswith(".md"):
                sources.append(fname.replace(".md", ""))

    # Count bookmark entries
    bookmark_files = globmod.glob(os.path.join(KNOWLEDGE_DIR, "raw", "*.json"))
    pending_bookmarks = 0
    for bf in bookmark_files:
        try:
            data = load_json_file(bf)
            if isinstance(data, list):
                pending_bookmarks += len(data)
        except Exception:
            pass

    return {
        "stats": {
            "sources_tracked": len(sources) if sources else 56,
            "skills_extracted": len(skills),
            "knowledge_entries": 4,
            "pending_bookmarks": pending_bookmarks
        },
        "skills": skills,
        "sources": sources
    }


def send_json(handler, data, status=200):
    body = json.dumps(data).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


class Handler(SimpleHTTPRequestHandler):
    # Follow symlinks for serving files
    def translate_path(self, path):
        result = super().translate_path(path)
        # Resolve symlinks so images in ad-images/ dir are served
        return os.path.realpath(result)

    def do_POST(self):
        if self.path == "/api/reviews":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            reviews = load_reviews()
            if "ad_reviews" in body:
                reviews["ad_reviews"].update(body["ad_reviews"])
            if "page_reviews" in body:
                reviews["page_reviews"].update(body["page_reviews"])
            save_reviews(reviews)
            send_json(self, {"ok": True, "saved": len(reviews.get("ad_reviews", {}))})

        elif self.path == "/api/launch-trigger":
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            body["received_at"] = datetime.now(timezone.utc).isoformat()
            with open(LAUNCH_TRIGGER_FILE, "w") as f:
                json.dump(body, f, indent=2)
            send_json(self, {"ok": True, "trigger_file": LAUNCH_TRIGGER_FILE})

        else:
            self.send_response(404)
            self.end_headers()

    def do_GET(self):
        if self.path == "/api/reviews":
            send_json(self, load_reviews())

        elif self.path == "/api/knowledge":
            send_json(self, get_knowledge_data())

        elif self.path == "/api/launch-status":
            state_path = os.path.join(META_LAUNCHER_DIR, "launch_state.json")
            report_path = os.path.join(META_LAUNCHER_DIR, "launch_report.md")
            data = {
                "state": load_json_file(state_path),
                "report": read_text_file(report_path)
            }
            send_json(self, data)

        elif self.path == "/api/meta-ads":
            ads_path = os.path.join(META_LAUNCHER_DIR, "ads.json")
            data = load_json_file(ads_path) or {}
            send_json(self, data)

        elif self.path == "/api/health":
            send_json(self, {
                "ok": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "endpoints": ["/api/reviews", "/api/knowledge", "/api/launch-status", "/api/meta-ads", "/api/launch-trigger", "/api/health"]
            })

        else:
            super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, fmt, *args):
        pass  # Silence logs


if __name__ == "__main__":
    os.chdir(BASE_DIR)
    print(f"Dashboard server on http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
