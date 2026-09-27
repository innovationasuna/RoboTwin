# Simulation demonstrations

These GIFs are full chronological previews of existing GAPA development runs,
not evidence of the September stage-feedback changes or a benchmark sample.
The source videos and execution records remain on the development workstation.

| Preview | Source run | Scene | Recorded result | Playback |
| --- | --- | --- | --- | --- |
| `cup-recovery.gif` | `20260615_131247_d2730f8c` | Cup on plate, seed 2, VLM perception | First attempt: `relay_place_failed`; second attempt succeeds in the same environment. Final pose error XYZ: 0.0162 / 0.0057 / 0.0072 m, within 0.05 / 0.05 / 0.03 m limits; both grippers open. | 2×, 8 fps |
| `stack.gif` | `20260615_132335_cb23711a` | Red/green/blue bottom-to-top, seed 1, VLM perception | One attempt; both adjacent pairs satisfy the 0.025 / 0.025 / 0.012 m stacking tolerances; both grippers open. | 3×, 8 fps |

Source: each run's `scene.json`, `summary.json`, `failure_reports.jsonl` (when present),
`programs/episode_sequence.json`, and `demo.mp4`. Playback is accelerated and
downsampled, with no attempt removed. LLM/VLM versions were not preserved in these
historical summaries. These are SAPIEN simulation demonstrations, not hardware runs.

`drop-head.png` and `drop-wrist.png` are unedited frames from the controlled
gripper-release probe on 2026-09-27 (seed 2, cup/plate, after_lift). The cup had
physically fallen 0.08118 m. The head-view VLM reported failure while the active
wrist-view VLM incorrectly reported success, both at 0.95 stated confidence.
This diagnostic case motivated the hybrid stage check; it is an injected fault,
not a naturally sampled test episode.
