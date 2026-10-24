"""Copy photos and videos from an SD card onto a hard drive, one folder per day.

Bytes are read from the card and written onto the destination drive. Nothing is
written to a temporary folder on the Mac's internal disk.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Tuple

CHUNK = 8 * 1024 * 1024
QT_EPOCH = datetime(1904, 1, 1, tzinfo=timezone.utc)
MANIFEST_DIR = ".sd-organizer"
MANIFEST_NAME = "verified.json"
COPYING_SUFFIX = ".copying"

PHOTO_EXT = {
    ".jpg", ".jpeg", ".png", ".heic", ".heif", ".arw", ".dng", ".tif", ".tiff",
    ".gif", ".webp", ".rw2", ".cr2", ".cr3", ".nef", ".orf", ".raf", ".raw",
}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mts", ".m2ts", ".mxf", ".avi", ".mpg", ".mpeg"}
SIDECAR_EXT = {".xml", ".thm"}

SKIP_DIRS = {
    ".trashes", ".spotlight-v100", ".fseventsd", ".temporaryitems",
    ".sd-organizer", "system volume information", "$recycle.bin",
    ".documentrevisions-v100",
}

ROOT_NAME_RE = re.compile(r"[^\\/\x00]{1,80}")
SIDECAR_SUFFIX_RE = re.compile(r"^(.*?)(?:M\d+|T\d+)$", re.IGNORECASE)
XML_CREATION_RE = re.compile(
    r"CreationDate\b[^>\n]*\bvalue\s*=\s*[\"']([^\"']+)[\"']",
    re.IGNORECASE,
)
XML_CREATION_TEXT_RE = re.compile(
    r"<CreationDate>\s*([^<]+?)\s*</CreationDate>",
    re.IGNORECASE,
)
ISO_LOCAL_RE = re.compile(
    r"(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})"
)


class OrganizerError(Exception):
    """A problem the person using the organizer can act on."""


class DiskFull(OrganizerError):
    """The destination drive cannot fit the next file."""


@dataclass
class MediaFile:
    path: Path
    kind: str  # photo, video, sidecar
    size: int
    captured: datetime
    day: str
    date_source: str  # exif, xml, quicktime, file, video
    video_path: Optional[Path] = None
    # Vertical when the picture is taller than it is wide after rotation. Square is Horizontal.
    orientation: str = "Horizontal"

    @property
    def name(self) -> str:
        return self.path.name


@dataclass
class FileResult:
    source: Path
    source_rel: str
    dest: Optional[Path]
    dest_rel: str
    action: str  # copied, renamed, skipped, failed
    kind: str
    day: str
    size: int
    sha256: str
    message: str


@dataclass
class CopyReport:
    results: List[FileResult] = field(default_factory=list)

    @property
    def copied(self) -> int:
        return sum(1 for r in self.results if r.action in ("copied", "renamed"))

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.results if r.action == "skipped")

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if r.action == "failed")


def volume_is_internal(path: Path, boot: Path = Path("/")) -> bool:
    """True when this folder sits on the same disk as the Mac itself.

    A real SD card or external drive is a separate mount, so its device id
    differs from the internal disk. A plain folder does not.
    """
    try:
        return path.stat().st_dev == boot.stat().st_dev
    except OSError:
        return True


def list_volumes(volumes_root: Path = Path("/Volumes"), boot: Path = Path("/")) -> List[dict]:
    root = Path(volumes_root)
    if not root.is_dir():
        return []
    found = []
    try:
        names = sorted(root.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        return []
    for path in names:
        if path.name.startswith(".") or path.is_symlink() or not path.is_dir():
            continue
        try:
            try:
                du = shutil.disk_usage(path)
                free, total = du.free, du.total
            except OSError:
                free, total = None, None
            found.append({
                "name": path.name,
                "path": str(path),
                "internal": volume_is_internal(path, boot),
                "free": free,
                "total": total,
            })
        except OSError:
            continue
    return found


def assert_external_volume(path: Path, boot: Path = Path("/")) -> None:
    if volume_is_internal(path, boot):
        raise OrganizerError(
            "That disk is the Mac's internal drive. Pick the SD card or the hard drive that is plugged in."
        )


def sanitize_root_name(name: str) -> str:
    cleaned = (name or "").strip()
    if not cleaned or cleaned in {".", ".."} or cleaned.startswith("."):
        raise OrganizerError("Type a folder name, like Sony.")
    if not ROOT_NAME_RE.fullmatch(cleaned) or "/" in cleaned or "\\" in cleaned:
        raise OrganizerError("The folder name can't include slashes.")
    return cleaned


def destination_root(volume: Path, root_name: str) -> Path:
    volume = Path(volume).resolve()
    dest = (volume / sanitize_root_name(root_name)).resolve()
    _assert_inside(dest, volume)
    return dest


def _assert_inside(path: Path, parent: Path) -> None:
    path = path.resolve()
    parent = parent.resolve()
    if path != parent and parent not in path.parents:
        raise OrganizerError("That folder is outside the drive you picked.")


def _skip_dir(name: str) -> bool:
    return name.lower() in SKIP_DIRS or name.startswith("._")


def iter_files(root: Path) -> Iterable[Path]:
    root = Path(root)
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if not _skip_dir(d)]
        for name in filenames:
            if name.startswith("._") or name == ".DS_Store" or name.endswith(COPYING_SUFFIX):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                if path.is_file():
                    yield path
            except OSError:
                continue


def kind_of(path: Path) -> Optional[str]:
    ext = path.suffix.lower()
    if ext in SIDECAR_EXT:
        return "sidecar"
    if ext in VIDEO_EXT:
        return "video"
    if ext in PHOTO_EXT:
        return "photo"
    return None


def sidecar_base(path: Path) -> str:
    match = SIDECAR_SUFFIX_RE.match(path.stem)
    return (match.group(1) if match else path.stem).lower()


def _parse_exif_string(value: str) -> Optional[datetime]:
    value = value.strip().strip("\x00")
    match = re.match(r"(\d{4}):(\d{2}):(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", value)
    if not match:
        match = re.match(r"(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})", value)
    if not match:
        return None
    parts = [int(p) for p in match.groups()]
    try:
        captured = datetime(*parts)
    except ValueError:
        return None
    if not 1990 <= captured.year <= 2100:
        return None
    return captured


def _ascii_value(buf: bytes, count: int, inline: bytes, offset: int) -> Optional[str]:
    if count <= 0 or count > 128:
        return None
    if count <= 4:
        raw = inline[:count]
    else:
        if offset < 0 or offset + count > len(buf):
            return None
        raw = buf[offset:offset + count]
    return raw.split(b"\x00", 1)[0].decode("latin1", "replace")


def _walk_ifd(buf: bytes, endian: str, offset: int, found: Dict[str, object], depth: int) -> None:
    if depth > 8 or offset < 0 or offset + 2 > len(buf):
        return
    count = struct.unpack_from(endian + "H", buf, offset)[0]
    if count > 512:
        return
    entry = offset + 2
    for _ in range(count):
        if entry + 12 > len(buf):
            return
        tag, typ, cnt = struct.unpack_from(endian + "HHI", buf, entry)
        inline = buf[entry + 8:entry + 12]
        value_off = struct.unpack_from(endian + "I", buf, entry + 8)[0]
        if tag == 0x8769 and typ == 4 and cnt >= 1:
            _walk_ifd(buf, endian, value_off, found, depth + 1)
        elif tag == 0x014A and typ == 4 and cnt >= 1 and depth < 6:
            # SubIFDs hold the full-size raw frame. The little thumbnail is not the picture.
            offsets = [value_off] if cnt == 1 else []
            if cnt > 1:
                for index in range(min(cnt, 8)):
                    pos = value_off + index * 4
                    if pos + 4 > len(buf):
                        break
                    offsets.append(struct.unpack_from(endian + "I", buf, pos)[0])
            for off in offsets:
                _walk_ifd(buf, endian, off, found, depth + 1)
        elif tag == 0x0112 and typ == 3 and cnt >= 1 and depth == 0 and "orientation" not in found:
            found["orientation"] = struct.unpack_from(endian + "H", inline)[0]
        elif tag in (0x0100, 0x0101) and typ in (3, 4) and cnt >= 1:
            number = struct.unpack_from(endian + "H", inline)[0] if typ == 3 else value_off
            if number > 0:
                key = "width" if tag == 0x0100 else "height"
                previous = found.get(key)
                if not isinstance(previous, int) or number > previous:
                    found[key] = number
        elif tag in (0x0132, 0x9003, 0x9004) and typ == 2:
            text = _ascii_value(buf, cnt, inline, value_off)
            key = {0x0132: "datetime", 0x9003: "original", 0x9004: "digitized"}[tag]
            if text and key not in found:
                found[key] = text
        entry += 12
    if entry + 4 <= len(buf):
        nxt = struct.unpack_from(endian + "I", buf, entry)[0]
        if nxt and nxt != offset:
            _walk_ifd(buf, endian, nxt, found, depth + 1)


def _tiff_facts(buf: bytes) -> Dict[str, object]:
    found: Dict[str, object] = {}
    if len(buf) < 8:
        return found
    if buf[:2] == b"II":
        endian = "<"
    elif buf[:2] == b"MM":
        endian = ">"
    else:
        return found
    if struct.unpack_from(endian + "H", buf, 2)[0] != 42:
        return found
    offset = struct.unpack_from(endian + "I", buf, 4)[0]
    _walk_ifd(buf, endian, offset, found, 0)
    return found


def _datetime_from_tiff(buf: bytes) -> Optional[datetime]:
    found = _tiff_facts(buf)
    for key in ("original", "digitized", "datetime"):
        text = found.get(key)
        if isinstance(text, str):
            captured = _parse_exif_string(text)
            if captured:
                return captured
    return None


def exif_datetime(path: Path) -> Optional[datetime]:
    """DateTimeOriginal from a JPEG or a TIFF-based raw file such as Sony ARW."""
    try:
        with path.open("rb") as handle:
            sig = handle.read(2)
            if sig == b"\xff\xd8":
                return _exif_from_jpeg(handle)
            if sig in (b"II", b"MM"):
                handle.seek(0)
                # EXIF for a raw file lives in the TIFF header at the start.
                return _datetime_from_tiff(handle.read(2 * 1024 * 1024))
    except OSError:
        return None
    return None


def _exif_from_jpeg(handle) -> Optional[datetime]:
    while True:
        marker_byte = handle.read(1)
        if not marker_byte:
            return None
        if marker_byte != b"\xff":
            continue
        marker = handle.read(1)
        while marker == b"\xff":
            marker = handle.read(1)
        if not marker or marker in (b"\xd8", b"\x01") or 0xD0 <= marker[0] <= 0xD9:
            if marker == b"\xd9":
                return None
            continue
        if marker == b"\xda":  # start of image data; the header is over
            return None
        length_bytes = handle.read(2)
        if len(length_bytes) < 2:
            return None
        size = struct.unpack(">H", length_bytes)[0]
        if size < 2:
            return None
        if marker == b"\xe1":
            payload = handle.read(size - 2)
            if payload.startswith(b"Exif\x00\x00"):
                return _datetime_from_tiff(payload[6:])
            continue
        handle.seek(size - 2, os.SEEK_CUR)


def _iter_atoms(handle, start: int, end: int):
    pos = start
    while pos + 8 <= end:
        handle.seek(pos)
        header = handle.read(8)
        if len(header) < 8:
            return
        size, kind = struct.unpack(">I4s", header)
        header_len = 8
        if size == 1:
            extra = handle.read(8)
            if len(extra) < 8:
                return
            size = struct.unpack(">Q", extra)[0]
            header_len = 16
        elif size == 0:
            size = end - pos
        if size < header_len or pos + size > end + 1:
            # A broken size would otherwise scan forever. Stop this level.
            if size < header_len:
                return
        atom_end = pos + size if size >= header_len else end
        if atom_end <= pos:
            return
        yield kind, pos + header_len, min(atom_end, end)
        pos = atom_end


def _parse_mvhd(payload: bytes) -> Optional[datetime]:
    if len(payload) < 8:
        return None
    version = payload[0]
    if version == 0 and len(payload) >= 8:
        created = struct.unpack_from(">I", payload, 4)[0]
    elif version == 1 and len(payload) >= 12:
        created = struct.unpack_from(">Q", payload, 4)[0]
    else:
        return None
    if created <= 0:
        return None
    moment = QT_EPOCH + timedelta(seconds=int(created))
    if not 1990 <= moment.year <= 2100:
        return None
    # QuickTime stores this in UTC. Use the Mac's timezone so the folder day
    # matches the day it was where the camera was, when no XML sidecar exists.
    return moment.astimezone().replace(tzinfo=None)


def quicktime_datetime(path: Path) -> Optional[datetime]:
    try:
        file_size = path.stat().st_size
    except OSError:
        return None
    if file_size < 16:
        return None
    try:
        with path.open("rb") as handle:
            moov = None
            for kind, payload, atom_end in _iter_atoms(handle, 0, file_size):
                if kind == b"moov":
                    moov = (payload, atom_end)
                    break
            if not moov:
                return None
            for kind, payload, atom_end in _iter_atoms(handle, moov[0], moov[1]):
                if kind == b"mvhd":
                    handle.seek(payload)
                    return _parse_mvhd(handle.read(min(64, atom_end - payload)))
    except OSError:
        return None
    return None


_SOF_MARKERS = {marker for marker in range(0xC0, 0xD0) if marker not in (0xC4, 0xC8, 0xCC)}


def classify_orientation(width: Optional[int], height: Optional[int]) -> str:
    """Taller than wide is Vertical. Square, landscape, and unknown go in Horizontal."""
    if not width or not height or width <= 0 or height <= 0:
        return "Horizontal"
    if height > width:
        return "Vertical"
    return "Horizontal"


def _apply_exif_orientation(width: Optional[int], height: Optional[int], orientation: int) -> Tuple[Optional[int], Optional[int]]:
    # Tags 5–8 turn the stored pixels on their side, so width and height trade places.
    if width and height and orientation in (5, 6, 7, 8):
        return height, width
    return width, height


def _jpeg_frame(path: Path) -> Tuple[Optional[int], Optional[int], int]:
    width = height = None
    orientation = 0
    try:
        with path.open("rb") as handle:
            if handle.read(2) != b"\xff\xd8":
                return None, None, 0
            while True:
                marker_byte = handle.read(1)
                if not marker_byte:
                    break
                if marker_byte != b"\xff":
                    continue
                marker = handle.read(1)
                while marker == b"\xff":
                    marker = handle.read(1)
                if not marker or marker in (b"\xd8", b"\x01") or 0xD0 <= marker[0] <= 0xD9:
                    if marker == b"\xd9":
                        break
                    continue
                if marker == b"\xda":
                    break
                length_bytes = handle.read(2)
                if len(length_bytes) < 2:
                    break
                size = struct.unpack(">H", length_bytes)[0]
                if size < 2:
                    break
                if marker[0] in _SOF_MARKERS and width is None and size >= 7:
                    data = handle.read(5)
                    if len(data) == 5:
                        _precision, height, width = struct.unpack(">BHH", data)
                    rest = size - 2 - 5
                    if rest > 0:
                        handle.seek(rest, os.SEEK_CUR)
                    continue
                if marker == b"\xe1":
                    payload = handle.read(size - 2)
                    if payload.startswith(b"Exif\x00\x00") and not orientation:
                        value = _tiff_facts(payload[6:]).get("orientation")
                        if isinstance(value, int):
                            orientation = value
                    continue
                handle.seek(size - 2, os.SEEK_CUR)
    except OSError:
        return None, None, 0
    return width, height, orientation


def _png_frame(path: Path) -> Tuple[Optional[int], Optional[int], int]:
    try:
        with path.open("rb") as handle:
            if handle.read(8) != b"\x89PNG\r\n\x1a\n":
                return None, None, 0
            width = height = None
            orientation = 0
            while True:
                header = handle.read(8)
                if len(header) < 8:
                    break
                length, kind = struct.unpack(">I4s", header)
                if length > 20_000_000:
                    break
                if kind == b"IHDR" and length >= 8 and width is None:
                    data = handle.read(8)
                    if len(data) == 8:
                        width, height = struct.unpack(">II", data)
                    leftover = length - 8
                    if leftover > 0:
                        handle.seek(leftover, os.SEEK_CUR)
                    handle.seek(4, os.SEEK_CUR)
                    continue
                if kind == b"eXIf" and length <= 2 * 1024 * 1024:
                    payload = handle.read(length)
                    value = _tiff_facts(payload).get("orientation")
                    if isinstance(value, int):
                        orientation = orientation or value
                    handle.seek(4, os.SEEK_CUR)
                    continue
                if kind == b"IEND":
                    break
                handle.seek(length + 4, os.SEEK_CUR)
            return width, height, orientation
    except OSError:
        return None, None, 0


def _gif_frame(path: Path) -> Tuple[Optional[int], Optional[int], int]:
    try:
        with path.open("rb") as handle:
            if handle.read(6) not in (b"GIF87a", b"GIF89a"):
                return None, None, 0
            raw = handle.read(4)
            if len(raw) < 4:
                return None, None, 0
            width, height = struct.unpack("<HH", raw)
            return width, height, 0
    except OSError:
        return None, None, 0


def _heif_frame(path: Path) -> Tuple[Optional[int], Optional[int]]:
    """Pixel size after the HEIF rotation tag. Rotation is already applied."""
    try:
        file_size = path.stat().st_size
    except OSError:
        return None, None
    width = height = None
    quarter_turns = 0
    try:
        with path.open("rb") as handle:
            def walk(start: int, end: int, depth: int) -> None:
                nonlocal width, height, quarter_turns
                if depth > 8:
                    return
                for kind, payload, atom_end in _iter_atoms(handle, start, end):
                    if kind == b"ispe" and width is None:
                        handle.seek(payload)
                        data = handle.read(12)
                        if len(data) >= 12:
                            width, height = struct.unpack_from(">II", data, 4)
                    elif kind == b"irot":
                        handle.seek(payload)
                        data = handle.read(5)
                        if len(data) >= 5:
                            quarter_turns = data[4] & 3
                    elif kind in (b"meta", b"iprp", b"ipco", b"moov") and atom_end - payload > 8:
                        walk(payload, atom_end, depth + 1)

            walk(0, file_size, 0)
    except OSError:
        return None, None
    if width and height and quarter_turns in (1, 3):
        width, height = height, width
    return width, height


def _tiff_photo_frame(path: Path) -> Tuple[Optional[int], Optional[int], int]:
    try:
        with path.open("rb") as handle:
            facts = _tiff_facts(handle.read(8 * 1024 * 1024))
    except OSError:
        return None, None, 0
    width = facts.get("width")
    height = facts.get("height")
    orientation = facts.get("orientation")
    return (
        int(width) if isinstance(width, int) else None,
        int(height) if isinstance(height, int) else None,
        int(orientation) if isinstance(orientation, int) else 0,
    )


def photo_orientation(path: Path) -> str:
    """Displayed orientation from the EXIF orientation tag and the pixel size."""
    ext = path.suffix.lower()
    if ext in {".jpg", ".jpeg", ".thm"}:
        width, height, orientation = _jpeg_frame(path)
        width, height = _apply_exif_orientation(width, height, orientation)
    elif ext == ".png":
        width, height, orientation = _png_frame(path)
        width, height = _apply_exif_orientation(width, height, orientation)
    elif ext == ".gif":
        width, height, _orientation = _gif_frame(path)
    elif ext in {".heic", ".heif", ".avif"}:
        width, height = _heif_frame(path)
    elif ext in {".tif", ".tiff", ".arw", ".dng", ".nef", ".cr2", ".orf", ".raf", ".rw2", ".raw"}:
        width, height, orientation = _tiff_photo_frame(path)
        width, height = _apply_exif_orientation(width, height, orientation)
    else:
        return "Horizontal"
    return classify_orientation(width, height)


def _matrix_swaps(a: int, b: int, c: int, d: int) -> bool:
    """True for a 90° or 270° QuickTime matrix. 0° and 180° keep the stored shape."""
    def near(value: int, target: int) -> bool:
        return abs(value - target) <= 0x2000

    return near(a, 0) and near(d, 0) and near(abs(b), 0x10000) and near(abs(c), 0x10000)


def _parse_tkhd(payload: bytes) -> Optional[Tuple[int, int, bool]]:
    if not payload:
        return None
    version = payload[0]
    if version == 0:
        matrix_at, wh_at, need = 40, 76, 84
    elif version == 1:
        matrix_at, wh_at, need = 52, 88, 96
    else:
        return None
    if len(payload) < need:
        return None
    a, b, _u, c, d, _v, _tx, _ty, _w = struct.unpack_from(">9i", payload, matrix_at)
    width = struct.unpack_from(">I", payload, wh_at)[0] >> 16
    height = struct.unpack_from(">I", payload, wh_at + 4)[0] >> 16
    if width <= 0 or height <= 0:
        return None
    return width, height, _matrix_swaps(a, b, c, d)


def _mp4_display_size(path: Path) -> Optional[Tuple[int, int]]:
    """Stored frame size with the track matrix applied. This is the bundled reader."""
    try:
        file_size = path.stat().st_size
    except OSError:
        return None
    if file_size < 16:
        return None
    tracks = []
    try:
        with path.open("rb") as handle:
            moov = None
            for kind, payload, atom_end in _iter_atoms(handle, 0, file_size):
                if kind == b"moov":
                    moov = (payload, atom_end)
                    break
            if not moov:
                return None
            for kind, payload, atom_end in _iter_atoms(handle, moov[0], moov[1]):
                if kind != b"trak":
                    continue
                size = None
                handler = b""
                for child, child_payload, child_end in _iter_atoms(handle, payload, atom_end):
                    if child == b"tkhd":
                        handle.seek(child_payload)
                        size = _parse_tkhd(handle.read(min(160, child_end - child_payload)))
                    elif child == b"mdia":
                        for grand, grand_payload, _grand_end in _iter_atoms(handle, child_payload, child_end):
                            if grand == b"hdlr":
                                handle.seek(grand_payload + 8)
                                handler = handle.read(4)
                                break
                if size:
                    tracks.append((handler, size))
    except OSError:
        return None
    video = [item for item in tracks if item[0] == b"vide"]
    pool = video or tracks
    if not pool:
        return None
    _handler, (width, height, swaps) = max(pool, key=lambda item: item[1][0] * item[1][1])
    if swaps:
        width, height = height, width
    return width, height


def _rotation_degrees(stream: dict) -> int:
    tags = stream.get("tags") or {}
    values = []
    if isinstance(tags, dict) and "rotate" in tags:
        values.append(tags["rotate"])
    for side in stream.get("side_data_list") or []:
        if isinstance(side, dict) and "rotation" in side:
            values.append(side["rotation"])
    for value in values:
        try:
            return int(float(str(value)))
        except (TypeError, ValueError):
            continue
    return 0


def _display_size_from_probe(raw: bytes) -> Optional[Tuple[int, int]]:
    try:
        data = json.loads(raw.decode("utf-8", "replace"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    streams = data.get("streams") if isinstance(data, dict) else None
    if not streams or not isinstance(streams, list):
        return None
    stream = streams[0]
    if not isinstance(stream, dict):
        return None
    width, height = stream.get("width"), stream.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return None
    if abs(_rotation_degrees(stream)) % 180 == 90:
        width, height = height, width
    return width, height


def _ffprobe_display_size(path: Path) -> Optional[Tuple[int, int]]:
    """Use ffprobe when it is installed. The built-in reader covers MP4 and MOV without it."""
    binary = shutil.which("ffprobe")
    if not binary:
        return None
    try:
        completed = subprocess.run(
            [
                binary,
                "-v", "error",
                "-select_streams", "v:0",
                "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
                "-of", "json",
                os.fspath(path),
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if completed.returncode != 0:
        return None
    return _display_size_from_probe(completed.stdout)


def video_orientation(path: Path) -> str:
    size = _mp4_display_size(path)
    if size is None:
        size = _ffprobe_display_size(path)
    if size is None:
        return "Horizontal"
    return classify_orientation(size[0], size[1])


def _parse_iso_local(value: str) -> Optional[datetime]:
    # Keep the date and clock time written by the camera. The offset is the
    # camera's own zone; shifting it to UTC would put late-night clips on the wrong day.
    match = ISO_LOCAL_RE.match(value.strip())
    if not match:
        return None
    parts = [int(p) for p in match.groups()]
    try:
        captured = datetime(*parts)
    except ValueError:
        return None
    if not 1990 <= captured.year <= 2100:
        return None
    return captured


def xml_datetime(path: Path) -> Optional[datetime]:
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            raw = handle.read(min(size, 1024 * 1024))
    except OSError:
        return None
    text = raw.decode("utf-8", "replace")
    match = XML_CREATION_RE.search(text) or XML_CREATION_TEXT_RE.search(text)
    if not match:
        return None
    return _parse_iso_local(match.group(1))


def file_datetime(path: Path) -> datetime:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return datetime.now()


def _day(captured: datetime) -> str:
    return captured.strftime("%Y-%m-%d")


def _pick_xml(video: Path, sidecars: List[Path]) -> Optional[Path]:
    base = video.stem.lower()
    matches = [p for p in sidecars if p.suffix.lower() == ".xml" and sidecar_base(p) == base]
    if not matches:
        return None
    same_dir = [p for p in matches if p.parent == video.parent]
    pool = same_dir or matches
    return sorted(pool, key=lambda p: str(p))[0]


def scan_card(root: Path) -> List[MediaFile]:
    """Every photo, video, and Sony sidecar on the card, with the day it was taken."""
    root = Path(root)
    photos: List[Path] = []
    videos: List[Path] = []
    sidecars: List[Path] = []
    for path in iter_files(root):
        kind = kind_of(path)
        if kind == "photo":
            photos.append(path)
        elif kind == "video":
            videos.append(path)
        elif kind == "sidecar":
            sidecars.append(path)

    media: List[MediaFile] = []
    video_records: Dict[Path, MediaFile] = {}
    for path in photos:
        captured = exif_datetime(path)
        source = "exif" if captured else "file"
        if captured is None:
            captured = file_datetime(path)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        media.append(MediaFile(
            path, "photo", size, captured, _day(captured), source,
            orientation=photo_orientation(path),
        ))

    for path in videos:
        xml_path = _pick_xml(path, sidecars)
        captured = xml_datetime(xml_path) if xml_path else None
        source = "xml" if captured else ""
        if captured is None:
            captured = quicktime_datetime(path)
            source = "quicktime" if captured else ""
        if captured is None:
            captured = file_datetime(path)
            source = "file"
        try:
            size = path.stat().st_size
        except OSError:
            continue
        record = MediaFile(
            path, "video", size, captured, _day(captured), source,
            orientation=video_orientation(path),
        )
        media.append(record)
        video_records[path] = record

    by_base: Dict[str, List[MediaFile]] = {}
    for record in video_records.values():
        by_base.setdefault(record.path.stem.lower(), []).append(record)

    paired: List[MediaFile] = []
    unpaired: List[MediaFile] = []
    for path in sidecars:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        candidates = by_base.get(sidecar_base(path), [])
        video: Optional[MediaFile] = None
        if len(candidates) == 1:
            video = candidates[0]
        elif candidates:
            same_dir = [c for c in candidates if c.path.parent == path.parent]
            pool = same_dir or candidates
            video = sorted(pool, key=lambda c: str(c.path))[0]
        if video:
            paired.append(MediaFile(
                path, "sidecar", size, video.captured, video.day, "video", video.path,
                orientation=video.orientation,
            ))
        else:
            captured = xml_datetime(path) if path.suffix.lower() == ".xml" else None
            source = "xml" if captured else "file"
            if captured is None:
                captured = file_datetime(path)
            orientation = photo_orientation(path) if path.suffix.lower() == ".thm" else "Horizontal"
            unpaired.append(MediaFile(
                path, "sidecar", size, captured, _day(captured), source, orientation=orientation,
            ))

    by_video: Dict[Path, List[MediaFile]] = {}
    for item in paired:
        by_video.setdefault(item.video_path, []).append(item)  # type: ignore[arg-type]
    ordered: List[MediaFile] = []
    for item in media:
        ordered.append(item)
        if item.kind == "video":
            ordered.extend(sorted(by_video.get(item.path, []), key=lambda s: s.name.lower()))
    ordered.extend(sorted(unpaired, key=lambda s: str(s.path).lower()))
    return ordered


def summarize(files: List[MediaFile]) -> dict:
    days: Dict[str, dict] = {}
    fallback = 0
    for item in files:
        bucket = days.setdefault(item.day, {
            "day": item.day, "photos": 0, "videos": 0, "sidecars": 0, "bytes": 0,
            "photoVertical": 0, "photoHorizontal": 0, "videoVertical": 0, "videoHorizontal": 0,
        })
        if item.kind == "photo":
            bucket["photos"] += 1
            key = "photoVertical" if item.orientation == "Vertical" else "photoHorizontal"
            bucket[key] += 1
        elif item.kind == "video":
            bucket["videos"] += 1
            key = "videoVertical" if item.orientation == "Vertical" else "videoHorizontal"
            bucket[key] += 1
        else:
            bucket["sidecars"] += 1
        bucket["bytes"] += item.size
        if item.date_source == "file":
            fallback += 1
    return {
        "photos": sum(1 for f in files if f.kind == "photo"),
        "videos": sum(1 for f in files if f.kind == "video"),
        "sidecars": sum(1 for f in files if f.kind == "sidecar"),
        "bytes": sum(f.size for f in files),
        "fallbackDates": fallback,
        "days": [days[key] for key in sorted(days)],
    }


def sha256_file(path: Path, on_chunk: Optional[Callable[[int], None]] = None) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
            if on_chunk:
                on_chunk(len(chunk))
    return digest.hexdigest()


def _copying_name(name: str) -> str:
    extra = COPYING_SUFFIX
    if len(name.encode("utf-8")) + len(extra) <= 240:
        return name + extra
    stem, ext = os.path.splitext(name)
    trimmed = stem
    while trimmed and len((trimmed + ext + extra).encode("utf-8")) > 240:
        trimmed = trimmed[:-1]
    return (trimmed or "file") + ext + extra


def copy_verified(
    src: Path,
    dest: Path,
    known_hash: Optional[str] = None,
    on_chunk: Optional[Callable[[int], None]] = None,
) -> str:
    """Stream src onto dest on the same drive, then checksum the file that landed there.

    The unfinished file lives next to the final name (on the hard drive), never
    in the Mac's temp folder. If the checksum does not match, the copy is removed.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_name(_copying_name(dest.name))
    # Guard: partial must stay in the destination folder.
    if partial.parent != dest.parent:
        raise OrganizerError("Could not prepare a file on the hard drive.")
    digest = hashlib.sha256()
    try:
        with src.open("rb") as source, partial.open("wb") as target:
            while True:
                chunk = source.read(CHUNK)
                if not chunk:
                    break
                target.write(chunk)
                digest.update(chunk)
                if on_chunk:
                    on_chunk(len(chunk))
            target.flush()
            os.fsync(target.fileno())
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise OrganizerError(
            f"Couldn't copy {src.name}. Leave the card and the drive plugged in. ({exc.strerror or exc})"
        ) from exc
    written = digest.hexdigest()
    if known_hash and known_hash != written:
        partial.unlink(missing_ok=True)
        raise OrganizerError(f"{src.name} changed while it was being read. It was not kept.")
    try:
        os.replace(partial, dest)
    except OSError as exc:
        partial.unlink(missing_ok=True)
        raise OrganizerError(f"Couldn't save {dest.name} on the drive. ({exc.strerror or exc})") from exc
    try:
        checked = sha256_file(dest)
        same_size = dest.stat().st_size == src.stat().st_size
    except OSError as exc:
        dest.unlink(missing_ok=True)
        raise OrganizerError(f"Couldn't re-read {dest.name} to check it. ({exc.strerror or exc})") from exc
    if checked != written or not same_size:
        dest.unlink(missing_ok=True)
        raise OrganizerError(
            f"{src.name} failed the checksum after copying, so that copy was removed from the drive. Try again."
        )
    try:
        st = src.stat()
        os.utime(dest, (st.st_atime, st.st_mtime))
    except OSError:
        pass
    try:
        folder = os.open(dest.parent, os.O_RDONLY)
    except OSError:
        folder = None
    if folder is not None:
        try:
            os.fsync(folder)
        except OSError:
            pass
        finally:
            os.close(folder)
    return checked


