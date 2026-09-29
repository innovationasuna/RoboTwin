"""Run one reproducible simulation smoke case; this is not a benchmark suite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import time


CASES = {
    "cup": ("把杯子放到盘子里", ["cup", "plate"]),
    "stack": ("方块按红绿蓝堆叠", ["red_block", "green_block", "blue_block"]),
    "row": ("方块按红绿蓝排序", ["red_block", "green_block", "blue_block"]),
    "drawer": ("把牌放到柜子里", ["playing_cards", "cabinet"]),
}


def command_output(*args: str) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=CASES, default="cup")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument("--perception", choices=("oracle", "vlm"), default="oracle")
    parser.add_argument("--stage-feedback", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    # Isolate memory and scene caches between runs; never silently reuse a result.
    output.mkdir(parents=True, exist_ok=False)
    from gapa.clients.llm import LLMClient
    from gapa.clients.vlm import VLMClient
    from gapa.runtime.runner import GapaRunner

    instruction, objects = CASES[args.case]
    manifest = {
        "purpose": "single-case simulation smoke; not a success-rate estimate",
        "case": args.case,
        "seed": args.seed,
        "instruction": instruction,
        "objects": objects,
        "perception_mode": args.perception,
        "stage_feedback": args.stage_feedback,
        "memory": "fresh isolated directory; no cross-case warmup",
        "git_commit": command_output("git", "rev-parse", "HEAD"),
        "git_changes": command_output("git", "status", "--short"),
        "llm_model": LLMClient().config.model,
        "vlm_model": VLMClient().config.model,
        "gpu": command_output("nvidia-smi", "--query-gpu=index,name", "--format=csv,noheader"),
        "max_agent_rounds": 3,
        "status": "running",
    }
    manifest_path = output / "manifest.json"
    def save() -> None:
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    save()
    print(json.dumps(manifest, ensure_ascii=False), flush=True)
    runner = GapaRunner(runs_root=output / "runs", memory_root=output / "memory")
    started = time.monotonic()
    try:
        runner.randomize_scene(seed=args.seed, object_names=objects)
        kwargs = {"stage_feedback": True} if args.stage_feedback else {}
        summary = runner.run_task(instruction, perception_mode=args.perception, **kwargs)
        manifest.update(status=summary["status"], run_id=summary.get("run_id"),
                        attempt_count=summary.get("attempt_count"),
                        success_check=summary.get("success_check"),
                        selection_reason=summary.get("selection_reason"))
    except Exception as exc:
        manifest.update(status="error", error_type=type(exc).__name__, error=str(exc))
    finally:
        runner._close_current_env()
        manifest["elapsed_seconds"] = round(time.monotonic() - started, 2)
        save()
    print(json.dumps(manifest, ensure_ascii=False, indent=2), flush=True)
    return 0 if manifest["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
