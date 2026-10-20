"""Sample-card tests: several days, missing dates, sidecars, duplicates, and delete safety."""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import organizer
import server


def tiff_exif(date_text: str = "2024:03:15 10:30:00") -> bytes:
    date = date_text.encode("ascii") + b"\x00"
    exif_ifd_off = 26
    string_off = 44
    ifd0 = struct.pack("<H", 1)
    ifd0 += struct.pack("<HHI", 0x8769, 4, 1) + struct.pack("<I", exif_ifd_off)
    ifd0 += struct.pack("<I", 0)
    exif = struct.pack("<H", 1)
    exif += struct.pack("<HHI", 0x9003, 2, len(date)) + struct.pack("<I", string_off)
    exif += struct.pack("<I", 0)
    return b"II" + struct.pack("<H", 42) + struct.pack("<I", 8) + ifd0 + exif + date


def jpeg_with_exif(date_text: str, payload: bytes = b"photo-bytes") -> bytes:
    tiff = tiff_exif(date_text)
    app = b"Exif\x00\x00" + tiff
    return b"\xff\xd8" + b"\xff\xe1" + struct.pack(">H", len(app) + 2) + app + payload + b"\xff\xd9"


def jpeg_without_exif(payload: bytes = b"no-date") -> bytes:
    return b"\xff\xd8" + payload + b"\xff\xd9"