def _hash_cache_key(path: Path) -> Tuple[str, int, int]:
    st = path.stat()
    return (str(path), st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))


def _cached_hash(path: Path, cache: Dict[Tuple[str, int, int], str]) -> str:
    key = _hash_cache_key(path)
    if key not in cache:
        cache[key] = sha256_file(path)
    return cache[key]


def _orientation_name(item: MediaFile) -> str:
    return "Vertical" if item.orientation == "Vertical" else "Horizontal"


def _same_size_under(folder: Path, size: int) -> List[Path]:
    """Same-size files already stored for this day, including the older Photos/Videos layout."""
    if not folder.is_dir():
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(folder, followlinks=False):
        dirnames[:] = [name for name in dirnames if not _skip_dir(name) and not name.startswith(".")]
        for name in filenames:
            if name.startswith(".") or name.endswith(COPYING_SUFFIX):
                continue
            path = Path(dirpath) / name
            if path.is_symlink():
                continue
            try:
                if path.is_file() and path.stat().st_size == size:
                    found.append(path)
            except OSError:
                continue
    return found


def _unique_name(folder: Path, preferred: str) -> str:
    if not (folder / preferred).exists():
        return preferred
    stem, ext = os.path.splitext(preferred)
    for number in range(2, 10000):
        candidate = f"{stem}_{number}{ext}"
        if not (folder / candidate).exists():
            return candidate
    raise OrganizerError(f"Too many files are already named {preferred}.")


