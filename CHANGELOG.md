# Changelog

Every commit gets a summary and timestamp here (Central Time). Newest first.

## 2026-10-25

- **10:20 PM CT — v54: Video Converter** (`main`)
  New Video Converter pill in Links. Pick a video, including an iPhone .mov, and convert it on the device into MP4, MOV, WebM, MKV, AVI, GIF, MP3, or ZIP. MP4 is marked "Best for Blackboard / uploads" and is H.264 with AAC. Mute and trim of the start and end are optional. A bar shows progress, then a download button. Nothing is uploaded. The first run downloads the converter (about 31 MB); after that it still works with no signal. iPhone clips over 200 MB are turned away so Safari doesn't close the page. The service worker is v54 so an installed copy picks this up. It uses the single-thread converter, so GitHub Pages does not need special headers, and the app's existing offline worker stays in charge.

## 2026-10-24

- **4:25 PM CT — v52: adding something keeps you at the top of the pill** (Claude, `main`)
  In every pill (Venture, Work, School, Just dos, Relationships, and the rest), adding an entry no longer jumps you to the bottom to open its notes. You stay on the add box with the keyboard up, so you can see what you type and add the next one. Tap an entry to add notes to it. Opening the keyboard also no longer shifts the dropdown.

- **4:15 PM CT — v51: scrolling works with a pill open, Up/Down buttons gone** (Claude, `main`)
  Opening a pill no longer locks the screen: you can scroll the dropdown and back up to the pills again. Removed the ↑ Up and ↓ Down buttons from inside the Relationships pill (hold-and-drag still reorders people).

- **11:25 AM CT — v50: dropdowns open below every pill** (Claude, `main`)
  Tapping any pill (main pills, the + pill, and the Links pills) now opens its dropdown at the bottom, below all the pills including the Links section. The dropdown scrolls with the whole page, so you can scroll back up to see every pill without closing it, then tap another pill to switch or tap the same pill to close.

- **6:07 AM CT — v49: tap outside a dropdown to close it** (Claude, `main`)
  With a dropdown open, tap anywhere outside the box (like the space at the top of the screen) and it closes and slides all the pills back down. Taps inside the box work as before.

- **5:57 AM CT — v48: dropdowns fill most of the screen** (Claude, `main`)
  Tapping a pill on the main page now slides the pill list up so the dropdown starts near the top of the screen and takes up most of the page, instead of being squeezed into the bottom half. Scroll up to get back to the other pills, or tap the pill again to close it and everything slides back.

## 2026-10-14

- **5:35 PM CT — v45: Prayers, your own pills (+), and pills inside pills** (Claude, `main`)
  Prayers pill on main: tap a prayer to count it (🙏 count and when you last prayed it), hold to rename, undo a tap, or delete. New + pill at the end of the list makes a pill of your own, as a Simple list (like Lessons) or a List with notes (like Work); rename or delete it from the bottom of its dropdown. Hold any pill for a moment and drag it onto another pill to put it inside as a sub-category; drag it to the bar at the bottom to bring it back to the main list. Sync now keeps every section, so pills and their layout match on all devices.

## 2026-10-12

- **4:45 PM CT — testing moved to `main`** (Claude)
  Main now matches testing: Links section, Lessons, Compare versions, Just dos DONE section, and the full Alarms pill (sound, Snooze 10 min, Turn off alarm, Set iPhone alarm through Shortcuts). Your notes and alarms were already shared through `daxtons-life-data`.

- **4:25 PM CT — alarm sound, Snooze 10 min, Turn off alarm, iPhone alarm setup** (Claude, `testing` branch)
  When an alarm goes off in the app it now plays a loud repeating alarm sound that also works with the iPhone silent switch on (after you tap the app once), shows the alarm's name big on screen, and has "Snooze 10 min" and "Turn off alarm". If the phone blocks the sound, a "Tap for sound" button appears. The Alarms dropdown has a new setup card with "Make the shortcut" and "Test it (alarm in 2 min)" links plus the Settings path, so "Set iPhone alarm" can create real Clock alarms that ring with the app closed. Not on `main` yet.

- **4:15 PM CT — Set iPhone alarm opens Shortcuts reliably** (Claude, `testing` branch)
  "Set iPhone alarm" is now a real link (opened from the top of the app, even inside Compare versions) instead of a script redirect, which iPhones were silently blocking. Added a quick way to test the shortcut on its own. Not on `main` yet.

