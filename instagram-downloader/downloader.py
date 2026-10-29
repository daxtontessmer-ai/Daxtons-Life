#!/usr/bin/env python3
"""Save a public Instagram Reel or post on this Mac.

yt-dlp does the downloading. This file does not log in, does not read a
browser's cookies, and does not store a password. Stories, highlights,
profiles, and private posts are refused before yt-dlp is called.
"""

from __future__ import annotations

import os
import re
import shutil

# Do not load yt-dlp plugins from the Mac. A plugin could add sites or extra network calls.
os.environ["YTDLP_NO_PLUGINS"] = "1"
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

MAX_LINKS = 8
MAX_VIDEO_BYTES = 1_000_000_000
MAX_IMAGE_BYTES = 40_000_000
_CODE = r"[A-Za-z0-9_-]{5,40}"
_POST_RE = re.compile(
    rf"https?://(?:www\.)?instagram\.com/(?:(?!share/)[^/?#]+/)?(?P<kind>p|tv|reels?)/(?P<code>{_CODE})(?=$|[\s?#]|/(?=$|[\s?#]))",
    re.IGNORECASE,
)
_STORY_RE = re.compile(r"instagram\.com/(?:stories|s)/", re.IGNORECASE)
_AUDIO_RE = re.compile(r"instagram\.com/reels?/audio/", re.IGNORECASE)
_SHARE_RE = re.compile(r"instagram\.com/share/", re.IGNORECASE)
_IG_RE = re.compile(r"instagram\.com|instagr\.am", re.IGNORECASE)

Progress = Callable[[dict], None]


class DownloaderError(Exception):
    """A problem we can explain in one sentence."""


def parse_links(text: str) -> list[str]:
    """Pull public post and Reel links out of pasted text, in order."""
    raw = text or ""
    if not raw.strip():
        raise DownloaderError("Paste an Instagram Reel or post link first.")
    found: list[str] = []
    seen: set[str] = set()
    for match in _POST_RE.finditer(raw):
        kind = match.group("kind").lower()
        code = match.group("code")
        if kind.startswith("reel") and code.lower() == "audio":
            continue
        if kind == "reels":
            kind = "reel"
        url = f"https://www.instagram.com/{kind}/{code}/"
        if url not in seen:
            seen.add(url)
            found.append(url)
    if found:
        if len(found) > MAX_LINKS:
            raise DownloaderError(f"Paste up to {MAX_LINKS} links at a time.")
        return found
    if _STORY_RE.search(raw):
        raise DownloaderError("Stories and Highlights are skipped. Paste a public Reel or post. No login is used.")
    if _AUDIO_RE.search(raw):
        raise DownloaderError("That is an audio page. Paste the Reel or the post itself.")
    if _SHARE_RE.search(raw):
        raise DownloaderError("That is a share link. Open it, then copy the address that contains /reel/ or /p/.")
    if _IG_RE.search(raw):
        raise DownloaderError("Paste one post or Reel. Profile pages, private accounts, and Stories are skipped.")
    raise DownloaderError("Paste an Instagram link, like instagram.com/reel/… or instagram.com/p/…")


def folder_stamp(when: datetime, urls: list[str]) -> str:
    stamp = when.strftime("%Y-%m-%d_%H%M%S")
    code = _POST_RE.search(urls[0]).group("code") if urls else "post"
    if len(urls) == 1:
        return f"{stamp}_{code}"
    return f"{stamp}_{len(urls)}-posts"


def unique_dir(root: Path, name: str) -> Path:
    path = root / name
    if not path.exists():
        return path
    for n in range(2, 50):
        alt = root / f"{name}-{n}"
        if not alt.exists():
            return alt
    raise DownloaderError("Couldn't make a new folder in Downloads.")