def _contains(parent: Path, path: Path) -> bool:
    parent_resolved = parent.resolve()
    path_resolved = path.resolve()
    return path_resolved == parent_resolved or parent_resolved in path_resolved.parents


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.name


def manifest_path(dest_root: Path) -> Path:
    return Path(dest_root) / MANIFEST_DIR / MANIFEST_NAME


def load_manifest(dest_root: Path) -> dict:
    path = manifest_path(dest_root)
    if not path.is_file():
        return {"version": 1, "files": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"version": 1, "files": []}
    if not isinstance(data, dict) or not isinstance(data.get("files"), list):
        return {"version": 1, "files": []}
    return data


def save_manifest(dest_root: Path, data: dict) -> None:
    path = manifest_path(dest_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + COPYING_SUFFIX)
    temporary.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _remember(manifest: dict, record: dict) -> None:
    files = manifest.setdefault("files", [])
    key = (record.get("sha256"), record.get("sourceRel"), record.get("sourceName"), record.get("size"))
    for existing in files:
        existing_key = (existing.get("sha256"), existing.get("sourceRel"), existing.get("sourceName"), existing.get("size"))
        if existing_key == key:
            existing.update(record)
            return
    files.append(record)


def cleanup_partials(dest_root: Path) -> None:
    root = Path(dest_root)
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = [d for d in dirnames if d == MANIFEST_DIR or not _skip_dir(d)]
        for name in filenames:
            if name.endswith(COPYING_SUFFIX):
                try:
                    (Path(dirpath) / name).unlink()
                except OSError:
                    pass


