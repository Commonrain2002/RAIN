import typing as t
from pathlib import Path
import numpy as np

from src.config import CONFIG
from src.utils import get_logger

DatasetName = t.Literal[
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_dev_perfect_subgoals",
    "wigderson_test",
    "wigderson_test_perfect_subgoals",
    "coq_bb5_dev",
    "coq_bb5_test",
    "pnvrocqlib_dev",
    "pnvrocqlib_test",
]
DATASET_NAMES: t.List[DatasetName] = [
    "dev",
    "test",
    "wigderson_dev",
    "wigderson_dev_perfect_subgoals",
    "wigderson_test",
    "wigderson_test_perfect_subgoals",
    "coq_bb5_dev",
    "coq_bb5_test",
    "pnvrocqlib_dev",
    "pnvrocqlib_test",
]

RESULTS_DIR = (
    (Path(CONFIG.ROOT_DIR) / "data/evaluation/zero_shot_pass_at_k").resolve().absolute()
)
LOGGER = get_logger("evaluation.zero_shot_pass_at_k")


# based on the humaneval paper
def pass_at_k(n, c, k):
    """
    :param n: total number of samples
    :param c: number of correct samples :param k: k in pass@$k$
    """
    if n - c < k:
        return 1.0
    return 1.0 - np.prod(1.0 - k / np.arange(n - c + 1, n + 1))


class SampleJSON(t.TypedDict):
    code: str
    success: bool
