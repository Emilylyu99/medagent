# Two-minute MedAgent demo

## Deliverable

The local release artifact is `artifacts/medagent-demo/medagent-demo.mp4`, with an English
subtitle track and a separate `medagent-demo.srt`. The narration is synthesized locally
using macOS Samantha; it does not impersonate the project author.

Verified output: 120.000 seconds, 1600 × 1000, H.264 video, AAC audio, English mov_text
subtitle track; approximately 6.34 MB. Representative frames were inspected, and the audio
track was checked to be non-silent and below clipping.

The video records real browser actions against the running FastAPI / Streamlit application.
It uses only synthetic examples and an extractive reasoner. It is not a mockup or a recording
of real patient care. Fixed reading pauses are presentation pacing, not model latency.

Large video and intermediate media files are excluded from Git. For a public portfolio,
upload the reviewed MP4 to a GitHub release or video host and add that URL to this page.
No upload or public sharing has been performed by the recording scripts.

## Chapters

| Time | Screen | Message |
| --- | --- | --- |
| 0:00–0:15 | Ask | Scope, synthetic cases, offline mode |
| 0:15–0:36 | Review + Sources | Citation-bound review points and attributed evidence |
| 0:36–0:53 | Agent Outputs | Structured component outputs and measured timings |
| 0:53–1:20 | Playground → Conflict Analysis | Two deliberate errors and the resulting review flags |
| 1:20–1:42 | Evaluate | Six-case smoke results, honest metric definitions, export |
| 1:42–1:53 | Cases | Session history and exportable snapshots |
| 1:53–2:00 | About | Limitations and the next model-quality experiment |

## Re-record on macOS

Prerequisites: the API and UI running in extractive mode, Google Chrome, Node.js 20 or newer,
the macOS `say` utility with Samantha, and `ffmpeg` / `ffprobe` on PATH.

```bash
npm --prefix scripts install
node scripts/record_demo.cjs --quick
node scripts/record_demo.cjs
node scripts/render_demo.cjs
```

The quick pass exercises the same workflow and saves screenshots but does not create video.
Recording uses a fresh isolated browser context, not your personal Chrome profile. It refuses
to run if the API health endpoint reports a model-backed reasoner.

Optional environment variables:

- `DEMO_URL`: UI address (default `http://localhost:8501`).
- `DEMO_API_URL`: API address (default `http://localhost:8000`).
- `DEMO_OUTPUT`: artifact directory (default `artifacts/medagent-demo`). Choose a new folder
  to keep a prior recording; the renderer replaces media files within the selected folder.

`recording.json` retains the chapter narration, source mode, resolution, and recording time.
Only the recording's initial page-loading period is trimmed; the remaining UI interaction
timeline is retained. Narration and subtitles are added separately during MP4 packaging.
