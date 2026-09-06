"""Official GAIA benchmark evaluation metrics and scoring functions.

Vendored from official GAIA leaderboard:
Repository/Space: gaia-benchmark/leaderboard
Source file: scorer.py
Commit: 9f133d71362e77b3539f1514f31b9c101a545fec
Reference: GAIA: a benchmark for General AI Assistants (Mialon et al., 2023)
"""

import re
import string
import warnings
from typing import Optional, List, Any

SCORER_NAME = "official-gaia-leaderboard"
SCORER_COMMIT = "9f133d71362e77b3539f1514f31b9c101a545fec"


def normalize_number_str(number_str: str) -> float:
    """Replaces common currency and unit symbols to allow float conversion."""
    for char in ["$", "%", ","]:
        number_str = number_str.replace(char, "")
    try:
        return float(number_str)
    except ValueError:
        return float("inf")


def split_string(
    s: str,
    char_list: Optional[List[str]] = None,
) -> List[str]:
    """Splits string on specified delimiter characters (default: comma and semicolon)."""
    if char_list is None:
        char_list = [",", ";"]
    pattern = f"[{''.join(char_list)}]"
    return re.split(pattern, s)


def normalize_str(input_str: str, remove_punct: bool = True) -> str:
    """Normalizes a string by:
    - Removing all white spaces (e.g. for 'sea gull' vs 'seagull')
    - Optionally removing punctuation (if remove_punct is True)
    - Converting to lowercase
    """
    no_spaces = re.sub(r"\s", "", input_str)
    if remove_punct:
        translator = str.maketrans("", "", string.punctuation)
        return no_spaces.lower().translate(translator)
    else:
        return no_spaces.lower()


def question_scorer(
    model_answer: Optional[str],
    ground_truth: str,
) -> bool:
    """Official GAIA question scoring function from gaia-benchmark/leaderboard.

    Handles:
    - Numeric answers (stripping $, %, commas)
    - Comma and semicolon separated lists
    - Punctuation removal for scalar string answers
    - Preserving punctuation inside list elements
    - Complete whitespace removal
    - Case insensitivity
    - None model predictions
    """
    def is_float(element: Any) -> bool:
        try:
            float(element)
            return True
        except (ValueError, TypeError):
            return False

    if model_answer is None:
        model_answer = "None"
    else:
        model_answer = str(model_answer)

    ground_truth = str(ground_truth)

    # If ground truth is a number
    if is_float(ground_truth):
        normalized_answer = normalize_number_str(model_answer)
        return normalized_answer == float(ground_truth)

    # If ground truth is a list (contains comma or semicolon)
    elif any(char in ground_truth for char in [",", ";"]):
        gt_elems = split_string(ground_truth)
        ma_elems = split_string(model_answer)

        # Check length is the same
        if len(gt_elems) != len(ma_elems):
            warnings.warn(
                "Answer lists have different lengths, returning False.", UserWarning
            )
            return False

        # Compare each element as float or str
        comparisons = []
        for ma_elem, gt_elem in zip(ma_elems, gt_elems):
            if is_float(gt_elem):
                normalized_ma_elem = normalize_number_str(ma_elem)
                comparisons.append(normalized_ma_elem == float(gt_elem))
            else:
                # Quirk in official scorer: does not remove punctuation in list elements
                comparisons.append(
                    normalize_str(ma_elem, remove_punct=False)
                    == normalize_str(gt_elem, remove_punct=False)
                )
        return all(comparisons)

    # If ground truth is a regular string
    else:
        return normalize_str(model_answer) == normalize_str(ground_truth)


# Official alias matching requirements
gaia_question_scorer = question_scorer


def normalize_answer(text: Optional[str]) -> str:
    """Retained helper for general text normalization."""
    if text is None:
        return ""
    return normalize_str(str(text))


def check_exact_match(prediction: Optional[str], ground_truth: Optional[str]) -> bool:
    """Evaluates match using official GAIA question scorer."""
    if ground_truth is None:
        return False
    return gaia_question_scorer(prediction, ground_truth)
