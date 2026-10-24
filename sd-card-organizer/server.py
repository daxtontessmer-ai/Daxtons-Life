#!/usr/bin/env python3
"""Organize SD card — a small local page for the MacBook.

Open http://127.0.0.1:8765 after launching this. It only listens on this
computer, so a phone on the same Wi-Fi cannot reach the drives.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import organizer

PORT = 8765
HERE = Path(__file__).resolve().parent
PAGE = HERE / "web" / "index.html"
CONFIRM = "DELETE FROM CARD"
MAX_BODY = 2 * 1024 * 1024

_LOCK = threading.Lock()
_JOBS: dict = {}
_PREVIEWS: dict = {}
_CURRENT: Optional[str] = None


def volumes_root() -> Path:
    return Path(os.environ.get("SD_ORGANIZER_VOLUMES", "/Volumes"))


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        print("[organizer]", fmt % args)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in ("/", "/index.html"):
            self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            return
        if path == "/api/health":
            self._send_json(200, {"ok": True, "name": "sd-card-organizer"}, cors=True)
            return
        if path == "/api/volumes":
            self._send_json(200, {"volumes": organizer.list_volumes(volumes_root())})
            return
        if path.startswith("/api/jobs/"):
            job_id = path.split("/")[-1]
            with _LOCK:
                job = _JOBS.get(job_id)
            if not job:
                self._send_json(404, {"error": "That copy isn't running anymore."})
                return
            self._send_json(200, _public_job(job))
            return
        self._send_json(404, {"error": "Not found."})

    def do_POST(self) -> None:  # noqa: N802
        if not self._origin_ok():
            self._send_json(403, {"error": "Open this page on the MacBook, at 127.0.0.1."})
            return
        path = urlparse(self.path).path
        try:
            body = self._body()
        except organizer.OrganizerError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        try:
            if path == "/api/scan":
                source, dest = self._roots(body)
                layout = organizer.layout_from_request(body)
                files = organizer.scan_card(source)
                summary = organizer.summarize(files, layout, dest)
                summary["source"] = str(source)
                summary["dest"] = str(dest)
                self._send_json(200, summary)
                return
            if path == "/api/copy":
                self._start_copy(body)
                return
            if path == "/api/delete-preview":
                source, dest = self._roots(body)
                plan = organizer.deletion_plan(source, dest)
                token = secrets.token_urlsafe(24)
                with _LOCK:
                    _drop_old_previews()
                    _PREVIEWS[token] = {
                        "rels": [item["rel"] for item in plan["eligible"]],
                        "source": str(source),
                        "dest": str(dest),
                        "at": time.time(),
                    }
                plan["token"] = token
                self._send_json(200, plan)
                return
            if path == "/api/delete":
                self._delete(body)
                return
        except organizer.OrganizerError as exc:
            self._send_json(400, {"error": str(exc)})
            return
        except Exception:
            traceback.print_exc()
            self._send_json(500, {"error": "Something went wrong. Leave both drives plugged in and try again."})
            return
        self._send_json(404, {"error": "Not found."})

    def _start_copy(self, body: dict) -> None:
        global _CURRENT
        source, dest = self._roots(body)
        layout = organizer.layout_from_request(body)
        with _LOCK:
            if _CURRENT and _JOBS.get(_CURRENT, {}).get("state") == "running":
                raise organizer.OrganizerError("A copy is already running.")
            job_id = secrets.token_hex(8)
            job = {
                "id": job_id,
                "state": "running",
                "phase": "ready",
                "doneBytes": 0,
                "totalBytes": 0,
                "doneFiles": 0,
                "totalFiles": 0,
                "current": "",
                "log": [],
                "error": "",
                "report": None,
            }
            _JOBS[job_id] = job
            _CURRENT = job_id

        def work() -> None:
            try:
                def on_progress(event: dict) -> None:
                    with _LOCK:
                        job["phase"] = event.get("phase") or job["phase"]
                        for key in ("doneBytes", "totalBytes", "doneFiles", "totalFiles", "current"):
                            if key in event:
                                job[key] = event[key]
                        last = event.get("last")
                        if last and (not job["log"] or job["log"][-1] != last):
                            job["log"].append(last)
                            job["log"] = job["log"][-40:]

                report = organizer.run_copy(source, dest, on_progress, layout)
                with _LOCK:
                    job["report"] = _public_report(report)
                    job["state"] = "done" if report.failed == 0 else "finished"
            except organizer.OrganizerError as exc:
                with _LOCK:
                    job["state"] = "error"
                    job["error"] = str(exc)
            except Exception:
                traceback.print_exc()
                with _LOCK:
                    job["state"] = "error"
                    job["error"] = "Copying stopped. Leave the card and the drive plugged in, then try again."

        threading.Thread(target=work, name="sd-copy", daemon=True).start()
        self._send_json(200, {"jobId": job_id})

    def _delete(self, body: dict) -> None:
        if body.get("confirm") != CONFIRM:
            raise organizer.OrganizerError("Nothing was deleted. Use the delete button after you read the summary.")
        token = str(body.get("token") or "")
        source, dest = self._roots(body)
        with _LOCK:
            preview = _PREVIEWS.get(token)
        if not preview or time.time() - preview["at"] > 30 * 60:
            raise organizer.OrganizerError("Look at the summary again, then delete. The last summary expired.")
        if preview["source"] != str(source) or preview["dest"] != str(dest):
            raise organizer.OrganizerError("The drives changed. Look at the summary again.")
        # Re-check every file on the drive before anything is removed.
        result = organizer.delete_verified(source, dest, preview["rels"])
        with _LOCK:
            _PREVIEWS.pop(token, None)
        self._send_json(200, result)

    def _roots(self, body: dict):
        source = _known_volume(str(body.get("source") or ""))
        dest_volume = _known_volume(str(body.get("dest") or ""))
        if source == dest_volume:
            raise organizer.OrganizerError("Pick the SD card and the hard drive as two different drives.")
        root_name = organizer.sanitize_root_name(str(body.get("rootName") or "Sony"))
        dest = organizer.destination_root(dest_volume, root_name)
        return source, dest

    def _origin_ok(self) -> bool:
        host = (self.headers.get("Host") or "").split(":")[0]
        if host not in ("127.0.0.1", "localhost"):
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        port = self.server.server_address[1]
        return origin in {f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def _body(self) -> dict:
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise organizer.OrganizerError("That request was not understood.")
        length = int(self.headers.get("Content-Length") or "0")
        if length < 0 or length > MAX_BODY:
            raise organizer.OrganizerError("That request was too large.")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise organizer.OrganizerError("That request was not understood.") from exc
        if not isinstance(data, dict):
            raise organizer.OrganizerError("That request was not understood.")
        return data

    def _send_json(self, code: int, payload: dict, cors: bool = False) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", cors=cors)

    def _send(self, code: int, data: bytes, content_type: str, cors: bool = False) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        if cors:
            self.send_header("Access-Control-Allow-Origin", "*")
            # GitHub Pages is https. Chrome asks before it will call http://127.0.0.1.
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/api/health":
            self._send_json(404, {"error": "Not found."})
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", "0")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def _known_volume(path_str: str) -> Path:
    if not path_str:
        raise organizer.OrganizerError("Pick a drive first.")
    try:
        path = Path(path_str).resolve()
    except OSError as exc:
        raise organizer.OrganizerError("That drive can't be opened.") from exc
    known = {}
    for volume in organizer.list_volumes(volumes_root()):
        known[Path(volume["path"]).resolve()] = volume
    info = known.get(path)
    if info is None:
        raise organizer.OrganizerError("That drive isn't plugged in. Plug it in and refresh the list.")
    if info["internal"] or organizer.volume_is_internal(path):
        raise organizer.OrganizerError(
            "That disk is the Mac's internal drive. Files go straight from the card to the hard drive."
        )
    return path


def _public_job(job: dict) -> dict:
    return {
        "id": job["id"],
        "state": job["state"],
        "phase": job["phase"],
        "doneBytes": job["doneBytes"],
        "totalBytes": job["totalBytes"],
        "doneFiles": job["doneFiles"],
        "totalFiles": job["totalFiles"],
        "current": job["current"],
        "log": list(job["log"]),
        "error": job["error"],
        "report": job["report"],
    }


def _public_report(report: organizer.CopyReport) -> dict:
    return {
        "copied": report.copied,
        "skipped": report.skipped,
        "failed": report.failed,
        "results": [
            {
                "name": item.source.name,
                "action": item.action,
                "day": item.day,
                "kind": item.kind,
                "size": item.size,
                "dest": item.dest_rel,
                "message": item.message,
            }
            for item in report.results
        ],
    }


def _drop_old_previews() -> None:
    cutoff = time.time() - 30 * 60
    for token, preview in list(_PREVIEWS.items()):
        if preview["at"] < cutoff:
            del _PREVIEWS[token]


def make_server(port: int = PORT) -> ThreadingHTTPServer:
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main() -> None:
    try:
        httpd = make_server(PORT)
    except OSError:
        print("Organize SD card is already running (or port 8765 is busy).")
        print("Open http://127.0.0.1:8765 in Safari. Leave this window open while you copy.")
        raise SystemExit(1)
    print("Organize SD card is running.")
    print("Open http://127.0.0.1:8765 in Safari if it did not open on its own.")
    print("Leave this window open until the copy finishes. Closing it stops the organizer.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
