# Architecture

## Goal

Accept local audio files, a background image, and an output target. Concatenate the audio into one timeline, overlay `artist - title` captions for each track segment, and render a final MP4.

## MVP boundaries

- Desktop-only app
- Local execution only
- Single job at a time
- External binaries required: `ffmpeg`, `ffprobe`
- User-provided local audio files only

## Module layout

```text
src/playlist_video_maker/
  app.py                # QApplication bootstrap
  main.py               # CLI entrypoint
  models.py             # Dataclasses for job config and track metadata
  ui/
    main_window.py      # Main form and log/progress UI
  services/
    binaries.py         # ffmpeg/ffprobe presence checks
    workflow.py         # End-to-end job orchestration
```

## Processing pipeline

1. **Input validation**
   - Validate at least one audio file exists
   - Validate background image path exists
   - Validate output directory
   - Verify `ffmpeg` and `ffprobe` are available in PATH
   - Validate subtitle size/alignment inputs

2. **Track metadata collection**
   - Read user-selected local tracks
   - Store artist/title metadata from form input

3. **Workspace creation**
   - Create a temporary job directory:

   ```text
   workspace/
     normalized/
     subtitles/
     output/
   ```

4. **Normalization**
   - Convert each selected source file into a normalized WAV file
   - Keep deterministic filenames using track index prefixes

5. **Concatenation**
   - Build a concat file for normalized outputs
   - Produce a single AAC output for final render

6. **Timeline derivation**
   - Probe normalized files with `ffprobe`
   - Build cumulative start/end timestamps for every track
   - Caption text format: `artist - title`
   - Apply user-adjusted subtitle size and position settings

7. **Subtitle generation**
   - Generate ASS subtitle file for better style/position control
   - One caption event per track range

8. **Final render**
   - Loop the background image for the total audio duration
   - Combine looped image video + concatenated audio + burned-in ASS subtitles
   - Output final MP4 in user-selected output directory

## Concurrency model

- UI thread: form, logs, progress updates, cancel button state
- Worker thread: job orchestration
- External heavy work is delegated to `ffmpeg` and `ffprobe` subprocesses
- The worker emits status/progress events back to the UI

## Failure boundaries

- Binary missing -> fail before starting processing
- Invalid local file path -> stop before normalization
- Single track normalization fails -> fail job with track index context
- Subtitle generation fails -> stop before final render
- Final render fails -> preserve workspace for debugging

## MVP implementation order

1. App scaffold + form
2. Binary checks + validation
3. Local track metadata entry
4. Audio normalization + concat
5. Subtitle/timeline generation
6. Final MP4 render
7. Progress/error polish
