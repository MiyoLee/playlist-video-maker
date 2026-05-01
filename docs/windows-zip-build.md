# Windows ZIP Build

This project now supports a **ZIP-first Windows release flow**.

## Goal

Create a **folder-based Windows app build**, then zip that folder and send it to a Windows user.

This first Windows distribution phase keeps:

- the existing macOS launcher unchanged
- bundled subtitle fonts included in the Windows artifact
- `ffmpeg` / `ffprobe` external

## Why ZIP first

The app already has Windows-oriented runtime preparation, but it does not yet have an installer pipeline.

A zipped folder build is safer because:

- resource paths stay closer to the current filesystem-based runtime assumptions
- it is easier to debug than an installer
- it avoids mixing installer bugs with app bugs

## Build host

Build the Windows ZIP **on a Windows machine**.

## Build script

Use the repo-root PowerShell script:

```powershell
.\build_windows_zip.ps1
```

The script:

1. installs `pyinstaller` into the current Python environment
2. builds a **windowed onedir** app
3. includes `resources/fonts`
4. writes a short `README-Windows.txt` into the release folder
5. zips the final app folder into `build/windows/release/`

## GitHub Actions build

If you do not have a Windows PC, use the GitHub Actions workflow:

1. push this repo to GitHub
2. open the repository's **Actions** tab
3. choose **Build Windows ZIP**
4. click **Run workflow**
5. download the uploaded artifact `playlist-video-maker-windows-zip`

The workflow runs on `windows-latest`, installs `ffmpeg` on the runner, executes `build_windows_zip.ps1`, and uploads the generated ZIP artifact.

## Output

Expected artifact shape:

```text
build/
  windows/
    release/
      playlist-video-maker/
      playlist-video-maker-windows-0.1.0.zip
```

In GitHub Actions, the downloadable artifact contains that generated ZIP file.

## Runtime assumptions

- subtitle fonts must remain available under `resources/fonts`
- `ffmpeg` and `ffprobe` remain external in this phase
- Windows users can satisfy that requirement by:
  - adding `ffmpeg/bin` to `PATH`, or
  - setting `FFMPEG_PATH` and `FFPROBE_PATH`

## Verification checklist

Before sending the ZIP to another Windows user, verify:

1. the app launches from the unzipped folder
2. subtitle previews still render with bundled fonts
3. final render also uses bundled fonts correctly
4. missing `ffmpeg` / `ffprobe` shows the guided error message
5. render starts successfully when binaries are available through `PATH` or env vars