- **4:10 PM CT — alarms that actually go off + dropdown scrolling fix** (Claude, `testing` branch)
  Alarms now ring with a full-screen alert, a repeating beep and Stop / Snooze 5 min, instead of a hidden pop-up. Each device rings on its own, so a preview open inside Compare versions can no longer silently use up an alarm. If the phone was asleep, the alarm shows as Missed when you open the app. New "Set iPhone alarm" button creates a real Clock alarm through Apple Shortcuts (one-time setup explained in the Alarms dropdown), so it rings even when the phone is locked. Dropdowns now size themselves to the space left on screen, so the bottom buttons can be reached and tapped. Not on `main` yet.

- **4:32 PM CT — v31: DONE section for Just dos** (Codex, `testing`)
  Just dos now separates unfinished items from a clearly labeled DONE section. Each item has a one-tap Done control, completed items move below immediately, and Undo returns them to the active list while preserving notes and sync data. Not on `main`.

- **4:05 PM CT — v30: scheduled alarms prototype** (Codex, `testing`)
  Added an Alarms pill with a one-week default, saved alarm names and times, web notification permission, due-alarm checking, deletion, and one-tap calendar files that can create a durable phone reminder even after the website is closed. Not on `main`.

- **3:30 PM CT — v28: Compare versions** (Claude, `main`)
  New "Compare versions" pill. It opens a page inside the app showing Main, Testing and Beta, each with its four newest changes and a live, usable preview. On a phone you switch between them with tabs; on a wide screen all three sit side by side. "Open" goes to that version full screen, and "‹ Back" returns to your app.

- **12:08 PM CT — v26: Lessons pill** (Claude, `main`)
  New "Lessons" pill next to Crazy IdEaS, working the same way: each lesson is its own pill, no word limit, hold one to edit or delete it. Lessons sync across your devices like everything else.

## 2026-10-11

- **1:08 AM CT — v25: Links section** (Claude, `testing` branch)
  The home screen now has two parts. Your own pills (Relationships, Just dos, Work, School, Live by, Crazy IdEaS, App Roadmap) sit on top. Below a thin line, a "Links" section holds Daxton's Portfolio and Shot List. Not on `main` yet.

- **12:45 AM CT — v14 moved to `main`** (Claude)
  Everything from `testing` (v6 to v14) is now on `main`: hold to edit or delete, Live by, Daxton's Portfolio, App Roadmap, Shot List links, dated Relationship notes, and no word limit. Your notes were already shared between versions through `daxtons-life-data`, so nothing needed moving.

## 2026-10-11

- **12:25 AM CT — v24: Crazy IdEaS pill** (Codex, `testing` branch)
  Added a new Crazy IdEaS pill formatted and behaved like Live by: ideas appear as individual flat pills, can be added without a word limit, and can be held to edit or delete. Crazy IdEaS uses its own synced data section, preserving the existing pills and privacy behavior. Not on `main` yet.

- **12:17 AM CT — v23: visible answer save times** (Codex, `testing` branch)
  Roadmap answers now show when they were last saved, including a Saved now confirmation followed by a compact date and time that remains visible after reopening the stage. The answer-specific timestamp travels with the existing synced roadmap data, making cross-device edits easier to trust. Not on `main` yet.

- **12:12 AM CT — v22: editable roadmap questions** (Codex, `testing` branch)
  Edit stage now opens both the stage title and its guiding question. Users can tailor the roadmap prompts to a specific app, save those changes through the existing sync system, or cancel without changing anything. Both editing fields have accessible labels and phone-sized text controls. Not on `main` yet.

- **12:07 AM CT — v21: visible roadmap editing** (Codex, `testing` branch)
  Added a clearly labeled Edit stage action inside every expanded roadmap stage, so changing a stage title or reaching its delete option no longer depends on discovering the hold gesture. The existing hold gesture still works, answers are saved before editing opens, and the edit field now has an accessible label. Not on `main` yet.

- **12:02 AM CT — v20: focus on unfinished roadmap stages** (Codex, `testing` branch)
  Added a Hide finished stages control that appears after progress begins. It filters completed stages out of the long mobile timeline while preserving accurate chapter totals, and Show all stages restores the full roadmap for review. Verified the filter and live chapter counts without changing saved data. Not on `main` yet.

## 2026-10-10

- **11:57 PM CT — v19: clear next-stage guidance** (Codex, `testing` branch)
  The App Roadmap progress card now names the next unfinished phase and its full action, so the Continue button always has clear context. When every stage is finished, the card switches to a completion and review message. Verified that completing and reopening stages updates this guidance immediately. Not on `main` yet.

