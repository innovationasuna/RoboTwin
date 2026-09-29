import json
import tempfile
import unittest
from pathlib import Path

from gapa.domain.task import TaskDSL
from gapa.memory import SuccessMemoryManager


SOURCE = '''
def play_once(api):
    source_pose = api.pose("cup")
    target_pose = api.target_pose(kind="object", target_name="plate", relation="on", dx=0.03)
    arm = api.choose_arm(source_pose)
    api.pick("cup", source_pose, arm=arm, pre_grasp_dis=0.11, grasp_dis=0.01)
    api.place("cup", target_pose, arm=arm, relation="on", target_name="plate", pre_dis=0.12, dis=0.03)
'''


class SuccessEpisodeMemoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.memory = SuccessMemoryManager(Path(self.temp.name))
        self.task = TaskDSL.place("cup", "plate", "on")

    def record(self, source=SOURCE, **kwargs):
        self.memory.record_success(
            self.task, source, run_id=kwargs.pop("run_id", "run-1"),
            instruction="put the cup on the plate", **kwargs,
        )

    def episodes(self):
        return [json.loads(line) for line in self.memory.episodes_path.read_text().splitlines()]

    def test_archive_preserves_source_and_provenance_without_changing_five_strategies(self):
        self.record()
        episode, = self.episodes()
        self.assertEqual(episode["source"], SOURCE)
        self.assertEqual(episode["task"], self.task.canonical_dict())
        self.assertEqual(episode["run_id"], "run-1")
        self.assertEqual(episode["verification_scope"], "atomic_task_success")
        strategies = [json.loads(line) for line in self.memory.jsonl_path.read_text().splitlines()]
        self.assertEqual(len(strategies), 5)
        self.assertEqual(self.memory.retrieve_strategy(self.task)[0]["verified_success_count"], 1)
        self.assertNotIn("source", self.memory.retrieve_strategy(self.task)[0])
        self.assertTrue(episode["recorded_at"])

    def test_retrieval_exposes_only_literal_skill_parameters_not_coordinates_or_arm(self):
        self.record()
        example, = self.memory.retrieve_tuning_examples(self.task)
        self.assertEqual(example["tuning_calls"], [
            {"api": "pick", "object_name": "cup", "kwargs": {"pre_grasp_dis": 0.11, "grasp_dis": 0.01}},
            {"api": "place", "object_name": "cup", "target_name": "plate", "relation": "on",
             "kwargs": {"pre_dis": 0.12, "dis": 0.03}},
        ])
        prompt = self.memory.prompt_for(self.task)
        self.assertIn('"pre_grasp_dis": 0.11', prompt)
        self.assertIn("Re-localize", prompt)
        self.assertIn("never replay historical coordinates", prompt)
        self.assertNotIn('"dx"', prompt)
        self.assertNotIn('"arm"', prompt)
        self.assertNotIn("def play_once", prompt)
        self.assertNotIn("run-1", prompt)
        self.assertNotIn("put the cup on the plate", prompt)

    def test_cross_object_and_cross_target_queries_keep_strategy_but_not_learned_parameters(self):
        self.record()
        for task in (TaskDSL.place("bowl", "plate", "on"), TaskDSL.place("cup", "bowl", "on")):
            self.assertEqual(self.memory.retrieve_strategy(task)[0]["strategy_id"], "place_on")
            self.assertEqual(self.memory.retrieve_tuning_examples(task), [])
            self.assertNotIn('"pre_grasp_dis": 0.11', self.memory.prompt_for(task))

    def test_parent_composite_program_is_archived_but_not_independently_attributed(self):
        self.record(parent_run_id="parent-1", subtask_index=2)
        episode, = self.episodes()
        self.assertEqual(episode["parent_run_id"], "parent-1")
        self.assertEqual(episode["subtask_index"], 2)
        self.assertEqual(episode["verification_scope"], "parent_composite_success")
        self.assertEqual(episode["source_scope"], "whole_parent_program")
        self.assertEqual(episode["tuning_calls"], [])
        self.assertEqual(self.memory.retrieve_tuning_examples(self.task), [])
        self.assertEqual(self.memory.retrieve_strategy(self.task)[0]["verified_success_count"], 1)

    def test_composite_query_uses_only_compatible_atomic_examples(self):
        self.record()
        composite = TaskDSL(task_type="composite", sub_tasks=[self.task, TaskDSL.move("red_block", "left", 0.05)])
        self.assertEqual(len(self.memory.retrieve_tuning_examples(composite)), 1)
        prompt = self.memory.prompt_for(composite)
        self.assertIn("### place_on", prompt)
        self.assertIn("### move", prompt)
        self.assertIn('"pre_grasp_dis": 0.11', prompt)

    def test_invalid_dynamic_boolean_and_out_of_range_tunings_are_not_retrieved(self):
        self.record('''
def play_once(api):
    api.pick("cup", pose, arm, pre_grasp_dis=0.7, grasp_dis=True)
    api.pick("cup", pose, arm, pre_grasp_dis=dynamic_value, grasp_dis=float("nan"))
    api.pick("bowl", pose, arm, pre_grasp_dis=0.1)
    api.place("cup", target, arm, "on", "bowl", pre_dis=0.12)
    api.target_pose("offset", reference_pose=pose, dx=0.04)
''')
        self.assertEqual(self.episodes()[0]["tuning_calls"], [])
        self.assertEqual(self.memory.retrieve_tuning_examples(self.task), [])

    def test_positional_parameters_and_multiple_calls_stay_separate(self):
        self.record('''
def play_once(api):
    api.pick("cup", pose, arm, 0.10, 0.01)
    api.pick("cup", pose, arm, 0.12, 0.02)
''')
        calls = self.memory.retrieve_tuning_examples(self.task)[0]["tuning_calls"]
        self.assertEqual([call["kwargs"]["pre_grasp_dis"] for call in calls], [0.10, 0.12])

    def test_drawer_steps_require_integer_and_context_matches_cabinet(self):
        task = TaskDSL.place("playing_cards", "cabinet", "in")
        self.memory.record_success(task, '''
def play_once(api):
    api.open_drawer("cabinet", arm, pre_grasp_dis=0.06, pull_dis=0.04, pull_steps=4)
    api.open_drawer("cabinet", arm, pull_dis=0.04, pull_steps=2.5)
''', run_id="drawer-1", instruction="put cards in cabinet")
        calls = self.memory.retrieve_tuning_examples(task)[0]["tuning_calls"]
        self.assertEqual(calls[0]["kwargs"]["pull_steps"], 4)
        self.assertNotIn("pull_steps", calls[1]["kwargs"])

    def test_recent_reference_limit_and_persistence(self):
        for index in range(5):
            self.record(run_id=f"run-{index}")
        reloaded = SuccessMemoryManager(self.memory.root)
        self.assertEqual([item["run_id"] for item in reloaded.retrieve_tuning_examples(self.task)],
                         ["run-4", "run-3", "run-2"])
        self.assertEqual(reloaded.retrieve_tuning_examples(self.task, limit=0), [])

    def test_legacy_strategy_counts_survive_and_do_not_invent_episodes(self):
        self.memory.success_dir.mkdir(parents=True)
        self.memory.jsonl_path.write_text(json.dumps({"strategy_id": "place_on", "verified_success_count": 7}) + "\n")
        self.assertEqual(self.memory.retrieve_tuning_examples(self.task), [])
        self.assertIn("re-localize", self.memory.prompt_for(self.task))
        self.record()
        self.assertEqual(self.memory.retrieve_strategy(self.task)[0]["verified_success_count"], 8)
        self.assertEqual(len(self.episodes()), 1)

    def test_source_syntax_error_is_retained_for_provenance_without_tuning_claims(self):
        self.record(source="def bad(")
        self.assertEqual(self.episodes()[0]["source"], "def bad(")
        self.assertEqual(self.memory.retrieve_tuning_examples(self.task), [])


if __name__ == "__main__":
    unittest.main()