def _ensure_space(dest_root: Path, size: int) -> None:
    target = dest_root if dest_root.exists() else dest_root.parent
    try:
        free = shutil.disk_usage(target).free
    except OSError as exc:
        raise OrganizerError(f"Couldn't check free space on the drive. ({exc.strerror or exc})") from exc
    # Leave a little room so the drive itself is not packed completely solid.
    if size + (8 * 1024 * 1024) > free:
        raise DiskFull(
            "The hard drive is out of free space. Copying stopped. Files already copied were checked and kept."
        )


def place_file(
    item: MediaFile,
    source_root: Path,
    dest_root: Path,
    cache: Dict[Tuple[str, int, int], str],
    manifest: dict,
    on_fraction: Optional[Callable[[float, str], None]] = None,
) -> FileResult:
    folder_name = "Photos" if item.kind == "photo" else "Videos"
    orient = _orientation_name(item)
    dest_dir = dest_root / item.day / folder_name / orient
    if not _contains(dest_root, dest_dir):
        raise OrganizerError("Refusing to write outside the folder you picked.")
    rel = _relative(item.path, source_root)
    # Look through the whole day, so a copy from before Vertical/Horizontal is not copied again.
    same_size = _same_size_under(dest_root / item.day, item.size)
    source_hash: Optional[str] = None
    if same_size:
        hashed = 0

        def _hashed(n: int, total: int = item.size) -> None:
            nonlocal hashed
            hashed += n
            if on_fraction and total:
                on_fraction(min(1.0, hashed / total), "checking")

        source_hash = sha256_file(item.path, _hashed)
        for existing in same_size:
            if _cached_hash(existing, cache) == source_hash:
                _remember(manifest, {
                    "sha256": source_hash,
                    "size": item.size,
                    "dest": _relative(existing, dest_root),
                    "sourceName": item.name,
                    "sourceRel": rel,
                    "kind": item.kind,
                    "day": item.day,
                    "orientation": orient,
                    "verified": True,
                })
                return FileResult(
                    item.path, rel, existing, _relative(existing, dest_root),
                    "skipped", item.kind, item.day, item.size, source_hash,
                    f"Skipped {item.name} — the same file is already on the drive.",
                )
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OrganizerError(f"Couldn't create a folder on the drive. ({exc.strerror or exc})") from exc
    final_name = _unique_name(dest_dir, item.name)
    action = "renamed" if final_name != item.name else "copied"
    dest = dest_dir / final_name
    if not _contains(dest_root, dest):
        raise OrganizerError("Refusing to write outside the folder you picked.")
    _ensure_space(dest_root, item.size)
    written = 0

    def _wrote(n: int, total: int = item.size) -> None:
        nonlocal written
        written += n
        if on_fraction and total:
            on_fraction(min(1.0, written / total), "copying")

    digest = copy_verified(item.path, dest, known_hash=source_hash, on_chunk=_wrote)
    cache[_hash_cache_key(dest)] = digest
    _remember(manifest, {
        "sha256": digest,
        "size": item.size,
        "dest": _relative(dest, dest_root),
        "sourceName": item.name,
        "sourceRel": rel,
        "kind": item.kind,
        "day": item.day,
        "orientation": orient,
        "verified": True,
    })
    landed = f"{item.day}/{folder_name}/{orient}"
    if action == "renamed":
        message = (
            f"Saved {item.name} as {final_name} in {landed} — a different file already used that name, so it was not overwritten."
        )
    else:
        message = f"Copied {item.name} into {landed}"
    return FileResult(
        item.path, rel, dest, _relative(dest, dest_root),
        action, item.kind, item.day, item.size, digest, message,
    )


