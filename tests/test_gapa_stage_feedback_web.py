import unittest
from importlib import import_module
from unittest.mock import patch

from gapa.web.app import RunTaskRequest, run_task


class StageFeedbackWebTest(unittest.TestCase):
    def test_feedback_disabled_by_default_and_forwarded_explicitly(self):
        for enabled in (False, True):
            with self.subTest(enabled=enabled), patch.object(import_module("gapa.web.app"), "RUNNER") as runner:
                request = RunTaskRequest(instruction="put cup on plate", stage_feedback=enabled)
                run_task(request)
                runner.run_task.assert_called_once_with(
                    "put cup on plate", perception_mode="oracle", stage_feedback=enabled)
        self.assertFalse(RunTaskRequest(instruction="x").stage_feedback)


if __name__ == "__main__":
    unittest.main()
