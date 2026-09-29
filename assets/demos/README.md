# Simulation demonstrations

These GIFs preserve chronological motion from a controlled Agent recovery trial
and an older stacking run. Neither is a benchmark sample.
The source videos and execution records remain on the development workstation.

| Preview | Source run | Scene | Recorded result | Playback |
| --- | --- | --- | --- | --- |
| `drop-recovery.gif` | `showcase20260928/agent-drop`, 2026-09-28 | Cup on plate, seed 2, Oracle localization + real VLM stage reports | Injected release caused an 8.14 cm drop. Simulator-height stage check stopped placement; FeedbackAgent diagnosed and CodegenAgent generated the second program. Same environment, final native success. | Source motion 1×, 12 fps preview; 3-second end holds added to each attempt |
| `stack.gif` | `20260615_132335_cb23711a` | Red/green/blue bottom-to-top, seed 1, VLM perception | One attempt; both adjacent pairs satisfy the 0.025 / 0.025 / 0.012 m stacking tolerances; both grippers open. | 3×, 8 fps |

The controlled trial's portable evidence and both actual generated programs are in
[`2026-09-28-agent-drop.json`](../../docs/results/2026-09-28-agent-drop.json).
The source motion videos retain every recorded frame; the preview downsample is
12 fps. English headers/captions and end holds explain the injected fault,
diagnosis, and success. Model-call waiting time is omitted; playback is not a
wall-clock latency claim. Localization is Oracle; the VLM is `qwen-vl-max`.

The old `cup-recovery.gif` is retained only as a historical artifact and is no
longer linked as a recovery example: `relay_place_failed` in its log does not
establish a visibly failed manipulation. The stack source remains
`20260615_132335_cb23711a`; its model version was not preserved. All footage is
SAPIEN simulation, not hardware.

`drop-head.png` and `drop-wrist.png` are unedited frames from the controlled
gripper-release probe on 2026-09-27 (seed 2, cup/plate, after_lift). The cup had
physically fallen 0.08118 m. The head-view VLM reported failure while the active
wrist-view VLM incorrectly reported success, both at 0.95 stated confidence.
This diagnostic case motivated the hybrid stage check; it is an injected fault,
not a naturally sampled test episode.

`stack-card.gif` presents `stack.gif` on a square white canvas for equal-sized README demo panels; frames and playback timing are retained.
