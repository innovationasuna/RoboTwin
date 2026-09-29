# Presentation assets

- `assets/files/gapa-overview.svg`: editable architecture figure; `gapa-overview.png` is the README raster export (1600 × 1080). Export using `rsvg-convert assets/files/gapa-overview.svg -o assets/files/gapa-overview.png`.
- Architecture follows `docs/architecture.md`. The code block is an abbreviated illustration, not a standalone executable program.
- Camera panels use `assets/demos/drop-head.png` and `drop-wrist.png` from the archived 2026-09-27 controlled-release probe. The recovery evidence strip describes the separate `docs/results/2026-09-28-agent-drop.json` trial. No new experiment was run for this figure.
- `assets/files/gapa-web-ui.png`: browser capture at 1280 × 1660 of the HTML defined in `gapa/web/app.py`. A local read-only preview supplied the real `object_options()` list, the two archived diagnostic frames and an MP4 conversion of `drop-recovery.gif`. World and left-wrist views were unavailable and are marked accordingly. The screenshot omits the preview-status banner for a cleaner README; it still uses archived media and has no simulation backend. Action buttons are disabled. Progress bars are not trial measurements.
- UI capture intentionally does not claim that the archived camera frames and the recovery video are synchronized observations from one run. The Ubuntu workstation was unreachable during this presentation update.

## Illustrated overview revision

The README now uses `assets/files/gapa-pipeline-refined.png`, edited from the original `gapa-pipeline-overview.jpg` with the built-in image generation tool. It preserves the illustrated tabletop scene and task callouts, reduces prose, and distinguishes three agent roles, skill execution, stage feedback and strategy memory. The robot scenes are conceptual illustrations, not execution evidence. The prior SVG and raster architecture remain available as detailed diagrams.

## Embodiment and object consistency revision

The current README image is `assets/files/gapa-pipeline-aloha.png`, edited in the ChatGPT web UI via ego-browser using the previous figure and a frame extracted from `assets/demos/stack.gif`. The active project configuration is `aloha-agilex` (`task_config/gapa_scene.yml`), not the separate `piper` or `franka-panda` configurations. Robot illustrations follow the recorded black-and-white angular AGILEX appearance. Localization, VLM, manipulation and failure illustrations use one red mug and white plate.

Editing conversation: https://chatgpt.com/c/6abb4e99-c7fc-83e8-95d5-2015acd99ea3

## Annotated detail pass

The current README uses `gapa-pipeline-detail-v2.png`. This web-edited revision removes the large acronym heading and check tile, simplifies the five-skill layout, clarifies memory/program icons, uses a mug-shaped point cloud, and refines parallel gripper geometry and the exterior mug grasp.

Editing conversation: https://chatgpt.com/c/6abb53e9-8374-83e8-87dc-5e32b5946eea

## Block manipulation overview

The README now uses `gapa-pipeline-block.png`: larger headline and a red block on a white plate consistently across the instruction, parser, manipulation, localization, point cloud, memory and failure illustrations. Recorded GIFs remain unchanged.

Editing conversation: https://chatgpt.com/c/6abb563b-9848-83e8-88a2-4cb411016c0b

## Parallel gripper correction

Current README asset: `gapa-pipeline-gripper.png`. All five rendered grippers now use a compact rectangular body and two straight parallel fingers. The figure remains a conceptual illustration.

Editing conversation: https://chatgpt.com/c/6abb5a44-c128-83e8-906a-3500224a31df
