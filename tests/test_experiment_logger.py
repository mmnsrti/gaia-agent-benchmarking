import os
import json
import shutil
import tempfile
import unittest
import uuid
from evaluation.experiment_logger import ExperimentLogger, get_git_metadata


class TestExperimentLogger(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_logger_creates_version_dir_and_appends(self):
        logger = ExperimentLogger(base_dir=self.test_dir, version="v0", filename="test_runs.jsonl")
        record1 = {
            "schema_version": 2,
            "run_id": str(uuid.uuid4()),
            "request_success": True,
            "completion_success": True,
            "finish_reason": "STOP",
            "output_tokens": 15,
            "thinking_tokens": 120,
        }
        record2 = {
            "schema_version": 2,
            "run_id": str(uuid.uuid4()),
            "request_success": True,
            "completion_success": False,
            "finish_reason": "MAX_TOKENS",
            "output_tokens": 2048,
            "thinking_tokens": 1800,
        }

        path1 = logger.append(record1)
        path2 = logger.append(record2)

        self.assertEqual(path1, path2)
        self.assertTrue(os.path.exists(path1))

        with open(path1, "r", encoding="utf-8") as f:
            lines = [json.loads(line) for line in f if line.strip()]

        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0]["schema_version"], 2)
        self.assertEqual(lines[0]["finish_reason"], "STOP")
        self.assertTrue(lines[0]["completion_success"])
        self.assertEqual(lines[0]["thinking_tokens"], 120)

        self.assertEqual(lines[1]["schema_version"], 2)
        self.assertEqual(lines[1]["finish_reason"], "MAX_TOKENS")
        self.assertFalse(lines[1]["completion_success"])
        self.assertEqual(lines[1]["thinking_tokens"], 1800)

    def test_git_metadata_does_not_crash(self):
        meta = get_git_metadata()
        self.assertIsInstance(meta, dict)
        self.assertIn("git_commit", meta)
        self.assertIn("git_branch", meta)
        self.assertIn("git_dirty", meta)

    def test_record_schema_no_secrets_and_null_types(self):
        logger = ExperimentLogger(base_dir=self.test_dir, version="v0")
        record = {
            "schema_version": 2,
            "run_id": str(uuid.uuid4()),
            "request_success": False,
            "completion_success": False,
            "finish_reason": None,
            "temperature": None,
            "thinking_level": "medium",
            "thinking_tokens": None,
            "output_tokens": None,
            "raw_response": None,
            "final_answer": None,
            "error_type": "RuntimeError",
            "error_message": "Rate limit exceeded",
        }
        path = logger.append(record)
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn('"schema_version": 2', content)
        self.assertIn('"temperature": null', content)
        self.assertIn('"thinking_tokens": null', content)
        self.assertIn('"output_tokens": null', content)
        self.assertIn('"finish_reason": null', content)
        self.assertIn('"raw_response": null', content)
        self.assertIn('"final_answer": null', content)
        self.assertNotIn("API_KEY", content)
        self.assertNotIn("fake-key", content)

    def test_ensure_healthy_git_index_repairs_corrupt_index(self):
        from evaluation.experiment_logger import ensure_healthy_git_index
        # Create a mock .git directory with a 0-byte index
        git_dir = os.path.join(self.test_dir, ".git")
        os.makedirs(git_dir, exist_ok=True)
        index_path = os.path.join(git_dir, "index")
        with open(index_path, "w") as f:
            f.write("")  # 0 bytes

        self.assertEqual(os.path.getsize(index_path), 0)
        # Should detect < 12 bytes and remove the corrupted index
        ensure_healthy_git_index(self.test_dir)
        self.assertFalse(os.path.exists(index_path))


if __name__ == "__main__":
    unittest.main()
