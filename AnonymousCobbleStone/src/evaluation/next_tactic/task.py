import typing as t
from pathlib import Path
import traceback
from functools import partial

from src.utils import Tqdm, TqdmFunc, set_example_name
from .utils import LOGGER
from src.llm import Usage, OpenaiChatPromptConfig
from src.dataset import (
    Example,
    PERFECT_PREMISE_NAMES,
)
from src.agent.zero_shot_tool import ZeroShotToolAgent, ZeroShotToolAgentConfig
from src.strategy import MakeAgentAndEnvironment
from src.strategy.next_tactic import (
    NextTacticConfig,
    NextTacticStrategy,
)
from src.environment import LemmaContext, Environment, EnvironmentConfig
from src.coq_serapy_util import LemmaLocation

ProcessArg = t.Tuple[Example, int, int, bool, Path, LemmaContext]
ProcessFn = t.Callable[[ProcessArg, t.Any, t.Any], t.Tuple[t.Optional[str], Usage]]


def run_tbt_for_example_tuple(
    arg: ProcessArg,
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[Example, t.Optional[str], Usage]:
    """
    splats the tuple arg and catches any uncaught errors
    """
    try:
        result = (
            arg[0],
            *run_tbt_for_example(*arg, tqdm_func, global_tqdm),
        )
        return result
    except Exception as e:
        LOGGER.critical(
            f"uncaught error while running tbt search",
            extra={
                "example": arg[0].name,
                "error": str(e),
                "traceback": traceback.format_exc(),
            },
        )
        return arg[0], None, Usage(name="run_tbt_for_example")
    finally:
        Environment.teardown_all()


def run_tbt_for_example(
    example: Example,
    max_nodes_to_expand: int,
    max_depth: int,
    try_hammer: bool,
    directory_path: Path,
    lemma_context: LemmaContext,
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[t.Optional[str], Usage]:
    """
    runs the tbt search for a single example
    """
    set_example_name(example.name)
    LOGGER.info(
        f"running tbt search for example {example.name}",
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
        premise_names = PERFECT_PREMISE_NAMES.get(example_name_without_tag, None)

    config = NextTacticConfig(
        max_nodes_to_expand=max_nodes_to_expand,
        lemma_context=lemma_context,
        state_file=directory_path / f"{example.name}.json",
        max_depth=max_depth,
        try_hammer=try_hammer,
        proof_prefix=example.proof_prefix,
        premise_names=premise_names,
        max_num_children_per_node=3,
    )

    strategy = NextTacticStrategy(
        example,
        config,
    )

    environment, usage = strategy.run(global_tqdm, tqdm_func)

    if environment is not None and environment.is_initial_goal_proven:
        return environment.observation_code, usage

    return None, usage


def make_agent_and_environment(
    # config arguments to be passed via partial
    lemma_context: LemmaContext,
    # actual make agent and env arguments
    proposition_command: str,
    hint: t.Optional[str],
    lemma_location: t.Optional[LemmaLocation],
    proof_prefix: t.Optional[str],
) -> t.Tuple[ZeroShotToolAgent, Environment]:
    """
    same as usual make agent and environment, but with the additional lemma_context argument
    """
    agent = ZeroShotToolAgent(
        proposition_command,
        config=ZeroShotToolAgentConfig(
            include_reasoning=True, chat_config=OpenaiChatPromptConfig()
        ),
    )
    environment = Environment(
        proposition_command,
        lemma_location,
        proof_prefix,
        config=EnvironmentConfig(lemma_context=lemma_context),
    )

    return agent, environment


# this variable is just for type checking
__TYPE_CHECK: MakeAgentAndEnvironment = partial(
    make_agent_and_environment, "preceding-lemmas-only"
)
