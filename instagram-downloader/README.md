# Instagram downloader

This saves a public Instagram Reel or post onto the Mac. The iPhone app cannot download the file itself, because Daxton's Life is a static site. This helper runs on the MacBook, the same way Organize SD card does.

Paste a link, click **Download**, and the files land in a new folder:

```text
~/Downloads/Instagram/2026-10-29_150405_SHORTCODE/
```

A zip of that folder is saved next to it, and the page can download the zip too. A carousel keeps every video and every photo from that post. One Reel is one MP4.

It uses yt-dlp. It does not log in to Instagram, does not read the browser's cookies, and does not store a password. Stories, Highlights, profile pages, and private accounts are skipped.

## Install

Python 3.12 and ffmpeg are already on the PATH, in `~/bin`. No Homebrew and no sudo.

1. Open the `instagram-downloader` folder inside Daxton's Life.
2. Double-click **Install Instagram Downloader.command**.
3. The first time, the Mac may say the file can't be opened because it came from the internet. Control-click it, choose **Open**, then click **Open** again.

That copies the folder to `~/Applications/instagram-downloader` and installs the pinned packages into a private `.venv` there. The packages are downloaded from `pypi.org` and `files.pythonhosted.org`. That is the only network the installer uses.

## Start it

1. In Finder, open **Applications**, then **instagram-downloader**.
2. Double-click **Download Instagram.command**.
3. Safari opens a page called Instagram. Leave the Terminal window open. Closing it stops the downloader.

Then paste a link from Instagram's Share → Copy link. A link with `?igsh=` on the end is fine. Press Return or click **Download**.

In Daxton's Life, the **Instagram** pill in Links opens this page when the helper is running. On the iPhone it only shows these steps, because the phone cannot save files onto the Mac.

## What a download talks to

The downloader contacts Instagram (`www.instagram.com` and Instagram's media servers, `cdninstagram.com` and `fbcdn.net`) to fetch the public post and its files. ffmpeg, if the video needs it, only runs on the Mac. It does not check GitHub for updates, and it does not load yt-dlp plugins from the Mac.

The versions are pinned in `requirements.txt`:

| Package | Version | What it does |
|---|---|---|
| yt-dlp | 2026.10.26 | Finds the public video and saves it. Unlicense. |
| curl-cffi | 0.17.0 | Lets yt-dlp send the same kind of connection a browser sends, so Instagram's public logged-out page will answer. It does not log in. MIT. |
| cffi | 2.1.1 | Used by curl-cffi to talk to its bundled copy of libcurl. No network of its own. MIT. |
| pycparser | 3.11 | Used by cffi. No network of its own. BSD. |
| certifi | 2026.10.23 | The list of certificate authorities used to check HTTPS. No network of its own. MPL-2.0. |
| brotli | 1.2.1 | Unpacks compressed responses. No network of its own. MIT. |