def run_copy(
    source_root: Path,
    dest_root: Path,
    on_progress: Optional[Callable[[dict], None]] = None,
) -> CopyReport:
    source_root = Path(source_root).resolve()
    dest_root = Path(dest_root).resolve()
    if source_root == dest_root or source_root in dest_root.parents or dest_root in source_root.parents:
        raise OrganizerError("The card and the folder on the drive have to be different places.")
    files = scan_card(source_root)
    total_bytes = sum(item.size for item in files)
    report = CopyReport()

    def progress(phase: str, done_bytes: int, done_files: int, current: str, last: str = "") -> None:
        if on_progress:
            on_progress({
                "phase": phase,
                "doneBytes": done_bytes,
                "totalBytes": total_bytes,
                "doneFiles": done_files,
                "totalFiles": len(files),
                "current": current,
                "last": last,
            })

    progress("ready", 0, 0, "")
    cleanup_partials(dest_root)
    manifest = load_manifest(dest_root)
    cache: Dict[Tuple[str, int, int], str] = {}
    done_bytes = 0
    stop = False
    for index, item in enumerate(files, start=1):
        progress("copying", done_bytes, index - 1, item.name)

        def on_fraction(fraction: float, phase: str, base: int = done_bytes, size: int = item.size, name: str = item.name) -> None:
            progress(phase, base + int(size * fraction), index - 1, name)

        try:
            result = place_file(item, source_root, dest_root, cache, manifest, on_fraction)
        except DiskFull as exc:
            result = FileResult(
                item.path, _relative(item.path, source_root), None, "",
                "failed", item.kind, item.day, item.size, "", str(exc),
            )
            stop = True
        except OrganizerError as exc:
            result = FileResult(
                item.path, _relative(item.path, source_root), None, "",
                "failed", item.kind, item.day, item.size, "", str(exc),
            )
        report.results.append(result)
        done_bytes += item.size
        save_manifest(dest_root, manifest)
        progress("copying", done_bytes, index, item.name, result.message)
        if stop:
            for rest in files[index:]:
                report.results.append(FileResult(
                    rest.path, _relative(rest.path, source_root), None, "",
                    "failed", rest.kind, rest.day, rest.size, "",
                    "Not copied — the hard drive is out of free space.",
                ))
            break
    if on_progress:
        on_progress({
            "phase": "done" if not stop else "stopped",
            "doneBytes": total_bytes if not stop else done_bytes,
            "totalBytes": total_bytes,
            "doneFiles": len(report.results),
            "totalFiles": len(files),
            "current": "",
        })
    return report


