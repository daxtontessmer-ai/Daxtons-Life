# Daxton's Life

A personal web app for iPhone. Open it in Safari, tap Share → **Add to Home Screen**, and it launches full screen like a real app (works offline too).

## Branches

| Branch | What it's for |
|---|---|
| `main` | The real, working version. Only things that are proven to work go here. |
| `testing` | An exact copy of `main` to experiment on. If an experiment works, merge it into `main`. |
| `Beta` | The next big iteration, built separately from the current version. |

## Files

- `index.html` — the app
- `video.html` — convert a video in the browser (opened from Links)
- `editor.html` — cut a reel in the browser (opened from Links)
- `image.html` — convert pictures (HEIC, PNG, and more) in the browser (opened from Links). `image-encoders.js` writes its BMP, ICO, TIFF, and PDF files; `test/image-encoders.test.js` checks them (`node test/image-encoders.test.js`)
- `instagram-downloader/` — saves a public Reel or post on the Mac (opened from Links). See its README.
- `img/daxton.jpg` — the landing-page photo
- `img/icon-*.png` — home-screen icons
- `manifest.webmanifest`, `sw.js` — make it installable and work with no signal
- `CHANGELOG.md` — a dated summary of every change
