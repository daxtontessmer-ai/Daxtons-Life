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


def tiff_oriented(date_text: str, width: int, height: int, orientation: int) -> bytes:
    date = date_text.encode("ascii") + b"\x00"
    exif_ifd_off = 62
    string_off = 80
    ifd0 = struct.pack("<H", 4)
    ifd0 += struct.pack("<HHI", 0x0100, 4, 1) + struct.pack("<I", width)
    ifd0 += struct.pack("<HHI", 0x0101, 4, 1) + struct.pack("<I", height)
    ifd0 += struct.pack("<HHI", 0x0112, 3, 1) + struct.pack("<H", orientation) + b"\x00\x00"
    ifd0 += struct.pack("<HHI", 0x8769, 4, 1) + struct.pack("<I", exif_ifd_off)
    ifd0 += struct.pack("<I", 0)
    exif = struct.pack("<H", 1)
    exif += struct.pack("<HHI", 0x9003, 2, len(date)) + struct.pack("<I", string_off)
    exif += struct.pack("<I", 0)
    return b"II" + struct.pack("<H", 42) + struct.pack("<I", 8) + ifd0 + exif + date


def jpeg_oriented(date_text: str, width: int, height: int, orientation: int, payload: bytes = b"pix") -> bytes:
    tiff = tiff_oriented(date_text, width, height, orientation)
    app = b"Exif\x00\x00" + tiff
    sof = struct.pack(">BHHB", 8, height, width, 1)
    return (
        b"\xff\xd8"
        + b"\xff\xe1" + struct.pack(">H", len(app) + 2) + app
        + b"\xff\xc0" + struct.pack(">H", len(sof) + 2) + sof
        + payload
        + b"\xff\xd9"
    )