- **11:52 PM CT — v18: roadmap chapters** (Codex, `testing` branch)
  Grouped the 18-stage App Roadmap into four scannable chapters—Discover, Plan, Build, and Grow—with a completed/total count for each. Custom stages are kept in their own chapter. This makes the full journey easier to understand and navigate on a phone without changing saved answers or progress. Not on `main` yet.

- **11:47 PM CT — v17: safer roadmap autosave** (Codex, `testing` branch)
  App Roadmap answers now save automatically after a short pause while typing, rather than waiting for the field to lose focus. The stage shows Saving… and Saved feedback, reducing the chance of losing a decision when the app is closed or another stage is opened. Added accessible labels to every roadmap answer field. Not on `main` yet.

- **11:42 PM CT — v16: guided roadmap progress** (Codex, `testing` branch)
  Added a progress card to App Roadmap showing completion percentage, answered-question count, and finished-stage count. A Continue button opens the next unfinished stage and keeps the active question in view, making the 18-stage timeline easier to work through on a phone. Not on `main` yet.

- **11:34 PM CT — v15: interactive app-building timeline** (Codex, `testing` branch)
  Expanded App Roadmap from 12 check-off pills into an 18-stage timeline from problem definition through sustainable monetization. Each stage now opens to a focused question, saves a written decision or evidence, and has a separate completion control. Answers, edits, and progress use the existing local and cross-device sync data. Not on `main` yet.

- **11:40 PM CT — v14: dated Relationship notes, no word limit** (Claude, `testing` branch)
  Notes about a person in Relationships now have a date. The date picker under the note box starts on today, and you can change it. The date shows on the right of each note. Hold a note to change its date, or add one to older notes. Also removed the 15-word limit everywhere: any section, any entry, as long as you want. Not on `main` yet.

- **11:29 PM CT — GitHub Pages branch previews** (Codex)
  Added an automatically refreshed GitHub Pages landing page with clickable live UI previews for `main`, `Beta`, and `testing`. The page rebuilds from the latest branch versions every five minutes.

- **11:20 PM CT — v13: Trip Finder link** (Claude, `testing` branch)
  The Shot List pill now has a third link: Trip Finder, a new page on the shot-list site. It asks one question at a time across 12 sections, opens follow-up questions based on your answers, and lands on one of 7 trip types with what you'll get out of it and what to expect. Not on `main` yet.

- **10:55 PM CT — v12: Shot List pill** (Claude, `testing` branch)
  New "Shot List" pill. Its dropdown has two links: your Shot List app, and the new Trip Planner page (added to the shot-list site at /trip.html) with 40 questions in 13 sections to plan a trip with friends. Not on `main` yet.

- **10:40 PM CT — v11: App Roadmap** (Claude, `testing` branch)
  New "App Roadmap" pill. Its dropdown is 12 step pills joined by one line, from naming who the app is for to sharing it publicly. Tap a step to check it off (the pill shows how many are done, like 2/12). Hold a step to change or delete it, and add your own steps at the top. Progress syncs like your notes. Not on `main` yet.

## 2026-10-09

- **2:25 PM CT — v10: Portfolio pill fixed** (Claude, `testing` branch)
  "Daxton's Portfolio" now looks exactly like the other pills. Tapping it goes straight to Daxton's Way (daxtontessmer-ai.github.io/DaxtonTessmer/DaxtonWay4721_linktree.html). Removed the slide-over page from v8. Not on `main` yet.

- **2:20 PM CT — v9: Live by** (Claude, `testing` branch)
  Added a "Live by" pill next to School. Tap it to add things to live by, each up to 15 words. Each one is its own pill with nothing underneath it (no second layer). Hold one to edit or delete it. Syncs like the others. Not on `main` yet.

- **2:15 PM CT — v8: Daxton's Portfolio** (Claude, `testing` branch)
  Added a light "Daxton's Portfolio" pill under the others (no dropdown). Tapping it slides your portfolio page (daxtontessmer-ai.github.io/DaxtonTessmer) in over the app. "‹ Back" (or swiping right on the top bar) slides back. "Open" shows it in Safari. Not on `main` yet.

- **2:05 PM CT — v7: hold to edit or delete** (Claude, `testing` branch)
  Removed the Remove, Rename, Edit and × buttons. Hold a person, item or note for about half a second to change or delete it. Tapping still opens and closes as before. Deleting a person or item takes two taps so nothing goes by accident. Not on `main` yet.

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