def mp4_with_creation(seconds: int, body: bytes = b"\x11" * 64) -> bytes:
    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I4s", 8 + len(payload), kind) + payload

    def box64(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload

    mvhd = struct.pack(">I", 0)
    mvhd += struct.pack(">II", seconds, seconds)
    mvhd += struct.pack(">II", 1000, 1000)
    mvhd += b"\x00" * 16
    ftyp = box(b"ftyp", b"isom" + b"\x00\x00\x00\x00" + b"isom")
    # moov after the media, the way many cameras write it, with a 64-bit size.
    mdat = box64(b"mdat", body)
    moov = box(b"moov", box(b"mvhd", mvhd))
    return ftyp + mdat + moov


def sony_xml(value: str) -> bytes:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<NonRealTimeMeta>\n"
        f'  <CreationDate value="{value}"/>\n'
        "</NonRealTimeMeta>\n"
    ).encode("utf-8")


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ParseTests(unittest.TestCase):
    def test_jpeg_exif_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DSC0001.JPG"
            write(path, jpeg_with_exif("2024:03:15 10:30:00"))
            self.assertEqual(organizer.exif_datetime(path), datetime(2024, 3, 15, 10, 30, 0))

    def test_raw_tiff_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "DSC0001.ARW"
            write(path, tiff_exif("2022:12:01 08:05:09") + b"raw")
            self.assertEqual(organizer.exif_datetime(path), datetime(2022, 12, 1, 8, 5, 9))

    def test_xml_keeps_camera_local_day(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "C0001M01.XML"
            # 23:30 in the camera's zone is the next morning in UTC. The folder uses the camera day.
            write(path, sony_xml("2024-01-02T23:30:00-06:00"))
            self.assertEqual(organizer.xml_datetime(path), datetime(2024, 1, 2, 23, 30, 0))

    def test_quicktime_creation_reads_moov_after_media(self):
        moment = datetime(2024, 5, 2, 18, 0, tzinfo=timezone.utc)
        seconds = int((moment - organizer.QT_EPOCH).total_seconds())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "C0002.MP4"
            write(path, mp4_with_creation(seconds))
            found = organizer.quicktime_datetime(path)
            self.assertIsNotNone(found)
            self.assertEqual(found, moment.astimezone().replace(tzinfo=None))


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.card = self.root / "card"
        self.drive = self.root / "drive" / "Sony"
        self.card.mkdir()
        self.internal = self.root / "internal-temp"
        self.internal.mkdir()
        self._old_tmp = {key: os.environ.get(key) for key in ("TMPDIR", "TEMP", "TMP")}
        for key in self._old_tmp:
            os.environ[key] = str(self.internal)

    def tearDown(self):
        for key, value in self._old_tmp.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.tmp.cleanup()

    def build_card(self):
        # Two shoot days, plus one photo with no camera date.
        write(self.card / "DCIM" / "100MSDCF" / "DSC0001.JPG", jpeg_with_exif("2024:03:15 10:30:00", b"day-one"))
        write(self.card / "DCIM" / "100MSDCF" / "DSC0002.JPG", jpeg_with_exif("2024:03:16 09:00:00", b"day-two"))
        bare = self.card / "DCIM" / "100MSDCF" / "DSC0099.JPG"
        write(bare, jpeg_without_exif(b"fallback-photo"))
        stamp = datetime(2021, 7, 4, 15, 0).timestamp()
        os.utime(bare, (stamp, stamp))

        moment = datetime(2020, 1, 1, 12, 0, tzinfo=timezone.utc)
        seconds = int((moment - organizer.QT_EPOCH).total_seconds())
        video = self.card / "PRIVATE" / "M4ROOT" / "CLIP" / "C0001.MP4"
        # Big enough to cross the 8 MB copy chunk, like a short 4K clip.
        write(video, mp4_with_creation(seconds, b"v" * (9 * 1024 * 1024 + 17)))
        os.utime(video, (datetime(2019, 1, 1).timestamp(),) * 2)
        xml = self.card / "PRIVATE" / "M4ROOT" / "CLIP" / "C0001M01.XML"
        write(xml, sony_xml("2024-01-02T23:30:00-06:00"))
        os.utime(xml, (datetime(2018, 5, 5).timestamp(),) * 2)
        thm = self.card / "PRIVATE" / "M4ROOT" / "THMBNL" / "C0001T01.THM"
        write(thm, jpeg_without_exif(b"thumb"))
        os.utime(thm, (datetime(2017, 2, 2).timestamp(),) * 2)
        # A sidecar with no matching video still has to be kept, using its own date.
        write(self.card / "PRIVATE" / "M4ROOT" / "CLIP" / "ORPHAN.XML", sony_xml("2023-08-08T12:00:00-05:00"))
        # Not media, and a symlink that must not be followed onto another disk.
        write(self.card / "notes.txt", b"ignore me")
        outside = self.root / "secret.txt"
        outside.write_text("nope")
        (self.card / "link-out.JPG").symlink_to(outside)

    def test_days_sidecars_fallback_and_direct_copy(self):
        self.build_card()
        report = organizer.run_copy(self.card, self.drive)
        self.assertEqual(report.failed, 0)
        self.assertEqual(os.listdir(self.internal), [])
        photos_15 = self.drive / "2024-03-15" / "Photos" / "DSC0001.JPG"
        photos_16 = self.drive / "2024-03-16" / "Photos" / "DSC0002.JPG"
        fallback = self.drive / "2021-07-04" / "Photos" / "DSC0099.JPG"
        video = self.drive / "2024-01-02" / "Videos" / "C0001.MP4"
        xml = self.drive / "2024-01-02" / "Videos" / "C0001M01.XML"
        thm = self.drive / "2024-01-02" / "Videos" / "C0001T01.THM"
        orphan = self.drive / "2023-08-08" / "Videos" / "ORPHAN.XML"
        for path in (photos_15, photos_16, fallback, video, xml, thm, orphan):
            self.assertTrue(path.is_file(), path)
        self.assertEqual(sha(photos_15), sha(self.card / "DCIM" / "100MSDCF" / "DSC0001.JPG"))
        self.assertEqual(sha(video), sha(self.card / "PRIVATE" / "M4ROOT" / "CLIP" / "C0001.MP4"))
        self.assertFalse(any(self.drive.rglob("*.copying")))
        self.assertFalse((self.drive / "notes.txt").exists())
        self.assertFalse(list(self.drive.rglob("link-out.JPG")))
        # The video folder is the camera day from the XML, not the file dates of the sidecars.
        self.assertFalse((self.drive / "2017-02-02").exists())
        self.assertFalse((self.drive / "2019-01-01").exists())

    def test_second_card_merges_skips_duplicates_and_renames_conflicts(self):
        self.build_card()
        first = organizer.run_copy(self.card, self.drive)
        self.assertGreater(first.copied, 0)
        # A different photo already using the name that the next card will bring.
        conflict_dir = self.drive / "2024-03-15" / "Photos"
        original = (conflict_dir / "DSC0001.JPG").read_bytes()
        (conflict_dir / "DSC0001.JPG").write_bytes(b"different-photo-same-name")
        # And the day-two photo is already there, byte for byte, under a renamed file.
        day_two = conflict_dir.parent.parent / "2024-03-16" / "Photos"
        existing = day_two / "DSC0002.JPG"
        existing.rename(day_two / "DSC0002_2.JPG")

        second = organizer.run_copy(self.card, self.drive)
        by_name = {item.source.name: item for item in second.results}
        self.assertEqual(by_name["DSC0001.JPG"].action, "renamed")
        self.assertEqual(by_name["DSC0001.JPG"].dest.name, "DSC0001_2.JPG")
        self.assertEqual((conflict_dir / "DSC0001.JPG").read_bytes(), b"different-photo-same-name")
        self.assertNotEqual(original, b"different-photo-same-name")
        self.assertEqual((conflict_dir / "DSC0001_2.JPG").read_bytes(), original)
        self.assertEqual(by_name["DSC0002.JPG"].action, "skipped")
        self.assertEqual(list(day_two.glob("DSC0002*.JPG")), [day_two / "DSC0002_2.JPG"])
        self.assertEqual(second.failed, 0)

    def test_checksum_failure_removes_the_copy(self):
        src_dir = self.card / "DCIM"
        src = src_dir / "A.JPG"
        write(src, jpeg_with_exif("2024:04:04 04:04:04", b"abc"))
        dest = self.drive / "out.JPG"
        with mock.patch.object(organizer, "sha256_file", return_value="0" * 64):
            with self.assertRaises(organizer.OrganizerError):
                organizer.copy_verified(src, dest)
        self.assertFalse(dest.exists())
        self.assertFalse(dest.with_name(dest.name + ".copying").exists())

    def test_delete_only_verified_files_and_only_when_asked(self):
        self.build_card()
        organizer.run_copy(self.card, self.drive)
        extra = self.card / "DCIM" / "100MSDCF" / "NOTCOPIED.JPG"
        write(extra, jpeg_with_exif("2024:03:15 11:00:00", b"still-on-card"))
        plan = organizer.deletion_plan(self.card, self.drive)
        rels = {item["rel"] for item in plan["eligible"]}
        self.assertIn("DCIM/100MSDCF/DSC0001.JPG", rels)
        self.assertNotIn("DCIM/100MSDCF/NOTCOPIED.JPG", rels)
        self.assertTrue(any(item["rel"].endswith("NOTCOPIED.JPG") for item in plan["kept"]))

        # Removing the drive copy makes the card file ineligible, even if it was copied before.
        video = self.drive / "2024-01-02" / "Videos" / "C0001.MP4"
        video.unlink()
        plan = organizer.deletion_plan(self.card, self.drive)
        self.assertNotIn("PRIVATE/M4ROOT/CLIP/C0001.MP4", {item["rel"] for item in plan["eligible"]})

        # The delete call itself re-checks. Passing the extra file does not remove it.
        gone = organizer.delete_verified(
            self.card,
            self.drive,
            [item["rel"] for item in plan["eligible"]] + ["DCIM/100MSDCF/NOTCOPIED.JPG", "../secret.txt"],
        )
        self.assertIn("DCIM/100MSDCF/DSC0001.JPG", gone["deleted"])
        self.assertFalse((self.card / "DCIM" / "100MSDCF" / "DSC0001.JPG").exists())
        self.assertTrue(extra.exists())
        self.assertTrue((self.root / "secret.txt").exists())
        self.assertTrue((self.drive / "2024-03-15" / "Photos" / "DSC0001.JPG").exists())
        # The video whose drive copy was removed is still on the card.
        self.assertTrue((self.card / "PRIVATE" / "M4ROOT" / "CLIP" / "C0001.MP4").exists())


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.volumes = self.root / "Volumes"
        self.card = self.volumes / "SD_CARD"
        self.hdd = self.volumes / "PhotoDrive"
        self.card.mkdir(parents=True)
        self.hdd.mkdir()
        write(self.card / "DCIM" / "DSC0100.JPG", jpeg_with_exif("2024:06:01 12:00:00", b"from-card"))
        write(self.card / "KEEP.JPG", jpeg_with_exif("2024:06:02 12:00:00", b"not-in-manifest-yet"))
        self._env = os.environ.get("SD_ORGANIZER_VOLUMES")
        os.environ["SD_ORGANIZER_VOLUMES"] = str(self.volumes)
        self.httpd = server.make_server(0)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.patch = mock.patch.object(organizer, "volume_is_internal", return_value=False)
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        if self._env is None:
            os.environ.pop("SD_ORGANIZER_VOLUMES", None)
        else:
            os.environ["SD_ORGANIZER_VOLUMES"] = self._env
        self.tmp.cleanup()

    def request(self, method, path, body=None, origin=None):
        import urllib.request
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request("http://127.0.0.1:%d%s" % (self.port, path), data=data, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/json")
        if origin:
            req.add_header("Origin", origin)
        try:
            with urllib.request.urlopen(req, timeout=30) as res:
                raw = res.read()
                return res.status, dict(res.headers), json.loads(raw) if raw else {}
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            return exc.code, dict(exc.headers), json.loads(raw) if raw else {}

    def test_page_and_health(self):
        import urllib.request
        with urllib.request.urlopen("http://127.0.0.1:%d/" % self.port, timeout=10) as res:
            page = res.read().decode()
        self.assertIn("Organize SD card", page)
        self.assertIn("Delete from the SD card", page)
        status, headers, body = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")

    def test_copy_then_delete_requires_an_explicit_confirm(self):
        status, _, volumes = self.request("GET", "/api/volumes")
        self.assertEqual(status, 200)
        names = {item["name"] for item in volumes["volumes"]}
        self.assertEqual(names, {"PhotoDrive", "SD_CARD"})
        body = {"source": str(self.card), "dest": str(self.hdd), "rootName": "Sony"}
        status, _, summary = self.request("POST", "/api/scan", body)
        self.assertEqual(summary["photos"], 2)
        status, _, started = self.request("POST", "/api/copy", body)
        self.assertEqual(status, 200)
        job = {}
        for _ in range(100):
            _, _, job = self.request("GET", "/api/jobs/" + started["jobId"])
            if job["state"] != "running":
                break
            import time
            time.sleep(0.05)
        self.assertEqual(job["state"], "done")
        self.assertEqual(job["report"]["copied"], 2)
        saved = self.hdd / "Sony" / "2024-06-01" / "Photos" / "DSC0100.JPG"
        self.assertTrue(saved.is_file())
        self.assertEqual(saved.read_bytes(), (self.card / "DCIM" / "DSC0100.JPG").read_bytes())

        status, _, denied = self.request("POST", "/api/delete", {**body, "confirm": "no", "token": "x"})
        self.assertEqual(status, 400)
        self.assertTrue((self.card / "DCIM" / "DSC0100.JPG").exists())

        # A website that is not the local page cannot ask for a delete.
        status, _, _ = self.request(
            "POST", "/api/delete",
            {**body, "confirm": server.CONFIRM, "token": "x"},
            origin="https://evil.example",
        )
        self.assertEqual(status, 403)
        self.assertTrue((self.card / "DCIM" / "DSC0100.JPG").exists())

        status, _, plan = self.request("POST", "/api/delete-preview", body)
        self.assertEqual(status, 200)
        self.assertEqual(len(plan["eligible"]), 2)
        status, _, result = self.request(
            "POST", "/api/delete",
            {**body, "confirm": server.CONFIRM, "token": plan["token"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(result["deleted"]), 2)
        self.assertFalse((self.card / "DCIM" / "DSC0100.JPG").exists())
        self.assertTrue(saved.is_file())

    def test_internal_disk_is_refused(self):
        self.patch.stop()
        body = {"source": str(self.card), "dest": str(self.hdd), "rootName": "Sony"}
        status, _, payload = self.request("POST", "/api/scan", body)
        self.assertEqual(status, 400)
        self.assertIn("internal", payload["error"].lower())
        self.patch.start()


if __name__ == "__main__":
    unittest.main()
