"""Verification boundaries for the orchestrator and successful-example memory."""

import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from gapa.agents.orchestrator import AgentOrchestrator
from gapa.domain.task import FailureReport, TaskDSL
from gapa.memory import SuccessMemoryManager
from gapa.runtime.api import ProgramCandidate


SOURCE = '''
def play_once(api):
    source = api.pose("cup")
    target = api.target_pose(kind="object", target_name="plate", relation="on")
    arm = api.choose_arm(source)
    api.pick("cup", source, arm=arm, pre_grasp_dis=0.11, grasp_dis=0.01)
    api.place("cup", target, arm=arm, relation="on", target_name="plate", pre_dis=0.10, dis=0.02)
'''


class OrchestratorVerificationTest(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.memory = SuccessMemoryManager(Path(directory.name))
        self.task = TaskDSL.place("cup", "plate", "on")

    def orchestrator(self, execute=None, max_rounds=1):
        orchestrator = AgentOrchestrator(SimpleNamespace(is_configured=False), execute=execute,
                                         memory=self.memory, max_rounds=max_rounds)
        orchestrator.codegen_agent.generate = Mock(return_value=ProgramCandidate("candidate", SOURCE))
        return orchestrator

    def run_task(self, orchestrator, **kwargs):
        return orchestrator.run("put cup on plate", self.task, {"cup": {}, "plate": {}}, **kwargs)

    def test_codegen_only_returns_candidate_without_success_or_memory_write(self):
        result = self.run_task(self.orchestrator())
        self.assertEqual(result.status, "not_executed")
        self.assertEqual(result.selection_reason, "execution_not_configured")
        self.assertEqual(result.rounds[0].execution["status"], "skipped")
        self.assertTrue(result.rounds[0].safety["ok"])
        self.assertEqual(result.all_candidates[0].source, SOURCE)
        self.assertIsNone(result.successful_program)
        self.assertFalse(self.memory.episodes_path.exists())
        self.assertFalse(self.memory.jsonl_path.exists())

    def test_verified_callback_success_is_archived_and_reaches_next_generation_prompt(self):
        execute = Mock(return_value=None)
        orchestrator = self.orchestrator(execute)
        result = self.run_task(orchestrator, run_id="verified-run")
        self.assertEqual(result.status, "success")
        execute.assert_called_once()
        self.run_task(orchestrator, run_id="next-run")
        prompt = orchestrator.codegen_agent.generate.call_args.kwargs["success_memory"]
        self.assertIn('"pre_grasp_dis": 0.11', prompt)
        self.assertNotIn("def play_once", prompt)
        episodes = [json.loads(line) for line in self.memory.episodes_path.read_text().splitlines()]
        self.assertEqual([episode["run_id"] for episode in episodes], ["verified-run", "next-run"])
        self.assertEqual(episodes[0]["verification_scope"], "atomic_task_success")

    def test_execution_failure_never_updates_success_memory(self):
        execute = Mock(return_value=FailureReport(1, "pick", "grasp failed", "none"))
        result = self.run_task(self.orchestrator(execute))
        self.assertEqual(result.status, "failed")
        self.assertFalse(self.memory.episodes_path.exists())

    def test_env_execution_path_still_verifies_and_archives_success(self):
        env = object()
        with patch("gapa.agents.orchestrator.execute_program_candidate", return_value=None) as execute:
            result = self.run_task(self.orchestrator(), env=env)
        self.assertEqual(result.status, "success")
        self.assertIs(execute.call_args.args[1], env)
        self.assertTrue(self.memory.episodes_path.exists())

    def test_failed_round_is_not_archived_before_verified_recovery(self):
        execute = Mock(side_effect=[FailureReport(1, "pick", "grasp failed", "none"), None])
        result = self.run_task(self.orchestrator(execute, max_rounds=2), run_id="recovered")
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.rounds), 2)
        episodes = self.memory.episodes_path.read_text().splitlines()
        self.assertEqual(len(episodes), 1)
        self.assertEqual(json.loads(episodes[0])["run_id"], "recovered")


if __name__ == "__main__":
    unittest.main()
