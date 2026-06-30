import typing as t
from pathlib import Path

from src.environment.config import LemmaContext
from src.config import CONFIG
from src.utils import get_logger

LOGGER = get_logger("evaluation.goal_decomposition")

LEMMA_CONTEXTS: t.List[LemmaContext] = [
    "preceding-lines",
    "preceding-lemmas-only",
    "preceding-lemmas-and-selected-premises",
    "perfect-premises",
]

RESULTS_DIR = (
    (Path(CONFIG.ROOT_DIR) / "data/evaluation/next_tactic").resolve().absolute()
)
