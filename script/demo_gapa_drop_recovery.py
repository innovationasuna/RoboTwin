#!/usr/bin/env python3
"""Controlled fault injection, not a natural failure or an Agent recovery benchmark.

Run with the RoboTwin environment: python demo_gapa_drop_recovery.py --repo /path/to/RoboTwin
Both attempts use actual CodegenAgent programs; FeedbackAgent diagnoses the fault.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import traceback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("runs_gapa/agent_drop_seed2"))
    parser.add_argument("--settle-steps", type=int, default=120)
    args = parser.parse_args()
    if not 1 <= args.settle_steps <= 500:
        parser.error("--settle-steps must be in [1, 500]")
    repo = args.repo.expanduser().resolve()
    output = args.output.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=False)  # Never overwrite an earlier probe.
    os.chdir(repo)
    sys.path.insert(0, str(repo))
    from gapa.agents.orchestrator import AgentOrchestrator
    from gapa.domain.task import TaskDSL
    from gapa.perception import VLMFeedbackProvider
    from gapa.runtime.api import ArmTag, execute_program_candidate, _initial_poses
    from gapa.runtime.runner import GapaRunner, write_json
    from gapa.runtime.success import SuccessChecker

    manifest = {"probe": "controlled_gripper_release", "seed": 2, "injected": False,
                "perception": "oracle", "stage_monitor": "real VLMFeedbackProvider",
                "source": "CodegenAgent", "agent_generated_recovery": True,
                "recovery_requested": True, "reset_or_teleport": False, "attempts": [],
                "scope": "single controlled fault with agent-generated recovery; not a success-rate benchmark"}
    runner, env = GapaRunner(runs_root=output / "runner", memory_root=output / "isolated_memory"), None
    task = TaskDSL.place("cup", "plate", "on")
    manifest["task"] = task.canonical_dict()
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
                        for step in range(args.settle_steps):
                            current_env.scene.step()
                            if step % 5 == 0:
                                current_env._take_picture()
                        after = actor.get_pose().p.tolist()
                        injection.update(after_xyz=after, drop_dz=before[2] - after[2],
                                         drop_observed=bool(moved and before[2] - after[2] > 0.02))
                    write_json(output / "manifest.json", manifest)
                # Unmodified event, real camera images, real model response.
                return provider.verify_stage(current_env, event, run_dir=run_dir)

        monitor = DropBeforeFeedback()
        videos = []

        def execute(program, current_task, attempt):
            run_dir = output / f"attempt{attempt}"
            run_dir.mkdir()
            (run_dir / "program.py").write_text(program.source, encoding="utf-8")
            runner._begin_collect_data_attempt(env, output, attempt)
            try:
                failure = execute_program_candidate(
                    program, env, current_task, run_dir=str(run_dir), attempt_id=attempt,
                    initial_poses=initial, perception_mode="oracle", stage_feedback_provider=monitor)
                if failure:
                    runner._attach_recovery_context(failure, env, attempt, current_task)
                trace = list(getattr(env, "gapa_api_trace", []))
                result = {"attempt": attempt, "same_env": True, "agent_generated": True,
                          "failure": failure.to_dict() if failure else None, "api_trace": trace,
                          "place_call_reached": any(call.get("api") == "place" for call in trace),
                          "success_checker": SuccessChecker(env).check(current_task, initial_poses=initial)}
                manifest["attempts"].append(result)
                write_json(run_dir / "result.json", result)
                write_json(output / "manifest.json", manifest)
                return failure
            finally:
                video = runner._finalize_collect_data_attempt(env, output, attempt)
                if video:
                    videos.append(video)

        selection = AgentOrchestrator(runner.planner.llm_client, execute=execute,
                                      memory=runner.memory, max_rounds=3).run(
            instruction="把杯子放到盘子上", task=task, scene_objects=env.get_scene_description(),
            scene_context={"cluttered_table": False}, run_id=output.name)
        write_json(output / "agent_rounds.json", selection.to_dict())
        manifest["selection"] = selection.to_dict()
        observed = manifest.get("injection", {}).get("drop_observed", False)
        first = manifest["attempts"][0] if manifest["attempts"] else {}
        stage = (first.get("failure") or {}).get("details", {}).get("stage_feedback", {})
        interrupted = stage.get("decision") == "interrupt"
        manifest["interrupted_at_after_lift"] = interrupted
        recovered = selection.status == "success" and len(manifest["attempts"]) > 1
        manifest["verdict"] = ("observed_drop_agent_recovered" if observed and interrupted and recovered
                               else "incomplete_recovery_demo")
        manifest["videos"] = videos
    except Exception:
        manifest["verdict"] = "probe_error"
        manifest["error"] = traceback.format_exc()
    finally:
        write_json(output / "manifest.json", manifest)
        runner._close_env(env)
    print(json.dumps({"manifest": str(output / "manifest.json"), "verdict": manifest.get("verdict")}, ensure_ascii=False))
    return 0 if manifest.get("verdict") == "observed_drop_agent_recovered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
