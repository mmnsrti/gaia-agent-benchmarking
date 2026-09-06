"""Dataset loader for local GAIA benchmark tasks.

Supports official GAIA benchmark schema and files:
- Formats: Parquet (.parquet), JSON Lines (.jsonl), JSON (.json)
- Official fields:
    task_id: unique task identifier
    Question: task prompt text (also supports 'question')
    Level: task difficulty level (1, 2, 3) (also supports 'level')
    Final answer: ground-truth target (also supports 'final_answer', 'ground_truth')
    file_name: optional attached filename (also supports 'file')
    file_path: optional path to attachment
    Annotator Metadata: optional annotation details
- Default split: GAIA 2023 validation
- Standard directory: data/gaia/

How to place and load local gated GAIA validation dataset:
1. Download official validation split from Hugging Face: gaia-benchmark/GAIA (2023 validation split)
2. Place the file at:
     data/gaia/2023/validation/metadata.parquet
   or:
     data/gaia/metadata.parquet
   or:
     data/gaia/metadata.jsonl
3. When attachments are present, place them under the corresponding directory (e.g. data/gaia/2023/validation/).
Note: Local benchmark files are gitignored and MUST NEVER be committed to the repository.
"""

import os
import json
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

# Expected counts for official GAIA 2023 validation split
EXPECTED_VALIDATION_COUNTS = {
    1: 53,
    2: 86,
    3: 26,
    None: 165,
}


@dataclass
class GAIATask:
    """Represents a single benchmark task loaded from local GAIA dataset."""
    task_id: str
    question: str
    level: int
    final_answer: Optional[str] = None
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    annotator_metadata: Optional[Dict[str, Any]] = None

    @property
    def has_attachment(self) -> bool:
        return bool(self.file_name and self.file_name.strip())


