import os
import json
import subprocess
from typing import Dict, Any, Optional


def get_git_metadata() -> Dict[str, Optional[Any]]:
    """Captures git commit, branch, and dirty status without raising exceptions."""
    metadata = {
        "git_commit": None,
        "git_branch": None,
        "git_dirty": None,
    }

    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        metadata["git_commit"] = commit or None
    except Exception:
        pass

    try:
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        metadata["git_branch"] = branch or None
    except Exception:
        pass

    try:
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        metadata["git_dirty"] = bool(status)
    except Exception:
        pass

    return metadata


class ExperimentLogger:
    """Handles appending experiment run records to versioned JSONL files."""

    def __init__(self, base_dir: Optional[str] = None, version: str = "v0", filename: str = "runs.jsonl"):
        if base_dir is None:
            # Default to <repo_root>/experiments/<version>
            repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
            self.output_dir = os.path.join(repo_root, "experiments", version)
        else:
            self.output_dir = os.path.join(base_dir, version)

        self.version = version
        self.filename = filename
        self.filepath = os.path.join(self.output_dir, self.filename)

    def append(self, record: Dict[str, Any]) -> str:
        """Appends a valid UTF-8 JSON record as a line in the versioned runs.jsonl file."""
        os.makedirs(self.output_dir, exist_ok=True)
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return self.filepath
