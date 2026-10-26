# Changelog

Every commit gets a summary and timestamp here (Central Time). Newest first.

## 2026-10-25

- **10:20 PM CT — v9: Video Converter** (`Beta`)
  Beta now has a Links section with a Video Converter pill. Pick a video, including an iPhone .mov, and convert it on the device into MP4, MOV, WebM, MKV, AVI, GIF, MP3, or ZIP. MP4 is marked "Best for Blackboard / uploads" and is H.264 with AAC. Mute and trim of the start and end are optional. A bar shows progress, then a download button. Nothing is uploaded. The first run downloads the converter (about 31 MB); after that it still works with no signal. iPhone clips over 200 MB are turned away so Safari doesn't close the page. The service worker is v9, and opening the converter does not replace the saved home page. It uses the single-thread converter, so GitHub Pages does not need special headers.

## 2026-10-23

- **11:50 PM CT — SD organizer: small days share Other Days, and Tetons gets a folder** (`Beta`)
  A day with fewer than 24 photos and videos goes in Sony/Other Days, still split into Photos or Videos and Vertical or Horizontal. October 15 through October 22, 2026 goes in Sony/Tetons. A small day in that range goes in Sony/Tetons/Other Days. The trip name, the dates, and 24 can be changed on the organizer page, and Look at the card shows the folder each day will use. A file already copied into an older day folder is recognized and not copied again. Delete still needs a matching size and checksum, and it is still a separate button.
- **11:25 PM CT — v8: SD Organizer pill at the top, and the Applications start path** (`Beta`)
  The first pill is now labeled SD Organizer. Tapping it checks http://127.0.0.1:8765/api/health. If the helper answers, the organizer opens in a new tab. If it does not, Daxton's Life stays open and shows how to start it: double-click ~/Applications/sd-card-organizer/Organize SD Card.command. The service worker is v8 so the phone picks up this page instead of a saved copy.
- **9:00 PM CT — v7: organizer stays in the app when it isn't running, and sorts Vertical / Horizontal** (`Beta`)
  Tapping Organize SD card on the iPhone, or on the Mac when the helper isn't running, stays in Daxton's Life and explains how to start it (double-click Organize SD Card.command). It no longer opens http://127.0.0.1:8765, which was the browser error page. Photos and videos now go in Sony/YYYY-MM-DD/Photos/Vertical or Horizontal, and the same for Videos. Taller than wide, after the camera rotation, is Vertical. A square is Horizontal. Each copy is still checked by size and checksum, and delete is still a separate button.

## 2026-10-20

- **4:45 PM CT — v6: add and edit pills, and open the latest version on its own** (Cursor, `Beta`)
  Add a list pill or a link pill from +. Relationships, a list you added, a person inside a list, and Organize SD card can be renamed from the page. A link pill’s name and address can both be changed. Delete hides Relationships or Organize SD card, or removes a pill you added; people already saved stay on this phone. Beta still keeps notes on the phone (it has no sync code). When the phone is online, the app loads the newest copy and refreshes itself; with no signal it still opens the saved copy.
- **4:55 PM CT — v5: Organize SD card** (`Beta`)
  New Organize SD card button next to Relationships. On the MacBook, with the helper running, it opens the local organizer. On the iPhone, or when the helper is not running, it explains that the copy happens on the MacBook and how to start it (double-click Organize SD Card.command in sd-card-organizer). The helper copies photos and videos straight from the SD card onto the hard drive, one folder per day, checks each file, and only deletes from the card when you ask.

## 2026-10-10

- **2:45 PM CT — v4: no word limit on notes** (Claude)
  Removed the 15-word limit on Relationship notes. Notes can be any length; the counter now just shows how many words you've typed.

## 2026-10-08

- **8:01 PM CT — v3: Relationships** (Claude)
  Added a "Relationships" pill near the top. Tap it to add people; tap a person to add unlimited notes (stories, desires, things to remember), each up to 15 words. Notes save on this device and stay after closing the app.

- **2:47 PM CT — v2: motto line** (Claude)
  Added "If it's not a hell yes, it's a no." under the headline on the landing page.

- **1:40 PM CT — v1: first version** (Claude)
  Created the repo with three branches: `main`, `testing` (copy of main for experiments), and `Beta` (next iteration).
  Landing page shows Daxton's photo full screen with "Hello Daxton, let's take over the world."
  Installable on iPhone from Safari (Add to Home Screen), with the photo as the app icon, and works offline.
