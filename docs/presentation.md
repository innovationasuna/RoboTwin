# Presentation assets

- `assets/files/gapa-overview.svg`: editable architecture figure; `gapa-overview.png` is the README raster export (1600 × 1080). Export using `rsvg-convert assets/files/gapa-overview.svg -o assets/files/gapa-overview.png`.
- Architecture follows `docs/architecture.md`. The code block is an abbreviated illustration, not a standalone executable program.
- Camera panels use `assets/demos/drop-head.png` and `drop-wrist.png` from the archived 2026-09-27 controlled-release probe. The recovery evidence strip describes the separate `docs/results/2026-09-28-agent-drop.json` trial. No new experiment was run for this figure.
- `assets/files/gapa-web-ui.png`: browser capture at 1280 × 1660 of the HTML defined in `gapa/web/app.py`. A local read-only preview supplied the real `object_options()` list, the two archived diagnostic frames and an MP4 conversion of `drop-recovery.gif`. World and left-wrist views were unavailable and are marked accordingly. The header explicitly marks this as an archived preview without a simulation backend; action buttons are disabled. Progress bars are not trial measurements.
- UI capture intentionally does not claim that the archived camera frames and the recovery video are synchronized observations from one run. The Ubuntu workstation was unreachable during this presentation update.
