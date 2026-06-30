from src.utils import get_logger
import typing as t

LOGGER = get_logger("evaluation.regenerate_from_failure_point")

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