def allowed_cdn(url: str) -> bool:
    """True only for https files on Instagram's public media hosts."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return False
    if parsed.scheme != "https" or parsed.username or parsed.password:
        return False
    host = (parsed.hostname or "").lower().rstrip(".")
    return host == "cdninstagram.com" or host.endswith(".cdninstagram.com") or host == "fbcdn.net" or host.endswith(".fbcdn.net")


def _sniff_image(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(data) >= 12 and data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ".webp"
    return ""


class _StayOnCdn(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not allowed_cdn(newurl):
            raise DownloaderError("The photo address left Instagram's media servers.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def save_public_image(url: str, dest: Path) -> Path:
    if not allowed_cdn(url):
        raise DownloaderError("That photo address is not an Instagram media file.")
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://www.instagram.com/",
        "Accept": "image/avif,image/webp,image/*,*/*;q=0.8",
    })
    opener = urllib.request.build_opener(_StayOnCdn)
    try:
        with opener.open(req, timeout=60) as resp:
            if not allowed_cdn(resp.geturl()):
                raise DownloaderError("The photo address left Instagram's media servers.")
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if "text/html" in ctype:
                raise DownloaderError("Instagram sent a page instead of a photo.")
            data = resp.read(MAX_IMAGE_BYTES + 1)
    except DownloaderError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise DownloaderError("The photo didn't download. The post may be private, or Instagram asked us to wait.") from exc
    if len(data) > MAX_IMAGE_BYTES:
        raise DownloaderError("That photo is larger than this downloader allows.")
    ext = _sniff_image(data)
    if not ext:
        raise DownloaderError("That file is not a photo.")
    path = dest.with_suffix(ext)
    path.write_bytes(data)
    return path


def _largest_image_url(entry: dict) -> str:
    thumbs = list(entry.get("thumbnails") or [])
    if entry.get("thumbnail"):
        thumbs.append({"url": entry.get("thumbnail")})
    best = ""
    best_score = -1
    for thumb in thumbs:
        if not isinstance(thumb, dict):
            continue
        url = str(thumb.get("url") or "")
        if not allowed_cdn(url):
            continue
        width = int(thumb.get("width") or 0)
        height = int(thumb.get("height") or 0)
        score = width * height
        if score >= best_score:
            best = url
            best_score = score
    return best


def build_options(folder: Path, hook: Progress) -> dict:
    """yt-dlp settings. No cookies, no login, no update check, no config file."""
    partial = folder / ".partial"
    options = {
        "quiet": True,
        "no_warnings": False,
        "noprogress": True,
        "color": "never",
        "cachedir": False,
        "warn_when_outdated": False,
        "usenetrc": False,
        "cookiefile": None,
        "cookiesfrombrowser": None,
        "username": None,
        "password": None,
        "getcomments": False,
        "writeinfojson": False,
        "writedescription": False,
        "writethumbnail": False,
        "write_all_thumbnails": False,
        "writesubtitles": False,
        "writeautomaticsub": False,
        "noplaylist": False,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "restrictfilenames": True,
        "windowsfilenames": False,
        "overwrites": False,
        "continuedl": True,
        "retries": 3,
        "fragment_retries": 3,
        "extractor_retries": 2,
        "socket_timeout": 30,
        "max_filesize": MAX_VIDEO_BYTES,
        "geo_bypass": False,
        "nocheckcertificate": False,
        "enable_file_urls": False,
        # Case-insensitive full match. This is the post/Reel extractor only,
# not instagram:story, instagram:user, or instagram:tag.
"allowed_extractors": ["^instagram$"],
        "paths": {"home": str(folder), "temp": str(partial)},
        "outtmpl": {"default": "%(id)s.%(ext)s"},
        "progress_hooks": [hook],
        "ignoreerrors": False,
    }
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg:
        options["ffmpeg_location"] = str(Path(ffmpeg).parent)
    return options


def friendly(exc: BaseException) -> str:
    text = str(exc)
    low = text.lower()
    if "cancel" in low:
        return "Download cancelled."
    if "rate-limit" in low or "rate limit" in low or "please wait" in low:
        return "Instagram asked us to wait. Try that link again in a few minutes."
    if "login" in low or "private" in low or "registered users" in low or "empty media" in low:
        return "This post isn't available without an Instagram login. Private accounts and Stories are skipped on purpose."
    if "unsupported url" in low or "no suitable extractor" in low:
        return "That link is not a public Instagram Reel or post."
    if "no video" in low:
        return "There was no video in that part of the post."
    if "ffmpeg" in low:
        return "The video downloaded, but ffmpeg could not finish the file. ffmpeg should be on the PATH in ~/bin."
    return "That download didn't finish. Check that the Reel or post is public, then try again."


def _safe_stem(entry: dict, index: int) -> str:
    raw = str(entry.get("id") or f"item-{index}")
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "", raw)[:40]
    return f"{index:02d}-{cleaned or 'media'}"


def _resolve_entries(ydl, info: dict, depth: int = 0) -> list[dict]:
    if depth > 3 or not isinstance(info, dict):
        return []
    kind = info.get("_type")
    if kind in ("playlist", "multi_video"):
        found: list[dict] = []
        for entry in info.get("entries") or []:
            if isinstance(entry, dict):
                found.extend(_resolve_entries(ydl, entry, depth + 1))
        return found
    webpage = str(info.get("webpage_url") or info.get("url") or "")
    if kind == "url" and "instagram.com" in webpage:
        return _resolve_entries(ydl, ydl.extract_info(webpage, download=False), depth + 1)
    return [info]


def _new_files(folder: Path, before: set[Path]) -> list[Path]:
    found = []
    for path in folder.rglob("*"):
        if not path.is_file():
            continue
        if ".partial" in path.parts or path.name == ".DS_Store":
            continue
        if path.suffix.lower() in {".part", ".ytdl", ".temp"}:
            continue
        if path not in before:
            found.append(path)
    return sorted(found)


def download_urls(text: str, root: Path, on_progress: Optional[Progress] = None, cancel=None) -> dict:
    """Download every pasted link into one new folder and zip that folder."""
    urls = parse_links(text)
    root = Path(root).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    when = datetime.now()
    folder = unique_dir(root, folder_stamp(when, urls))
    folder.mkdir(parents=True)
    (folder / ".partial").mkdir(exist_ok=True)
    progress = on_progress or (lambda _event: None)
    cancelled = cancel

    def hook(event: dict) -> None:
        if cancelled is not None and cancelled.is_set():
            from yt_dlp.utils import DownloadCancelled
            raise DownloadCancelled("Cancelled")
        status = event.get("status")
        if status == "downloading":
            progress({
                "phase": "saving",
                "current": Path(str(event.get("filename") or "")).name,
                "downloaded": int(event.get("downloaded_bytes") or 0),
                "total": int(event.get("total_bytes") or event.get("total_bytes_estimate") or 0),
            })

    titles: list[str] = []
    saved: list[Path] = []
    warnings: list[str] = []
    try:
        import yt_dlp
        from yt_dlp.utils import DownloadCancelled, DownloadError
    except ImportError as exc:
        shutil.rmtree(folder, ignore_errors=True)
        raise DownloaderError("The installer hasn't been run yet. Double-click Install Instagram Downloader.command.") from exc

    try:
        with yt_dlp.YoutubeDL(build_options(folder, hook)) as ydl:
            total = len(urls)
            for url_index, url in enumerate(urls, start=1):
                if cancelled is not None and cancelled.is_set():
                    raise DownloaderError("Download cancelled.")
                progress({"phase": "looking", "current": url, "doneFiles": len(saved), "totalFiles": total})
                try:
                    info = ydl.extract_info(url, download=False)
                except DownloadCancelled as exc:
                    raise DownloaderError("Download cancelled.") from exc
                except DownloadError as exc:
                    warnings.append(friendly(exc))
                    continue
                title = str((info or {}).get("title") or "").strip()
                if title:
                    titles.append(title.splitlines()[0][:180])
                entries = _resolve_entries(ydl, info or {})
                if not entries:
                    warnings.append("That link didn't include a video or a photo.")
                    continue
                for entry_index, entry in enumerate(entries, start=1):
                    if cancelled is not None and cancelled.is_set():
                        raise DownloaderError("Download cancelled.")
                    stem = _safe_stem(entry, len(saved) + 1)
                    progress({
                        "phase": "saving",
                        "current": stem,
                        "doneFiles": len(saved),
                        "totalFiles": max(total, len(entries)),
                        "urlIndex": url_index,
                    })
                    before = set(folder.rglob("*"))
                    try:
                        if entry.get("formats"):
                            ydl.params["outtmpl"] = {"default": stem + ".%(ext)s"}
                            ydl.process_info(entry)
                            new_files = _new_files(folder, before)
                            videos = [path for path in new_files if path.suffix.lower() in {".mp4", ".mkv", ".webm", ".mov"}]
                            saved.extend(videos or new_files)
                        else:
                            image_url = _largest_image_url(entry)
                            if not image_url:
                                warnings.append(f"Slide {entry_index} had no public video or photo.")
                                continue
                            saved.append(save_public_image(image_url, folder / stem))
                    except DownloadCancelled as exc:
                        raise DownloaderError("Download cancelled.") from exc
                    except DownloaderError as exc:
                        warnings.append(str(exc))
                    except DownloadError as exc:
                        warnings.append(friendly(exc))
                    except Exception as exc:  # yt-dlp raises a few of its own types
                        if exc.__class__.__name__ == "DownloadCancelled":
                            raise DownloaderError("Download cancelled.") from exc
                        warnings.append(friendly(exc))
        if not saved:
            detail = warnings[0] if warnings else "Nothing was saved."
            raise DownloaderError(detail)
        lines = [
            "Public Instagram download. Personal copy on this Mac.",
            "No Instagram login was used.",
            "",
            *urls,
            "",
            *titles,
        ]
        (folder / "source.txt").write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        saved.append(folder / "source.txt")
        zip_path = root / f"{folder.name}.zip"
        _write_zip(folder, zip_path)
        progress({"phase": "done", "doneFiles": len(saved), "totalFiles": len(saved)})
        return {
            "folder": str(folder),
            "zip": str(zip_path),
            "files": [path.name for path in saved],
            "warnings": warnings,
            "title": titles[0] if titles else "",
        }
    except DownloaderError:
        if not saved:
            shutil.rmtree(folder, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(folder / ".partial", ignore_errors=True)


def _write_zip(folder: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(folder.rglob("*")):
            if not path.is_file() or ".partial" in path.parts or path.name == ".DS_Store":
                continue
            archive.write(path, arcname=str(Path(folder.name) / path.relative_to(folder)))
