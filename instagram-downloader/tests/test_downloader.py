"""Checks for link rules, the zip, and the local page. No network."""

from __future__ import annotations

import json
import sys
import threading
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import downloader
import server


class ParseTests(unittest.TestCase):
    def test_reel_post_tv_and_tracking(self):
        links = downloader.parse_links(
            "see https://www.instagram.com/reel/Chunk8-jurw/?igsh=abc and "
            "https://instagram.com/name/p/BQ0eAlwhDrw/ "
            "https://www.instagram.com/tv/BkfuX9UB-eK\n"
            "https://www.instagram.com/reels/Cop84x6u7CP/"
        )
        self.assertEqual(links, [
            "https://www.instagram.com/reel/Chunk8-jurw/",
            "https://www.instagram.com/p/BQ0eAlwhDrw/",
            "https://www.instagram.com/tv/BkfuX9UB-eK/",
            "https://www.instagram.com/reel/Cop84x6u7CP/",
        ])

    def test_dedupes_and_caps(self):
        self.assertEqual(
            downloader.parse_links("https://www.instagram.com/reel/Chunk8-jurw/ https://www.instagram.com/reel/Chunk8-jurw/"),
            ["https://www.instagram.com/reel/Chunk8-jurw/"],
        )
        many = " ".join(f"https://www.instagram.com/p/code{i:05d}X/" for i in range(9))
        with self.assertRaises(downloader.DownloaderError):
            downloader.parse_links(many)

    def test_rejects_stories_profiles_shares_and_other_sites(self):
        for text in (
            "https://www.instagram.com/stories/natgeo/123456/",
            "https://www.instagram.com/instagram/",
            "https://www.instagram.com/share/reel/AbCdEfGhIjK/",
            "https://www.instagram.com/reel/audio/123/",
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "",
        ):
            with self.assertRaises(downloader.DownloaderError):
                downloader.parse_links(text)

    def test_cdn_allowlist(self):
        self.assertTrue(downloader.allowed_cdn("https://scontent.cdninstagram.com/v/photo.jpg"))
        self.assertTrue(downloader.allowed_cdn("https://instagram.fxyz1-1.fna.fbcdn.net/v/photo.jpg"))
        self.assertFalse(downloader.allowed_cdn("http://scontent.cdninstagram.com/v/photo.jpg"))
        self.assertFalse(downloader.allowed_cdn("https://www.instagram.com/accounts/login/"))
        self.assertFalse(downloader.allowed_cdn("https://evil.example/cdninstagram.com/a.jpg"))
        self.assertFalse(downloader.allowed_cdn("file:///etc/passwd"))


class OptionTests(unittest.TestCase):
    def test_options_do_not_use_cookies_or_login(self):
        opts = downloader.build_options(Path("/tmp/ig-test"), lambda _event: None)
        self.assertIsNone(opts["cookiefile"])
        self.assertIsNone(opts["cookiesfrombrowser"])
        self.assertIsNone(opts["username"])
        self.assertIsNone(opts["password"])
        self.assertFalse(opts["usenetrc"])
        self.assertFalse(opts["cachedir"])
        self.assertFalse(opts["warn_when_outdated"])
        self.assertFalse(opts["getcomments"])
        self.assertFalse(opts["writeinfojson"])
        self.assertEqual(opts["allowed_extractors"], ["^instagram$"])
        self.assertFalse(opts["geo_bypass"])
        self.assertNotIn("impersonate", opts)


class ZipTests(unittest.TestCase):
    def test_folder_and_zip(self):
        def fake(text, root, on_progress, cancel):
            urls = downloader.parse_links(text)
            folder = downloader.unique_dir(root, downloader.folder_stamp(__import__("datetime").datetime(2026, 10, 29, 15, 4, 5), urls))
            folder.mkdir(parents=True)
            video = folder / "01-Chunk8-jurw.mp4"
            video.write_bytes(b"\x00\x00\x00\x18ftypisom" + b"\x00" * 32)
            (folder / "source.txt").write_text(urls[0] + "\n", encoding="utf-8")
            zip_path = root / f"{folder.name}.zip"
            downloader._write_zip(folder, zip_path)
            on_progress({"phase": "done", "doneFiles": 1, "totalFiles": 1})
            return {"folder": str(folder), "zip": str(zip_path), "files": ["01-Chunk8-jurw.mp4", "source.txt"], "warnings": [], "title": "Video by instagram"}

        root = Path(self.id().replace(".", "_"))
        # unique temp under the system temp dir
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            result = fake("https://www.instagram.com/reel/Chunk8-jurw/", root, lambda _e: None, threading.Event())
            self.assertTrue(Path(result["zip"]).is_file())
            with zipfile.ZipFile(result["zip"]) as archive:
                names = archive.namelist()
            self.assertTrue(any(name.endswith("01-Chunk8-jurw.mp4") for name in names))
            self.assertTrue(Path(result["folder"], "01-Chunk8-jurw.mp4").is_file())


