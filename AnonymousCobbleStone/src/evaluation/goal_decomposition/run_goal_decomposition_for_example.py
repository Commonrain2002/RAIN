import time
import typing as t
from pathlib import Path
import traceback

from src.utils import Tqdm, TqdmFunc, set_example_name
from .example_wall_times import ExampleWallTime, utc_now_iso
from .utils import LOGGER
from src.llm import Usage
from src.dataset import (
    Example,
    COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES,
    COQ_WIGDERSON_TEST_PERFECT_PREMISE_NAMES,
    COQGYM_TEST_SAMPLED_PERFECT_PREMISE_NAMES,
)
from src.strategy.goal_decomposition import (
    GoalDecompositionConfig,
    GoalDecompositionStrategy,
)
from src.environment import LemmaContext, Environment
from src.llm.model_names import OpenaiChatModelName

ProcessArg = t.Tuple[
    Example,
    int,
    int,
    bool,
    Path,
    LemmaContext,
    OpenaiChatModelName,
    t.Optional[float],
]
ProcessFn = t.Callable[
    [ProcessArg, t.Any, t.Any],
    t.Tuple[Example, t.Optional[str], Usage, ExampleWallTime, bool],
]


def run_goal_decomposition_for_example_tuple(
    arg: ProcessArg,
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[Example, t.Optional[str], Usage, ExampleWallTime]:
    started_at = utc_now_iso()
    start_perf = time.perf_counter()
    proof: t.Optional[str] = None
    usage = Usage(name="run_goal_decomposition_for_example")
    successful = False
    wall_budget_exhausted = False
    try:
        proof, usage, wall_budget_exhausted = run_goal_decomposition_for_example(
            *arg, tqdm_func, global_tqdm
        )
        successful = proof is not None
        if wall_budget_exhausted and not successful:
            LOGGER.warning(
                "example stopped: cumulative wall budget exhausted for this session",
                extra={"example": arg[0].name},
            )
    except Exception as e:
        LOGGER.critical(
            f"uncaught error while running goal decomposition",
            extra={
                "example": arg[0].name,
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )
    finally:
        try:
            Environment.teardown_all()
        except Exception as e:
            LOGGER.critical(
                f"error while tearing down environment. ignoring",
                extra={
                    "example": arg[0].name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
        wall_time = _wall_time(start_perf, started_at, successful)
    return arg[0], proof, usage, wall_time, wall_budget_exhausted


def _wall_time(
    start_perf: float, started_at: str, successful: bool
) -> ExampleWallTime:
    return ExampleWallTime(
        duration_seconds=time.perf_counter() - start_perf,
        started_at=started_at,
        finished_at=utc_now_iso(),
        successful=successful,
    )


def run_goal_decomposition_for_example(
    example: Example,
    max_nodes_to_expand: int,
    max_depth: int,
    try_hammer: bool,
    directory_path: Path,
    lemma_context: LemmaContext,
    model: OpenaiChatModelName,
    session_wall_budget_seconds: t.Optional[float],
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[t.Optional[str], Usage, bool]:
    set_example_name(example.name)
    LOGGER.info(
        f"running goal decomposition for example {example.name}",
        extra={
            "example": example.name,
            "max_nodes_to_expand": max_nodes_to_expand,
        },
    )

    example_name_without_tag = (
        example.name[0 : -len(f"-{example.tag}")] if example.tag else example.name
    )
    premise_names: t.List[str] | None = None
    if lemma_context == "perfect-premises":
        premise_names = COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES.get(
            example_name_without_tag,
            COQ_WIGDERSON_TEST_PERFECT_PREMISE_NAMES.get(
                example_name_without_tag,
                COQGYM_TEST_SAMPLED_PERFECT_PREMISE_NAMES.get(
                    example_name_without_tag, None
                ),
            ),
        )

    config = GoalDecompositionConfig(
        max_nodes_to_expand,
        session_wall_budget_seconds=session_wall_budget_seconds,
        lemma_context=lemma_context,
        state_file=directory_path / f"{example.name}.json",
        max_depth=max_depth,
        try_hammer=try_hammer,
        proof_prefix=example.proof_prefix,
        premise_names=premise_names,
        model=model,
    )

    strategy = GoalDecompositionStrategy(example,config)

    environment, usage = strategy.run(global_tqdm, tqdm_func)
    wall_budget_exhausted = strategy.search.wall_budget_exhausted

    if environment is not None and environment.is_initial_goal_proven:
        return environment.observation_code, usage, False

    return None, usage, wall_budget_exhausted

