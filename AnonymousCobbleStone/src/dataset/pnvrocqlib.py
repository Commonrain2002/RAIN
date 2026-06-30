import pickle
import json
from pathlib import Path
import typing as t

from src.dataset.dataset import Dataset, Example, LemmaLocation
from src.config import CONFIG

# region TEST

PNV_ROCQLIB_TEST_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/PNV_ROCQLIB_TEST_SAMPLED_DATASET.pkl"
)

PNV_ROCQLIB_TEST_CSV_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/PNV_ROCQLIB_TEST_SAMPLED_DATASET.csv"
)

PNV_ROCQLIB_TEST_DATASET: Dataset = pickle.load(open(PNV_ROCQLIB_TEST_SAMPLED_FILE, "rb"))

# endregion TEST

# region DEV

PNV_ROCQLIB_DEV_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/PNV_ROCQLIB_DEV_SAMPLED_DATASET.pkl"
)


PNV_ROCQLIB_DEV_CSV_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/PNV_ROCQLIB_DEV_SAMPLED_DATASET.csv"
)

PNV_ROCQLIB_DEV_DATASET: Dataset = pickle.load(open(PNV_ROCQLIB_DEV_SAMPLED_FILE, "rb"))

# endregion DEV

# region RETRYING

PNV_ROCQLIB_RETRYING_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/PNV_ROCQLIB_RETRYING_SAMPLED_DATASET.pkl"
)

PNV_ROCQLIB_RETRYING_SAMPLED_CSV_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/PNV_ROCQLIB_RETRYING_SAMPLED_DATASET.csv"
)

PNV_ROCQLIB_RETRYING_SAMPLED_DATASET: Dataset = pickle.load(open(PNV_ROCQLIB_RETRYING_SAMPLED_FILE, "rb"))

# endregion RETRYING