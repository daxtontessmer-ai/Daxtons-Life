# Changelog

Every commit gets a summary and timestamp here (Central Time). Newest first.

## 2026-10-09

- **11:20 AM CT — v6: edit notes + faster loading** (Claude, `testing` branch)
  Every note under a person (or any pill item) now has **Edit** and **×**: tap the note or Edit to change it (same 15-word limit), × to delete it. Each person/item also has **Rename**. Faster opening: the app now opens instantly from the copy saved on the phone and checks for updates in the background; if there's a new version, a "Tap to refresh" button appears. Photo shrunk from 345 KB to 186 KB, intro animation shortened from ~2.5s to under 1s, and the big unused icons are no longer downloaded on first open. Not on `main` yet.

- **2:05 AM CT — v5: notes sync everywhere** (Claude)
  Notes in all four pills now save to the private repo `daxtons-life-data`, so your phone, your Mac, and anyone you give the sync code to all see the same notes. Tap the Sync button (top right) and paste the sync code once per device. Works offline and catches up when back online. Deleting on one device removes it everywhere. Notes already on a phone carry over. Fixed the offline helper so it never serves old copies of your notes.

- **1:52 AM CT — v4: Just dos, Work, School** (Claude, `testing` branch)
  Added three new pills next to Relationships, each working the same way: add items, tap one to add notes (15 words max). Only one pill opens at a time. Existing Relationships notes are kept. Not on `main` yet.

## 2026-10-08

- **8:01 PM CT — v3: Relationships** (Claude)
  Added a "Relationships" pill near the top. Tap it to add people; tap a person to add unlimited notes (stories, desires, things to remember), each up to 15 words. Notes save on this device and stay after closing the app.

- **2:47 PM CT — v2: motto line** (Claude)
  Added "If it's not a hell yes, it's a no." under the headline on the landing page.

- **1:40 PM CT — v1: first version** (Claude)
  Created the repo with three branches: `main`, `testing` (copy of main for experiments), and `Beta` (next iteration).
  Landing page shows Daxton's photo full screen with "Hello Daxton, let's take over the world."
  Installable on iPhone from Safari (Add to Home Screen), with the photo as the app icon, and works offline.
