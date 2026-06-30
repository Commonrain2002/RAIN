import pickle
import json
from pathlib import Path
import typing as t

from src.dataset.dataset import Dataset, Example, LemmaLocation
from src.config import CONFIG

# region TEST

COQ_BB5_TEST_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_BB5_TEST_SAMPLED_DATASET.pkl"
)

COQ_BB5_TEST_CSV_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_BB5_TEST_SAMPLED_DATASET.csv"
)

COQ_BB5_TEST_DATASET: Dataset = pickle.load(open(COQ_BB5_TEST_SAMPLED_FILE, "rb"))

# endregion TEST

# region DEV

COQ_BB5_DEV_SAMPLED_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_BB5_DEV_SAMPLED_DATASET.pkl"
)


COQ_BB5_DEV_CSV_FILE = (
    Path(CONFIG.ROOT_DIR) / "data/COQ_BB5_DEV_SAMPLED_DATASET.csv"
)

COQ_BB5_DEV_DATASET: Dataset = pickle.load(open(COQ_BB5_DEV_SAMPLED_FILE, "rb"))

# endregion DEV
