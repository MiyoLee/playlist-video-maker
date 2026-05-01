# Playlist Video Maker

Desktop app for generating a single MP4 from local audio files, a user-provided background image, and per-track captions.

## Stack

- PySide6
- ffmpeg (external binary)

## Run

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
playlist-video-maker
```

### Windows (PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
playlist-video-maker
```

## ffmpeg / ffprobe

- `ffmpeg` and `ffprobe` must be available before rendering starts.
- The app checks your `PATH` first.
- On Windows, you can also set `FFMPEG_PATH` and `FFPROBE_PATH` to the full executable paths if they are not on `PATH`.

## Windows ZIP distribution

For a sendable Windows ZIP build flow, see `docs/windows-zip-build.md`.

If you do not have a Windows PC, you can build the Windows ZIP through GitHub Actions after pushing this repo to GitHub.

## Current status

- Architecture documented
- Local-audio form scaffolded
- Local ffmpeg render pipeline implemented
