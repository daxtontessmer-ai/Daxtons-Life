# Organize SD card

This copies photos and videos off the Sony a6400 SD card onto a hard drive, on the MacBook. The iPhone cannot see drives that are plugged into the Mac, so this runs on the Mac only.

Each day the pictures were taken gets its own folder, then Vertical or Horizontal:

```text
Hard Drive / Sony / 2024-03-15 / Photos / Vertical
Hard Drive / Sony / 2024-03-15 / Photos / Horizontal
Hard Drive / Sony / 2024-03-15 / Videos / Vertical
Hard Drive / Sony / 2024-03-15 / Videos / Horizontal
```

`Sony` is the folder name you type. You can change it. A picture that is taller than it is wide, after the camera's rotation, goes in `Vertical`. A landscape or a square goes in `Horizontal`. The small Sony `.XML` and `.THM` files that belong to a video sit in that video's folder, next to the video.

The date comes from the camera (the photo's EXIF date, or the video's XML / video date). If a file has no camera date, the file's own date is used. Photo orientation comes from the EXIF orientation tag plus the pixel size. Video orientation comes from the width, height, and rotation stored in the video. If `ffprobe` is installed, it is used when that built-in reader cannot see a size.

Files copy straight from the card to the hard drive. They are not saved on the Mac's internal disk first. After each copy, the file on the drive is read back and checked for the same size and the same checksum. If the check fails, that copy is removed and the original stays on the card.

Putting in another card later merges into the same day folders. A file that is already on the drive (same bytes) is skipped. A different file that happens to have the same name is saved under a new name. Nothing already on the drive is overwritten.

Deleting files from the SD card is a separate button. It shows a summary first. It only deletes a file when the copy on the drive still matches the card in size and checksum. It never deletes by itself.

## Start it

1. Plug the SD card and the hard drive into the MacBook.
2. In Finder, open **Applications**, then the folder **sd-card-organizer**.
3. Double-click **Organize SD Card.command**. That file is `~/Applications/sd-card-organizer/Organize SD Card.command`.
4. Safari opens a page called Organize SD card. Leave the Terminal window open until you are done. Closing it stops the organizer.

The first time, the Mac may say the file can't be opened because it came from the internet. Control-click **Organize SD Card.command**, choose **Open**, then click **Open** again.

If the Mac says Python 3 is needed, click Install on the command line tools window, wait for it to finish, and double-click the launcher again.

## Use it

1. Click the SD card under **SD card**.
2. Click the hard drive under **Hard drive**. The Mac's internal disk is shown but can't be picked.
3. Leave the folder name as `Sony`, or type another name.
4. Click **Look at the card** to see the days and how many photos and videos there are.
5. Click **Copy to the hard drive** and wait. Large 4K videos are copied in pieces, so the page stays responsive.
6. When it says Done, the files are on the drive and each one was checked.

To clear the card afterward:

1. Click **Show what would be deleted**.
2. Read the summary. Files that were not checked are listed and will stay.
3. Click **Delete these files from the SD card**, then **Yes, delete them from the card**.

Unplug the card from the Finder eject button when you are finished, the same as usual.

## If you opened it from Daxton's Life

The SD Organizer pill only opens this page when the helper is already running on that Mac. On the iPhone, or when the helper is not running, the app stays on Daxton's Life and shows these steps. It does not send you to an error page. The phone cannot copy to a drive that is plugged into the Mac.
