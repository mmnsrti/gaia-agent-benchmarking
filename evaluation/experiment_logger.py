import os
import json
import subprocess
from typing import Dict, Any, Optional


_CACHED_GIT_METADATA: Optional[Dict[str, Optional[Any]]] = None


def ensure_healthy_git_index(repo_root: Optional[str] = None) -> None:
    """Detects and repairs a truncated or zero-byte .git/index file automatically."""
    if repo_root is None:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    index_path = os.path.join(repo_root, ".git", "index")
    if os.path.exists(index_path):
        try:
            if os.path.getsize(index_path) < 12:
                os.remove(index_path)
                subprocess.run(
                    ["git", "reset"],
                    cwd=repo_root,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
        except Exception:
            pass


def get_git_metadata(cached: bool = True) -> Dict[str, Optional[Any]]:
    """Captures git commit, branch, and dirty status safely without lock contention."""
    global _CACHED_GIT_METADATA
    if cached and _CACHED_GIT_METADATA is not None:
        return dict(_CACHED_GIT_METADATA)

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ensure_healthy_git_index(repo_root)

    metadata = {
        "git_commit": None,
        "git_branch": None,
        "git_dirty": None,
    }

    # Fast path: read commit SHA and branch name directly from .git files (zero subprocess overhead)
    git_dir = os.path.join(repo_root, ".git")
    head_path = os.path.join(git_dir, "HEAD")
    if os.path.isfile(head_path):
        try:
            with open(head_path, "r", encoding="utf-8") as f:
                head_content = f.read().strip()
            if head_content.startswith("ref: "):
                ref_rel = head_content[5:].strip()
                metadata["git_branch"] = ref_rel.replace("refs/heads/", "")
                ref_file = os.path.join(git_dir, ref_rel.replace("/", os.sep))
                if os.path.isfile(ref_file):
                    with open(ref_file, "r", encoding="utf-8") as f:
                        metadata["git_commit"] = f.read().strip() or None
                else:
                    packed_file = os.path.join(git_dir, "packed-refs")
                    if os.path.isfile(packed_file):
                        with open(packed_file, "r", encoding="utf-8") as f:
                            for line in f:
                                line = line.strip()
                                if line.endswith(ref_rel):
                                    metadata["git_commit"] = line.split()[0]
                                    break
            elif len(head_content) == 40:
                metadata["git_commit"] = head_content
        except Exception:
            pass

    # Fallback to subprocess with --no-optional-locks if commit or branch not resolved
    env = dict(os.environ, GIT_OPTIONAL_LOCKS="0")
    if not metadata["git_commit"]:
        try:
            commit = subprocess.check_output(
                ["git", "--no-optional-locks", "rev-parse", "HEAD"],
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=repo_root,
                timeout=5,
            ).decode().strip()
            metadata["git_commit"] = commit or None
        except Exception:
            pass

    if not metadata["git_branch"]:
        try:
            branch = subprocess.check_output(
                ["git", "--no-optional-locks", "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=repo_root,
                timeout=5,
            ).decode().strip()
            metadata["git_branch"] = branch or None
        except Exception:
            pass

    try:
        status = subprocess.check_output(
            ["git", "--no-optional-locks", "status", "--porcelain"],
        diff_code = subprocess.run(
            ["git", "--no-optional-locks", "diff-index", "--quiet", "HEAD", "--"],
            stderr=subprocess.DEVNULL,
            env=env,
            cwd=repo_root,
            timeout=5,
        ).decode().strip()
        metadata["git_dirty"] = bool(status)
        ).returncode
        if diff_code != 0:
            metadata["git_dirty"] = True
        else:
            untracked = subprocess.check_output(
                ["git", "--no-optional-locks", "ls-files", "--others", "--exclude-standard"],
                stderr=subprocess.DEVNULL,
                env=env,
                cwd=repo_root,
                timeout=5,
            ).decode().strip()
            metadata["git_dirty"] = bool(untracked)
    except Exception:
        pass

    if cached:
        _CACHED_GIT_METADATA = dict(metadata)

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