def _manifest_candidates(manifest: dict, name: str, rel: str, size: int) -> List[dict]:
    found = []
    for record in manifest.get("files", []):
        if not record.get("verified"):
            continue
        if int(record.get("size") or -1) != size:
            continue
        if record.get("sourceRel") == rel or record.get("sourceName") == name:
            found.append(record)
    return found


def deletion_plan(source_root: Path, dest_root: Path) -> dict:
    """Say what on the card is safe to delete. Does not delete anything."""
    source_root = Path(source_root).resolve()
    dest_root = Path(dest_root).resolve()
    manifest = load_manifest(dest_root)
    eligible = []
    kept = []
    for path in iter_files(source_root):
        kind = kind_of(path)
        rel = _relative(path, source_root)
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if kind is None:
            continue
        records = _manifest_candidates(manifest, path.name, rel, size)
        if not records:
            kept.append({
                "name": path.name,
                "rel": rel,
                "size": size,
                "reason": "It has not been verified on the drive.",
            })
            continue
        try:
            source_hash = sha256_file(path)
        except OSError:
            kept.append({
                "name": path.name,
                "rel": rel,
                "size": size,
                "reason": "The card couldn't be read just now.",
            })
            continue
        record = next((r for r in records if r.get("sha256") == source_hash), None)
        if record is None:
            kept.append({
                "name": path.name,
                "rel": rel,
                "size": size,
                "reason": "The file on the card does not match the copy that was checked.",
            })
            continue
        dest = dest_root / record["dest"]
        try:
            dest_ok = dest.is_file() and not dest.is_symlink() and dest.stat().st_size == size
            dest_ok = dest_ok and sha256_file(dest) == source_hash
            _assert_inside(dest, dest_root)
        except (OSError, OrganizerError):
            dest_ok = False
        if not dest_ok:
            kept.append({
                "name": path.name,
                "rel": rel,
                "size": size,
                "reason": "The copy on the drive is missing or failed the checksum.",
            })
            continue
        eligible.append({
            "name": path.name,
            "rel": rel,
            "size": size,
            "sha256": source_hash,
            "dest": record["dest"],
            "day": record.get("day") or "",
            "kind": kind,
        })
    return {
        "eligible": eligible,
        "kept": kept,
        "eligibleBytes": sum(item["size"] for item in eligible),
        "keptCount": len(kept),
    }


