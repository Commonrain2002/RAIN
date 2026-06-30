import typing as t
from pathlib import Path

from src.environment.config import LemmaContext
from src.config import CONFIG
from src.utils import get_logger

RESULTS_DIR = (
    (Path(CONFIG.ROOT_DIR) / "data/evaluation/goal_decomposition").resolve().absolute()
)
LOGGER = get_logger("evaluation.goal_decomposition")

DatasetName = t.Literal[
    "dev",
    "test",
    "test_perfect_subgoals",
    "wigderson_dev",
    "wigderson_err",
    "wigderson_dev_perfect_subgoals",
    "wigderson_test",
    "wigderson_test_perfect_subgoals",
    "coq_bb5_dev",
    "coq_bb5_test",
    "pnvrocqlib_dev",
    "pnvrocqlib_test",
    "pnvrocqlib_retrying",
]
DATASET_NAMES: t.List[DatasetName] = [
    "dev",
    "test",
    "test_perfect_subgoals",
    "wigderson_dev",
    "wigderson_err",
    "wigderson_dev_perfect_subgoals",
    "wigderson_test",
    "wigderson_test_perfect_subgoals",
    "coq_bb5_dev",
    "coq_bb5_test",
    "pnvrocqlib_dev",
    "pnvrocqlib_test",
    "pnvrocqlib_retrying",
]


LEMMA_CONTEXTS: t.List[LemmaContext] = [
    "preceding-lines",
    "preceding-lemmas-only",
    "preceding-lemmas-and-selected-premises",
    "perfect-premises",
]