class ImageTests(unittest.TestCase):
    def test_rejects_html_pretending_to_be_a_photo(self):
        self.assertEqual(downloader._sniff_image(b"\xff\xd8\xff\xe0rest"), ".jpg")
        self.assertEqual(downloader._sniff_image(b"<!doctype html>"), "")


class ServerTests(unittest.TestCase):
    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.calls = []

        def fake(text, root, on_progress, cancel):
            self.calls.append(text)
            folder = root / "2026-10-29_150405_Chunk8-jurw"
            folder.mkdir()
            (folder / "01-Chunk8-jurw.mp4").write_bytes(b"\x00\x00\x00\x18ftypisomfake-video")
            zip_path = root / "2026-10-29_150405_Chunk8-jurw.zip"
            downloader._write_zip(folder, zip_path)
            on_progress({"phase": "done"})
            return {
                "folder": str(folder),
                "zip": str(zip_path),
                "files": ["01-Chunk8-jurw.mp4"],
                "warnings": [],
                "title": "Video by instagram",
            }

        app = server.App(self.root, fetcher=fake)
        self.httpd = server.ThreadingHTTPServer(("127.0.0.1", 0), server.make_handler(app))
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def _request(self, method, path, body=None, origin=None, host=None):
        import urllib.error
        import urllib.request
        data = None if body is None else json.dumps(body).encode()
        headers = {}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if origin is not None:
            headers["Origin"] = origin
        if host is not None:
            headers["Host"] = host
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, resp.read(), dict(resp.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read(), dict(exc.headers)

    def test_health_page_and_download(self):
        code, raw, _headers = self._request("GET", "/api/health")
        info = json.loads(raw)
        self.assertEqual(code, 200)
        self.assertTrue(info["ok"])
        self.assertEqual(info["name"], "instagram-downloader")
        code, page, _headers = self._request("GET", "/")
        self.assertEqual(code, 200)
        self.assertIn(b"Download", page)
        origin = f"http://127.0.0.1:{self.port}"
        code, raw, _headers = self._request("POST", "/api/download", {"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}, origin=origin)
        self.assertEqual(code, 400)
        self.assertEqual(self.calls, [])
        code, raw, _headers = self._request("POST", "/api/download", {"url": "https://www.instagram.com/reel/Chunk8-jurw/?igsh=1"}, origin="https://evil.example")
        self.assertEqual(code, 403)
        code, raw, _headers = self._request("POST", "/api/download", {"url": "https://www.instagram.com/reel/Chunk8-jurw/?igsh=1"}, origin=origin)
        self.assertEqual(code, 200)
        job_id = json.loads(raw)["jobId"]
        for _ in range(20):
            code, raw, _headers = self._request("GET", f"/api/jobs/{job_id}")
            job = json.loads(raw)
            if job["state"] != "running":
                break
        self.assertEqual(job["state"], "done")
        self.assertIn("01-Chunk8-jurw.mp4", job["files"])
        self.assertTrue(job["folder"].endswith("2026-10-29_150405_Chunk8-jurw"))
        code, blob, headers = self._request("GET", f"/api/jobs/{job_id}/zip")
        self.assertEqual(code, 200)
        self.assertEqual(headers.get("Content-Type"), "application/zip")
        self.assertTrue(blob.startswith(b"PK"))
        with zipfile.ZipFile(__import__("io").BytesIO(blob)) as archive:
            names = archive.namelist()
        self.assertTrue(any(name.endswith(".mp4") for name in names))


if __name__ == "__main__":
    unittest.main()
