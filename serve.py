"""Local preview of the built site, at the same path it will have on GitHub Pages.

    python serve.py [--port 8801] [--drafts]      then open http://127.0.0.1:8801/bedtime-manhwa-site/

Serves docs/ (or preview_drafts/ with --drafts) under the base path from site.json, so every link works exactly as it
will online. Local only (127.0.0.1). Read-only.
"""
import argparse
import json
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

HERE = Path(__file__).resolve().parent


class Handler(SimpleHTTPRequestHandler):
    base = ""

    def translate_path(self, path):
        p = urlparse(path).path
        if not p.startswith(self.base + "/") and p != self.base:
            return str(Path(self.directory) / "__nope__")
        return super().translate_path(p[len(self.base):] or "/")

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", ""):
            self.send_response(302)
            self.send_header("Location", self.base + "/")
            self.end_headers()
            return
        if p == self.base:
            self.send_response(301)
            self.send_header("Location", self.base + "/")
            self.end_headers()
            return
        target = Path(self.translate_path(self.path))
        if not target.exists() or (target.is_dir() and not (target / "index.html").exists()):
            body = (Path(self.directory) / "404.html").read_bytes()   # what Pages does for a missing page
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8801)
    ap.add_argument("--drafts", action="store_true")
    a = ap.parse_args()
    cfg = json.loads((HERE / "site.json").read_text(encoding="utf-8"))
    Handler.base = urlparse(cfg["base_url"]).path.rstrip("/")
    root = HERE / ("preview_drafts" if a.drafts else "docs")
    srv = ThreadingHTTPServer(("127.0.0.1", a.port), partial(Handler, directory=str(root)))
    print(f"serving {root.name}/ at http://127.0.0.1:{a.port}{Handler.base}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
