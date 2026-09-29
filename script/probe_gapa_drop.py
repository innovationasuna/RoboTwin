#!/usr/bin/env python3
"""Controlled fault injection, not a natural failure or an Agent recovery benchmark.

Run with the RoboTwin environment: python probe_drop.py --repo /path/to/RoboTwin
Optional --recover uses a fixed hand-written program in the SAME scene.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback

SOURCE = '''def play_once(api):
    source = api.pose("cup")
    arm = api.choose_arm(source)
    api.pick("cup", source, arm=arm, pre_grasp_dis=0.09, grasp_dis=0.0)
    target = api.target_pose(kind="object", target_name="plate", relation="on")
    api.place("cup", target, arm=arm, relation="on", target_name="plate", pre_dis=0.08, dis=0.02)
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("runs_gapa/probe_drop_seed2"))
    parser.add_argument("--recover", action="store_true")
    parser.add_argument("--settle-steps", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.settle_steps <= 500:
        parser.error("--settle-steps must be in [1, 500]")
    repo = args.repo.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier probe.
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    from gapa.domain.task import TaskDSL
    from gapa.perception import VLMFeedbackProvider
    from gapa.runtime.api import ArmTag, ProgramCandidate, execute_program_candidate, _initial_poses
    from gapa.runtime.runner import GapaRunner, write_json
    from gapa.runtime.success import SuccessChecker

    manifest = {"probe": "controlled_gripper_release", "seed": 2, "injected": False,
                "perception": "oracle", "stage_monitor": "real VLMFeedbackProvider",
                "source": "hand_written_fixed_program", "agent_generated_recovery": False,
                "recovery_requested": args.recover, "reset_or_teleport": False, "attempts": [],
                "scope": "single controlled fault; not a success-rate or autonomous-recovery claim"}
    runner, env = GapaRunner(runs_root=output / "runner", memory_root=output / "unused_memory"), None
    task = TaskDSL.place("cup", "plate", "on")
    manifest["task"] = task.canonical_dict()
    (output / "program.py").write_text(SOURCE, encoding="utf-8")
    try:
        provider = VLMFeedbackProvider()
        if not provider.client.is_configured:
            raise RuntimeError("Real VLM credentials are not configured; no stub fallback is allowed.")
        manifest["vlm_model"] = provider.client.config.model
        env = runner._create_env(seed=2, save_path=output / "env", object_names=["cup", "plate"], task=task)
        initial = _initial_poses(env, task)
        manifest["initial_poses"] = initial

        class DropBeforeFeedback:
            fired = False

            def verify_stage(self, current_env, event, run_dir=None):
                if not self.fired and event.stage == "after_lift" and event.object_name == "cup":
                    self.fired = True
                    actor = current_env.get_actor("cup")
                    before = actor.get_pose().p.tolist()
                    injection = {"event": event.to_dict(), "before_xyz": before,
                                 "method": "physical open_gripper followed by scene.step",
                                 "settle_steps": args.settle_steps, "drop_observed": False}
                    manifest["injection"] = injection
                    try:
                        current_env.save_camera_images(task_name="probe_drop", step_name="before_release",
                                                       generate_num_id="seed2", save_dir=str(output))
                    except Exception as exc:
                        injection["before_image_error"] = str(exc)
                    if before[2] - initial["cup"][2] < 0.03:
                        injection["skipped_reason"] = "cup_not_observed_lifted_3cm_above_initial_height"
                    else:
                        moved = current_env.move(current_env.open_gripper(ArmTag(event.arm), pos=1.0))
                        manifest["injected"] = bool(moved)
                        injection["open_gripper_return"] = bool(moved)
                        for _ in range(args.settle_steps):
                            current_env.scene.step()
                        after = actor.get_pose().p.tolist()
                        injection.update(after_xyz=after, drop_dz=before[2] - after[2],
                                         drop_observed=bool(moved and before[2] - after[2] > 0.02))
                    write_json(output / "manifest.json", manifest)
                # Unmodified event, real camera images, real model response.
                return provider.verify_stage(current_env, event, run_dir=run_dir)

        def execute(attempt, monitor):
            run_dir = output / f"attempt{attempt}"
            run_dir.mkdir()
            failure = execute_program_candidate(
                ProgramCandidate(f"fixed_pick_place_{attempt}", SOURCE), env, task,
                run_dir=str(run_dir), attempt_id=attempt, initial_poses=initial,
                perception_mode="oracle", stage_feedback_provider=monitor)
            trace = list(getattr(env, "gapa_api_trace", []))
            stages = [stage for call in trace for stage in call.get("stage_feedback", [])]
            result = {"attempt": attempt, "same_env": True, "manual_fixed_program": True,
                      "failure": failure.to_dict() if failure else None, "api_trace": trace,
                      "stage_evidence": stages, "place_call_reached": any(call.get("api") == "place" for call in trace),
                      "success_checker": SuccessChecker(env).check(task, initial_poses=initial)}
            manifest["attempts"].append(result)
            write_json(run_dir / "result.json", result)
            return failure

        failure = execute(1, DropBeforeFeedback())
        stage = failure.details.get("stage_feedback", {}) if failure else {}
        interrupted = stage.get("decision") == "interrupt" and stage.get("event", {}).get("stage") == "after_lift"
        observed = manifest.get("injection", {}).get("drop_observed", False)
        lift_evidence = [item for item in manifest["attempts"][0]["stage_evidence"]
                         if item.get("event", {}).get("stage") == "after_lift"]
        available = any(item.get("report", {}).get("status") in {"ok", "failed", "uncertain"} for item in lift_evidence)
        manifest["interrupted_at_after_lift"] = interrupted
        manifest["vlm_after_lift_response_available"] = available
        manifest["verdict"] = ("observed_drop_interrupted" if observed and interrupted else
                               "inconclusive_monitor_unavailable" if observed and not available else
                               "observed_drop_not_interrupted" if observed else "inconclusive_no_verified_drop")
        if args.recover and observed and interrupted:
            execute(2, provider)  # No scene reset; api.pose re-observes the fallen cup.
        elif args.recover:
            manifest["recovery_skipped"] = "requires both an observed drop and an after_lift interruption"
    except Exception:
        manifest["verdict"] = "probe_error"
        manifest["error"] = traceback.format_exc()
    finally:
        write_json(output / "manifest.json", manifest)
        runner._close_env(env)
    print(json.dumps({"manifest": str(output / "manifest.json"), "verdict": manifest.get("verdict")}, ensure_ascii=False))
    return 1 if manifest.get("verdict") == "probe_error" else 0


if __name__ == "__main__":
    raise SystemExit(main())