def mp4_with_frame(seconds: int, width: int, height: int, quarter_turn: bool) -> bytes:
    def box(kind: bytes, payload: bytes) -> bytes:
        return struct.pack(">I4s", 8 + len(payload), kind) + payload

    mvhd = struct.pack(">I", 0)
    mvhd += struct.pack(">II", seconds, seconds)
    mvhd += struct.pack(">II", 1000, 1000)
    mvhd += b"\x00" * 16
    if quarter_turn:
        matrix = [0, 0x10000, 0, -0x10000, 0, 0, 0, 0, 0x40000000]
    else:
        matrix = [0x10000, 0, 0, 0, 0x10000, 0, 0, 0, 0x40000000]
    tkhd = bytes([0, 0, 0, 7])
    tkhd += struct.pack(">II", 0, 0)
    tkhd += struct.pack(">II", 1, 0)
    tkhd += struct.pack(">I", 1000)
    tkhd += b"\x00" * 8
    tkhd += struct.pack(">hhhh", 0, 0, 0, 0)
    tkhd += struct.pack(">9i", *matrix)
    tkhd += struct.pack(">II", width << 16, height << 16)
    hdlr = bytes(4) + struct.pack(">I", 0) + b"vide" + b"Video\x00"
    trak = box(b"trak", box(b"tkhd", tkhd) + box(b"mdia", box(b"hdlr", hdlr)))
    ftyp = box(b"ftyp", b"isom" + b"\x00\x00\x00\x00" + b"isom")
    return ftyp + box(b"moov", box(b"mvhd", mvhd) + trak)


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

    def test_photo_orientation_respects_exif_rotation_and_square(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            landscape = root / "wide.JPG"
            turned = root / "turned.JPG"
            square = root / "square.JPG"
            tall = root / "tall.JPG"
            upside = root / "upside.JPG"
            write(landscape, jpeg_oriented("2024:03:15 10:00:00", 4000, 3000, 1))
            write(turned, jpeg_oriented("2024:03:15 10:00:00", 4000, 3000, 6))
            write(square, jpeg_oriented("2024:03:15 10:00:00", 2000, 2000, 1))
            write(tall, jpeg_oriented("2024:03:15 10:00:00", 3000, 4000, 1))
            write(upside, jpeg_oriented("2024:03:15 10:00:00", 1920, 1080, 3))
            self.assertEqual(organizer.photo_orientation(landscape), "Horizontal")
            self.assertEqual(organizer.photo_orientation(turned), "Vertical")
            self.assertEqual(organizer.photo_orientation(square), "Horizontal")
            self.assertEqual(organizer.photo_orientation(tall), "Vertical")
            self.assertEqual(organizer.photo_orientation(upside), "Horizontal")
            self.assertEqual(organizer.exif_datetime(turned), datetime(2024, 3, 15, 10, 0, 0))

    def test_video_orientation_uses_matrix_and_ffprobe_rotation(self):
        moment = datetime(2024, 5, 2, 18, 0, tzinfo=timezone.utc)
        seconds = int((moment - organizer.QT_EPOCH).total_seconds())
        with tempfile.TemporaryDirectory() as tmp:
            wide = Path(tmp) / "wide.MP4"
            tall = Path(tmp) / "tall.MP4"
            write(wide, mp4_with_frame(seconds, 1920, 1080, False))
            write(tall, mp4_with_frame(seconds, 1920, 1080, True))
            self.assertEqual(organizer.video_orientation(wide), "Horizontal")
            self.assertEqual(organizer.video_orientation(tall), "Vertical")
        probe = json.dumps({
            "streams": [{"width": 1920, "height": 1080, "tags": {"rotate": "90"}}]
        }).encode()
        self.assertEqual(organizer._display_size_from_probe(probe), (1080, 1920))
        sideways = json.dumps({
            "streams": [{"width": 1080, "height": 1920, "side_data_list": [{"rotation": -90}]}]
        }).encode()
        self.assertEqual(organizer._display_size_from_probe(sideways), (1920, 1080))


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
        photos_15 = self.drive / "Other Days" / "Photos" / "Horizontal" / "DSC0001.JPG"
        photos_16 = self.drive / "Other Days" / "Photos" / "Horizontal" / "DSC0002.JPG"
        fallback = self.drive / "Other Days" / "Photos" / "Horizontal" / "DSC0099.JPG"
        video = self.drive / "Other Days" / "Videos" / "Horizontal" / "C0001.MP4"
        xml = self.drive / "Other Days" / "Videos" / "Horizontal" / "C0001M01.XML"
        thm = self.drive / "Other Days" / "Videos" / "Horizontal" / "C0001T01.THM"
        orphan = self.drive / "Other Days" / "Videos" / "Horizontal" / "ORPHAN.XML"
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
        self.assertFalse((self.drive / "2024-03-15").exists())
        self.assertFalse((self.drive / "2024-01-02").exists())

    def test_second_card_merges_skips_duplicates_and_renames_conflicts(self):
        self.build_card()
        first = organizer.run_copy(self.card, self.drive)
        self.assertGreater(first.copied, 0)
        # A different photo already using the name that the next card will bring.
        conflict_dir = self.drive / "Other Days" / "Photos" / "Horizontal"
        original = (conflict_dir / "DSC0001.JPG").read_bytes()
        (conflict_dir / "DSC0001.JPG").write_bytes(b"different-photo-same-name")
        # And the day-two photo is already there, byte for byte, under a renamed file.
        day_two = self.drive / "Other Days" / "Photos" / "Horizontal"
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
        video = self.drive / "Other Days" / "Videos" / "Horizontal" / "C0001.MP4"
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
        self.assertTrue((self.drive / "Other Days" / "Photos" / "Horizontal" / "DSC0001.JPG").exists())
        # The video whose drive copy was removed is still on the card.
        self.assertTrue((self.card / "PRIVATE" / "M4ROOT" / "CLIP" / "C0001.MP4").exists())

    def test_portrait_square_and_legacy_folder(self):
        write(self.card / "wide.JPG", jpeg_oriented("2024:03:15 10:00:00", 4000, 3000, 1, b"wide"))
        write(self.card / "tall.JPG", jpeg_oriented("2024:03:15 10:00:00", 4000, 3000, 6, b"tall-pixels"))
        write(self.card / "square.JPG", jpeg_oriented("2024:03:15 10:00:00", 1000, 1000, 1, b"square"))
        seconds = int((datetime(2024, 3, 15, 12, 0, tzinfo=timezone.utc) - organizer.QT_EPOCH).total_seconds())
        write(self.card / "clip.MP4", mp4_with_frame(seconds, 1920, 1080, True))
        write(self.card / "clipM01.XML", sony_xml("2024-03-15T12:00:00-05:00"))
        report = organizer.run_copy(self.card, self.drive)
        self.assertEqual(report.failed, 0)
        self.assertTrue((self.drive / "Other Days" / "Photos" / "Horizontal" / "wide.JPG").is_file())
        self.assertTrue((self.drive / "Other Days" / "Photos" / "Vertical" / "tall.JPG").is_file())
        self.assertTrue((self.drive / "Other Days" / "Photos" / "Horizontal" / "square.JPG").is_file())
        self.assertTrue((self.drive / "Other Days" / "Videos" / "Vertical" / "clip.MP4").is_file())
        self.assertTrue((self.drive / "Other Days" / "Videos" / "Vertical" / "clipM01.XML").is_file())
        self.assertEqual(os.listdir(self.internal), [])

        # A file copied by an older version, sitting directly in the day folder, is not copied again.
        legacy = self.drive / "2024-03-15" / "Photos" / "wide.JPG"
        current = self.drive / "Other Days" / "Photos" / "Horizontal" / "wide.JPG"
        legacy.parent.mkdir(parents=True, exist_ok=True)
        legacy.write_bytes(current.read_bytes())
        current.unlink()
        again = organizer.run_copy(self.card, self.drive)
        by_name = {item.source.name: item for item in again.results}
        self.assertEqual(by_name["wide.JPG"].action, "skipped")
        self.assertFalse(current.exists())
        self.assertTrue(legacy.is_file())

    def test_small_days_trip_range_and_earlier_copies(self):
        def photos(day_text, count, stem):
            for number in range(count):
                write(
                    self.card / "DCIM" / f"{stem}{number:04d}.JPG",
                    jpeg_with_exif(day_text, f"{stem}-{number}".encode()),
                )

        photos("2024:05:01 10:00:00", 24, "BIG")
        photos("2024:05:02 10:00:00", 23, "SML")
        photos("2026:10:15 10:00:00", 24, "TET")
        photos("2026:10:16 10:00:00", 3, "TIN")
        photos("2026:10:14 10:00:00", 3, "BEF")
        photos("2026:10:22 10:00:00", 24, "END")
        photos("2026:10:23 10:00:00", 24, "AFT")

        earlier = jpeg_with_exif("2026:10:20 11:00:00", b"already-on-drive")
        write(self.card / "DCIM" / "OLD0001.JPG", earlier)
        legacy = self.drive / "2026-10-20" / "Photos" / "Horizontal" / "OLD0001.JPG"
        write(legacy, earlier)

        for number in range(30):
            write(
                self.drive / "2024-08-01" / "Photos" / "Horizontal" / f"HAVE{number:04d}.JPG",
                jpeg_with_exif("2024:08:01 09:00:00", f"have-{number}".encode()),
            )
        photos("2024:08:01 12:00:00", 2, "NEW")

        report = organizer.run_copy(self.card, self.drive)
        self.assertEqual(report.failed, 0)
        self.assertEqual(report.copied, 127)
        self.assertEqual(sum(1 for item in report.results if item.action == "skipped"), 1)
        self.assertTrue((self.drive / "2024-05-01" / "Photos" / "Horizontal" / "BIG0000.JPG").is_file())
        self.assertFalse((self.drive / "2024-05-02").exists())
        self.assertTrue((self.drive / "Other Days" / "Photos" / "Horizontal" / "SML0000.JPG").is_file())
        self.assertTrue((self.drive / "Tetons" / "2026-10-15" / "Photos" / "Horizontal" / "TET0000.JPG").is_file())
        self.assertTrue((self.drive / "Tetons" / "2026-10-22" / "Photos" / "Horizontal" / "END0000.JPG").is_file())
        self.assertFalse((self.drive / "Tetons" / "2026-10-16").exists())
        self.assertTrue((self.drive / "Tetons" / "Other Days" / "Photos" / "Horizontal" / "TIN0000.JPG").is_file())
        self.assertTrue((self.drive / "Other Days" / "Photos" / "Horizontal" / "BEF0000.JPG").is_file())
        self.assertFalse((self.drive / "Tetons" / "2026-10-14").exists())
        self.assertTrue((self.drive / "2026-10-23" / "Photos" / "Horizontal" / "AFT0000.JPG").is_file())
        self.assertFalse((self.drive / "Tetons" / "2026-10-23").exists())
        by_name = {item.source.name: item for item in report.results}
        self.assertEqual(by_name["OLD0001.JPG"].action, "skipped")
        self.assertEqual(by_name["OLD0001.JPG"].dest, legacy)
        self.assertFalse((self.drive / "Tetons" / "Other Days" / "Photos" / "Horizontal" / "OLD0001.JPG").exists())
        self.assertTrue((self.drive / "2024-08-01" / "Photos" / "Horizontal" / "NEW0000.JPG").is_file())
        self.assertFalse((self.drive / "Other Days" / "Photos" / "Horizontal" / "NEW0000.JPG").exists())
        self.assertEqual(os.listdir(self.internal), [])

        # A copied file still has to match size and checksum before it can be deleted.
        plan = organizer.deletion_plan(self.card, self.drive)
        eligible = {item["rel"] for item in plan["eligible"]}
        self.assertIn("DCIM/BIG0000.JPG", eligible)
        self.assertIn("DCIM/OLD0001.JPG", eligible)
        kept = self.drive / "2024-05-01" / "Photos" / "Horizontal" / "BIG0000.JPG"
        original = kept.read_bytes()
        kept.write_bytes(original[:-1] + b"Z")
        plan = organizer.deletion_plan(self.card, self.drive)
        self.assertNotIn("DCIM/BIG0000.JPG", {item["rel"] for item in plan["eligible"]})
        kept.write_bytes(original)

        one = self.root / "card2"
        drive2 = self.root / "drive2"
        write(one / "A.JPG", jpeg_with_exif("2026:10:15 10:00:00", b"solo"))
        park = organizer.Layout(min_day=1, trip_name="Park", trip_start="2026-10-15", trip_end="2026-10-15")
        moved = organizer.run_copy(one, drive2, layout=park)
        self.assertEqual(moved.failed, 0)
        self.assertTrue((drive2 / "Park" / "2026-10-15" / "Photos" / "Horizontal" / "A.JPG").is_file())

        plain = organizer.Layout(min_day=1, trip_name="", trip_start="2026-10-15", trip_end="2026-10-22")
        drive3 = self.root / "drive3"
        again = organizer.run_copy(one, drive3, layout=plain)
        self.assertEqual(again.failed, 0)
        self.assertTrue((drive3 / "2026-10-15" / "Photos" / "Horizontal" / "A.JPG").is_file())
        self.assertFalse((drive3 / "Tetons").exists())

        files = organizer.scan_card(self.card)
        summary = organizer.summarize(files, organizer.Layout(), self.drive)
        by_day = {day["day"]: day["folder"] for day in summary["days"]}
        self.assertEqual(by_day["2024-05-01"], "2024-05-01")
        self.assertEqual(by_day["2024-05-02"], "Other Days")
        self.assertEqual(by_day["2026-10-15"], "Tetons/2026-10-15")
        self.assertEqual(by_day["2026-10-16"], "Tetons/Other Days")
        self.assertEqual(by_day["2026-10-20"], "Tetons/Other Days")
        self.assertEqual(by_day["2026-10-22"], "Tetons/2026-10-22")
        self.assertEqual(by_day["2026-10-23"], "2026-10-23")
        self.assertEqual(by_day["2024-08-01"], "2024-08-01")
        self.assertEqual(summary["minDay"], 24)

        with self.assertRaises(organizer.OrganizerError):
            organizer.layout_from_request({"tripStart": "2026-10-22", "tripEnd": "2026-10-15"})
        with self.assertRaises(organizer.OrganizerError):
            organizer.layout_from_request({"minDay": "0"})
        with self.assertRaises(organizer.OrganizerError):
            organizer.layout_from_request({"tripName": "Other Days"})
        custom = organizer.layout_from_request({
            "minDay": "10",
            "tripName": "Park",
            "tripStart": "2026-10-01",
            "tripEnd": "2026-10-02",
        })
        self.assertEqual(custom, organizer.Layout(10, "Park", "2026-10-01", "2026-10-02"))

    def test_delete_needs_matching_size_and_hash(self):
        write(self.card / "A.JPG", jpeg_oriented("2024:04:04 04:04:04", 4000, 3000, 1, b"abc-photo"))
        organizer.run_copy(self.card, self.drive)
        dest = self.drive / "Other Days" / "Photos" / "Horizontal" / "A.JPG"
        original = dest.read_bytes()
        rel = "A.JPG"
        dest.write_bytes(original[:-1])
        plan = organizer.deletion_plan(self.card, self.drive)
        self.assertNotIn(rel, {item["rel"] for item in plan["eligible"]})
        self.assertTrue(any("checksum" in item["reason"].lower() or "missing" in item["reason"].lower() for item in plan["kept"]))
        dest.write_bytes(original[:-1] + b"Z")
        plan = organizer.deletion_plan(self.card, self.drive)
        self.assertNotIn(rel, {item["rel"] for item in plan["eligible"]})
        self.assertTrue((self.card / "A.JPG").exists())
        dest.write_bytes(original)
        plan = organizer.deletion_plan(self.card, self.drive)
        self.assertIn(rel, {item["rel"] for item in plan["eligible"]})
        # Delete still does not run unless delete_verified is called.
        self.assertTrue((self.card / "A.JPG").exists())


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
        self.assertIn("Photos/Vertical", page)
        self.assertIn("Videos/Horizontal", page)
        self.assertIn("Other Days", page)
        self.assertIn('value="Tetons"', page)
        self.assertIn("2026-10-15", page)
        self.assertIn("2026-10-22", page)
        self.assertIn('value="24"', page)
        status, headers, body = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(body["ok"])
        self.assertEqual(headers.get("Access-Control-Allow-Origin"), "*")
        self.assertEqual(headers.get("Access-Control-Allow-Private-Network"), "true")
        import http.client
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("OPTIONS", "/api/health", headers={
            "Origin": "https://daxtontessmer-ai.github.io",
            "Access-Control-Request-Private-Network": "true",
        })
        preflight = conn.getresponse()
        preflight.read()
        self.assertEqual(preflight.status, 204)
        self.assertEqual(preflight.getheader("Access-Control-Allow-Private-Network"), "true")
        conn.close()

    def test_copy_then_delete_requires_an_explicit_confirm(self):
        status, _, volumes = self.request("GET", "/api/volumes")
        self.assertEqual(status, 200)
        names = {item["name"] for item in volumes["volumes"]}
        self.assertEqual(names, {"PhotoDrive", "SD_CARD"})
        body = {"source": str(self.card), "dest": str(self.hdd), "rootName": "Sony"}
        status, _, summary = self.request("POST", "/api/scan", body)
        self.assertEqual(summary["photos"], 2)
        self.assertEqual({day["folder"] for day in summary["days"]}, {"Other Days"})
        self.assertEqual(summary["minDay"], 24)
        self.assertEqual(summary["tripName"], "Tetons")
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
        saved = self.hdd / "Sony" / "Other Days" / "Photos" / "Horizontal" / "DSC0100.JPG"
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
