#!/usr/bin/env python3
"""Local page for saving a public Instagram Reel or post.

Listens on 127.0.0.1 only. A phone on the same Wi-Fi cannot reach it.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

import downloader

os.environ["YTDLP_NO_PLUGINS"] = "1"

PORT = 8766
HERE = Path(__file__).resolve().parent
PAGE = HERE / "web" / "index.html"
MAX_BODY = 32 * 1024
# The installed app on GitHub Pages. The path (/Daxtons-Life/, /testing/, /Beta/) is not part of the origin.
PAGES_ORIGIN = "https://daxtontessmer-ai.github.io"


class App:
    def __init__(self, root: Path, fetcher=None):
        self.root = Path(root).expanduser()
        self.fetcher = fetcher or downloader.download_urls
        self.jobs: dict = {}
        self.lock = threading.Lock()
        self.current: str | None = None


def library_version() -> str:
    try:
        import yt_dlp.version
        return yt_dlp.version.__version__
    except ImportError:
        return ""


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args) -> None:
            print("[instagram]", fmt % args)

        def do_OPTIONS(self) -> None:  # noqa: N802
            path = urlparse(self.path).path
            if path == "/api/health":
                self.send_response(204)
                self._cors()
                self.end_headers()
                return
            self._send_json(404, {"error": "Not found."})

        def do_GET(self) -> None:  # noqa: N802
            if not self._host_ok():
                self._send_json(403, {"error": "Open this page on the Mac, at 127.0.0.1."})
                return
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                return
            if path == "/api/health":
                self._send_json(200, {
                    "ok": True,
                    "name": "instagram-downloader",
                    "version": library_version(),
                    "ffmpeg": bool(shutil.which("ffmpeg")),
                }, cors=True)
                return
            if path.startswith("/api/jobs/") and path.endswith("/zip"):
                self._send_zip(path.split("/")[-2])
                return
            if path.startswith("/api/jobs/"):
                job_id = path.split("/")[-1]
                with app.lock:
                    job = app.jobs.get(job_id)
                if not job:
                    self._send_json(404, {"error": "That download isn't running anymore."})
                    return
                self._send_json(200, _public_job(job))
                return
            self._send_json(404, {"error": "Not found."})

        def do_POST(self) -> None:  # noqa: N802
            if not self._host_ok() or not self._origin_ok():
                self._send_json(403, {"error": "Open this page on the Mac, at 127.0.0.1."})
                return
            path = urlparse(self.path).path
            try:
                body = self._body()
            except downloader.DownloaderError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            if path == "/api/download":
                self._start(body)
                return
            if path.startswith("/api/jobs/") and path.endswith("/cancel"):
                self._cancel(path.split("/")[-2])
                return
            if path.startswith("/api/jobs/") and path.endswith("/reveal"):
                self._reveal(path.split("/")[-2])
                return
            self._send_json(404, {"error": "Not found."})

        def _start(self, body: dict) -> None:
            text = str(body.get("url") or "")
            try:
                downloader.parse_links(text)
            except downloader.DownloaderError as exc:
                self._send_json(400, {"error": str(exc)})
                return
            with app.lock:
                if app.current and app.jobs.get(app.current, {}).get("state") == "running":
                    self._send_json(409, {"error": "A download is already running."})
                    return
                job_id = os.urandom(8).hex()
                cancel = threading.Event()
                job = {
                    "id": job_id,
                    "state": "running",
                    "phase": "looking",
                    "message": "Looking at the post…",
                    "current": "",
                    "doneFiles": 0,
                    "totalFiles": 0,
                    "downloaded": 0,
                    "total": 0,
                    "files": [],
                    "warnings": [],
                    "folder": "",
                    "zip": "",
                    "error": "",
                    "title": "",
                    "cancel": cancel,
                }
                app.jobs[job_id] = job
                app.current = job_id

            def work() -> None:
                def on_progress(event: dict) -> None:
                    with app.lock:
                        job["phase"] = event.get("phase") or job["phase"]
                        if event.get("current"):
                            job["current"] = str(event["current"])
                        for key in ("doneFiles", "totalFiles", "downloaded", "total"):
                            if key in event:
                                job[key] = event[key]
                        if job["phase"] == "looking":
                            job["message"] = "Looking at the post…"
                        elif job["phase"] == "saving":
                            job["message"] = "Saving " + (job["current"] or "the file") + "…"
                        elif job["phase"] == "done":
                            job["message"] = "Saved."

                try:
                    result = app.fetcher(text, app.root, on_progress, cancel)
                    with app.lock:
                        job["state"] = "done"
                        job["phase"] = "done"
                        job["message"] = "Saved on this Mac."
                        job["folder"] = result.get("folder") or ""
                        job["zip"] = result.get("zip") or ""
                        job["files"] = list(result.get("files") or [])
                        job["warnings"] = list(result.get("warnings") or [])
                        job["title"] = result.get("title") or ""
                        job["doneFiles"] = len(job["files"])
                        job["totalFiles"] = len(job["files"])
                    print("[instagram] saved", job["folder"])
                except downloader.DownloaderError as exc:
                    with app.lock:
                        job["state"] = "cancelled" if "cancel" in str(exc).lower() else "error"
                        job["error"] = str(exc)
                        job["message"] = str(exc)
                    print("[instagram]", exc)
                except Exception:
                    traceback.print_exc()
                    with app.lock:
                        job["state"] = "error"
                        job["error"] = "That download didn't finish. Check that the Reel or post is public, then try again."
                        job["message"] = job["error"]

            threading.Thread(target=work, name="ig-download", daemon=True).start()
            self._send_json(200, {"jobId": job_id})

        def _cancel(self, job_id: str) -> None:
            with app.lock:
                job = app.jobs.get(job_id)
            if not job:
                self._send_json(404, {"error": "That download isn't running anymore."})
                return
            job["cancel"].set()
            self._send_json(200, {"ok": True})

        def _reveal(self, job_id: str) -> None:
            with app.lock:
                job = app.jobs.get(job_id)
            if not job or not job.get("folder"):
                self._send_json(404, {"error": "That folder isn't ready yet."})
                return
            folder = Path(job["folder"]).resolve()
            root = app.root.resolve()
            if root not in folder.parents and folder != root:
                self._send_json(400, {"error": "That folder isn't one this downloader made."})
                return
            if not folder.is_dir():
                self._send_json(404, {"error": "That folder isn't on the Mac anymore."})
                return
            opener = "open" if os.uname().sysname == "Darwin" else "xdg-open"
            try:
                import subprocess
                subprocess.Popen([opener, str(folder)], start_new_session=True)  # noqa: S603
            except OSError as exc:
                self._send_json(500, {"error": "The folder is saved, but it could not be opened."})
                print("[instagram] reveal failed", exc)
                return
            self._send_json(200, {"ok": True})

        def _send_zip(self, job_id: str) -> None:
            with app.lock:
                job = app.jobs.get(job_id)
            if not job or job.get("state") != "done" or not job.get("zip"):
                self._send_json(404, {"error": "The zip isn't ready yet."})
                return
            path = Path(job["zip"]).resolve()
            root = app.root.resolve()
            if root != path.parent or path.suffix != ".zip" or not path.is_file():
                self._send_json(404, {"error": "The zip isn't ready yet."})
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            with path.open("rb") as handle:
                while True:
                    chunk = handle.read(256 * 1024)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
            return host in ("127.0.0.1", "localhost")

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            if not origin:
                return True
            port = self.server.server_address[1]
            return origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

        def _body(self) -> dict:
            ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            if ctype != "application/json":
                raise downloader.DownloaderError("That request was not understood.")
            length = int(self.headers.get("Content-Length") or "0")
            if length < 0 or length > MAX_BODY:
                raise downloader.DownloaderError("That request was too large.")
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise downloader.DownloaderError("That request was not understood.") from exc
            if not isinstance(data, dict):
                raise downloader.DownloaderError("That request was not understood.")
            return data

        def _cors_origin(self) -> str | None:
            origin = self.headers.get("Origin")
            if not origin:
                return None
            port = self.server.server_address[1]
            allowed = {PAGES_ORIGIN, f"http://127.0.0.1:{port}"}
            return origin if origin in allowed else None

        def _cors(self) -> None:
            origin = self._cors_origin()
            if not origin:
                return
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin, Access-Control-Request-Private-Network")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            # A public page calling this loopback server needs this. Do not send it for any other site.
            if origin == PAGES_ORIGIN:
                self.send_header("Access-Control-Allow-Private-Network", "true")

        def _send_json(self, code: int, payload: dict, cors: bool = False) -> None:
            self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", cors=cors)

        def _send(self, code: int, data: bytes, content_type: str, cors: bool = False) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            if cors:
                self._cors()
            self.end_headers()
            self.wfile.write(data)

    return Handler


def _public_job(job: dict) -> dict:
    return {key: job[key] for key in (
        "id", "state", "phase", "message", "current", "doneFiles", "totalFiles",
        "downloaded", "total", "files", "warnings", "folder", "error", "title",
    ) if key in job}


def serve(port: int, root: Path) -> None:
    app = App(root)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    httpd.allow_reuse_address = True
    url = f"http://127.0.0.1:{httpd.server_address[1]}/"
    print("Instagram downloader is running at", url)
    print("Files go to", Path(root).expanduser())
    print("Leave this window open. Closing it stops the downloader.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        httpd.server_close()


def main() -> None:
    port = int(os.environ.get("IG_DOWNLOADER_PORT", str(PORT)))
    root = Path(os.environ.get("IG_DOWNLOADER_HOME", str(Path.home() / "Downloads" / "Instagram"))).expanduser()
    if os.environ.get("IG_DOWNLOADER_OPEN") == "1":
        webbrowser.open(f"http://127.0.0.1:{port}/")
    serve(port, root)


if __name__ == "__main__":
    main()