def delete_verified(source_root: Path, dest_root: Path, only_rels: Iterable[str]) -> dict:
    """Delete card files that are still checksum-verified on the drive.

    ``only_rels`` is the set the person just reviewed. Anything else is left alone.
    """
    source_root = Path(source_root).resolve()
    dest_root = Path(dest_root).resolve()
    allowed = set(only_rels)
    plan = deletion_plan(source_root, dest_root)
    deleted = []
    skipped = []
    eligible_rels = {item["rel"] for item in plan["eligible"]}
    for rel in sorted(allowed):
        if rel not in eligible_rels:
            skipped.append({"rel": rel, "reason": "It was not verified on the drive, so it was left on the card."})
            continue
        path = (source_root / rel).resolve()
        try:
            _assert_inside(path, source_root)
        except OrganizerError:
            skipped.append({"rel": rel, "reason": "That path is outside the card."})
            continue
        if not path.is_file() or path.is_symlink():
            skipped.append({"rel": rel, "reason": "It is no longer on the card."})
            continue
        try:
            path.unlink()
        except OSError as exc:
            skipped.append({"rel": rel, "reason": exc.strerror or "The card would not delete it. Unlock the card's write-protect switch."})
            continue
        deleted.append(rel)
    return {
        "deleted": deleted,
        "skipped": skipped,
        "kept": [item for item in plan["kept"] if item["rel"] not in allowed],
    }