def _clean_str(val: Any) -> Optional[str]:
    """Helper to clean string values and handle NaN/empty values from DataFrames/JSON."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() == "nan":
        return None
    return s


def _parse_task_dict(data: Dict[str, Any], require_ground_truth: bool = False) -> GAIATask:
    """Extracts task attributes accommodating both official GAIA and course benchmark key variations."""
    task_id = str(data.get("task_id") or data.get("task_id_") or data.get("id") or "").strip()
    if not task_id:
        raise ValueError("Encountered task record without a valid 'task_id'.")

    # Official 'Question' or normalized 'question'
    raw_question = data.get("Question") if data.get("Question") is not None else data.get("question")
    question = _clean_str(raw_question) or ""

    # Official 'Level' or normalized 'level'
    raw_level = data.get("Level") if data.get("Level") is not None else data.get("level")
    try:
        level = int(raw_level)
    except (ValueError, TypeError):
        level = 1

    # Official 'Final answer' or normalized 'final_answer' / 'ground_truth'
    raw_answer = None
    for key in ["Final answer", "final_answer", "ground_truth", "target"]:
        if key in data and data[key] is not None:
            raw_answer = data[key]
            break

    final_answer = _clean_str(raw_answer)
    if require_ground_truth and final_answer is None:
        raise ValueError(
            f"Ground truth 'Final answer' missing or empty for task '{task_id}'. "
            "Evaluation requires valid ground truth."
        )

    # Attachments
    file_name = _clean_str(data.get("file_name") or data.get("file"))
    file_path = _clean_str(data.get("file_path"))

    # Metadata
    annotator_meta = data.get("Annotator Metadata") or data.get("annotator_metadata")
    if isinstance(annotator_meta, str):
        try:
            annotator_meta = json.loads(annotator_meta)
        except Exception:
            pass

    return GAIATask(
        task_id=task_id,
        question=question,
        level=level,
        final_answer=final_answer,
        file_name=file_name,
        file_path=file_path,
        annotator_metadata=annotator_meta if isinstance(annotator_meta, dict) else None,
    )


def resolve_gaia_data_path(data_path: Optional[str] = None) -> str:
    """Resolves local GAIA dataset path, searching standard candidate locations if none provided."""
    if data_path and os.path.isfile(data_path):
        return os.path.abspath(data_path)

    search_dirs = []
    if data_path and os.path.isdir(data_path):
        search_dirs.append(os.path.abspath(data_path))
    else:
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        search_dirs.append(os.path.join(repo_root, "data", "gaia"))
        search_dirs.append(os.path.join(repo_root, "data"))

    candidate_rel_paths = [
        os.path.join("2023", "validation", "metadata.parquet"),
        os.path.join("validation", "metadata.parquet"),
        "metadata.parquet",
        os.path.join("2023", "validation", "metadata.jsonl"),
        os.path.join("validation", "metadata.jsonl"),
        "metadata.jsonl",
        "val.jsonl",
        "tasks.jsonl",
        "tasks.json",
    ]

    for base_dir in search_dirs:
        for rel_path in candidate_rel_paths:
            full_path = os.path.join(base_dir, rel_path)
            if os.path.isfile(full_path):
                return full_path

    searched_desc = "\n".join([f"  - {os.path.join(d, rel)}" for d in search_dirs for rel in candidate_rel_paths[:4]])
    raise FileNotFoundError(
        f"Local GAIA dataset not found at '{data_path or 'data/gaia/'}'.\n"
        "Please ensure local benchmark data is placed under 'data/gaia/' (e.g. 'data/gaia/2023/validation/metadata.parquet' or 'data/gaia/metadata.parquet').\n"
        f"Searched locations include:\n{searched_desc}\n"
        "Note: Benchmark files are gitignored and must never be committed to the repository."
    )


def load_gaia_tasks(
    data_path: Optional[str] = None,
    level: Optional[int] = None,
    require_ground_truth: bool = False,
) -> List[GAIATask]:
    """Loads benchmark tasks from a local Parquet, JSONL, or JSON file.

    Parameters:
    - data_path: Path to dataset file or directory. If None, default search paths are checked.
    - level: Optional filter for GAIA difficulty level (1, 2, or 3).
    - require_ground_truth: If True, raises ValueError if any task has missing or empty ground truth.

    Raises:
    - FileNotFoundError: If dataset file cannot be found.
    - ValueError: If format is unsupported, parsing fails, or required ground truth is missing.
    """
    resolved_path = resolve_gaia_data_path(data_path)
    tasks: List[GAIATask] = []

    if resolved_path.endswith(".parquet"):
        try:
            import pandas as pd
        except ImportError:
            raise ImportError(
                "Loading .parquet datasets requires pandas and pyarrow. "
                "Please run 'pip install pandas pyarrow'."
            )
        try:
            df = pd.read_parquet(resolved_path)
            records = df.to_dict(orient="records")
            for line_idx, r in enumerate(records, start=1):
                try:
                    tasks.append(_parse_task_dict(r, require_ground_truth=require_ground_truth))
                except Exception as e:
                    raise ValueError(f"Error parsing row {line_idx} in {resolved_path}: {e}")
        except Exception as e:
            if not isinstance(e, ValueError):
                raise ValueError(f"Failed to read parquet file '{resolved_path}': {e}")
            raise

    elif resolved_path.endswith(".jsonl"):
        with open(resolved_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    tasks.append(_parse_task_dict(data, require_ground_truth=require_ground_truth))
                except Exception as e:
                    raise ValueError(f"Error parsing line {line_idx} in {resolved_path}: {e}")

    elif resolved_path.endswith(".json"):
        with open(resolved_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
            except Exception as e:
                raise ValueError(f"Error parsing JSON in {resolved_path}: {e}")

            if isinstance(data, list):
                for item in data:
                    tasks.append(_parse_task_dict(item, require_ground_truth=require_ground_truth))
            elif isinstance(data, dict):
                items = data.get("tasks") or data.get("data") or [data]
                for item in items:
                    tasks.append(_parse_task_dict(item, require_ground_truth=require_ground_truth))
    else:
        raise ValueError(
            f"Unsupported dataset format '{resolved_path}'. Expected .parquet, .jsonl, or .json."
        )

    if level is not None:
        tasks = [t for t in tasks if t.level == level]

    return tasks
