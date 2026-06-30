import typing as t
from pathlib import Path
import json
import traceback
from functools import partial

from src.utils import Tqdm, TqdmFunc
from .utils import LOGGER
from src.llm.usage import Usage
from src.agent.zero_shot_tool import ZeroShotToolAgent, ZeroShotToolAgentConfig
from src.strategy.single_edit import SingleEditConfig, single_edit
from src.dataset import (
    Example,
    COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES,
    COQ_WIGDERSON_TEST_PERFECT_PREMISE_NAMES,
    COQGYM_TEST_SAMPLED_PERFECT_PREMISE_NAMES,
)
from src.premise_selection import select_premises
from src.environment import Environment, EnvironmentConfig, LemmaContext
from src.strategy import MakeAgentAndEnvironment
from src.coq_serapy_util import LemmaLocation
from src.llm.gpt import OpenaiChatPromptConfig
from src.llm.model_names import OpenaiChatModelName
from src.utils import set_example_name

Temperature = float
ProcessArg = t.Tuple[
    Example, int, t.List[t.Tuple[str, bool]], Path, LemmaContext, Temperature, OpenaiChatModelName
]
ProcessFn = t.Callable[
    [ProcessArg, t.Any, t.Any], t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]
]


def collect_samples_for_example_tuple(
    arg: ProcessArg,
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]:
    return collect_samples_for_example(*arg, tqdm_func, global_tqdm)


def collect_samples_for_example(
    example: Example,
    total_num_samples: int,
    existing_samples: t.List[t.Tuple[str, bool]],
    directory_path: Path,
    lemma_context: LemmaContext,
    temperature: Temperature,
    model: OpenaiChatModelName,
    tqdm_func: TqdmFunc,
    global_tqdm: Tqdm,
) -> t.Tuple[t.List[t.Tuple[Example, str, bool]], Usage]:
    set_example_name(example.name)
    LOGGER.info(
        "collecting samples for example",
        extra={
            "example": example.name,
            "total_num_samples": total_num_samples,
            "num_existing_samples": len(existing_samples),
        },
    )

    samples: t.List[t.Tuple[str, bool]] = existing_samples.copy()
    usage = Usage(name=example.name)

    selected_premises: t.List[str] = []
    if lemma_context == "preceding-lemmas-and-selected-premises":
        _, environment = make_agent_and_environment(
            lemma_context,
            temperature,
            model,
            #
            example.proposition_command,
            None,
            example.location,
            None,
        )
        selected_premises, p_usage = select_premises(
            environment.base_observation,
            environment.coq,
            include_reasoning=True,
            n_identifiers=5,
        )
        usage.add_child(p_usage)
    elif lemma_context == "perfect-premises":
        _, environment = make_agent_and_environment(
            lemma_context,
            temperature,
            model,
            #
            example.proposition_command,
            None,
            example.location,
            None,
        )
        example_name_without_tag = (
            example.name[0 : -len(f"-{example.tag}")] if example.tag else example.name
        )
        premise_names = COQ_WIGDERSON_DEV_PERFECT_PREMISE_NAMES.get(
            example_name_without_tag,
            COQ_WIGDERSON_TEST_PERFECT_PREMISE_NAMES.get(
                example_name_without_tag,
                COQGYM_TEST_SAMPLED_PERFECT_PREMISE_NAMES.get(
                    example_name_without_tag, None
                ),
            ),
        )
        LOGGER.info(
            "perfect premises",
            extra={
                "example": example.name,
                "premise_names": premise_names,
            },
        )
        selected_premises = (
            environment.coq.get_lemmas_for_identifiers(premise_names)
            if premise_names
            else []
        )

    def __make_agent_and_environment(
        proposition_command: str,
        hint: t.Optional[str],
        lemma_location: t.Optional[LemmaLocation],
        proof_prefix: t.Optional[str],
    ) -> t.Tuple[ZeroShotToolAgent, Environment]:
        nonlocal lemma_context
        agent, environment = make_agent_and_environment(
            lemma_context,
            temperature,
            model,
            #
            proposition_command,
            hint,
            lemma_location,
            proof_prefix,
        )
        if lemma_context == "preceding-lemmas-and-selected-premises":
            environment.add_lemmas(selected_premises)
        return agent, environment

    __TYPE_CHECK: MakeAgentAndEnvironment = __make_agent_and_environment

    num_samples_to_collect = total_num_samples - len(existing_samples)
    with tqdm_func(
        total=num_samples_to_collect,
        desc=example.name[: len("total progress")],
        dynamic_ncols=True,
    ) as bar:
        for i in range(num_samples_to_collect):
            try:
                environment, single_edit_usage = single_edit(
                    example,
                    __make_agent_and_environment,
                    config=SingleEditConfig(n=1, bar=False),
                )
                usage.add_child(single_edit_usage)
                if environment is not None:
                    samples.append((environment.observation_code, environment.done))
                else:
                    samples.append(("", False))
            except Exception as e:
                LOGGER.error(
                    f"error while collecting sample for {example} on attempt {i + 1}. Skipping this sample.",
                    extra={
                        "exception": str(e),
                        "example": example.name,
                        "attempt": i + 1,
                        "stacktrace": traceback.format_exc(),
                    },
                )
            finally:
                bar.update()
                global_tqdm.update()

    output_file = directory_path / f"{example.name}.samples.json"
    with open(output_file, "w") as f:
        json.dump([{"code": code, "success": success} for code, success in samples], f)

    Environment.teardown_all()
    return [(example, sample[0], sample[1]) for sample in samples], usage


def make_agent_and_environment(
    # config arguments to be passed via partial
    lemma_context: LemmaContext,
    temperature: Temperature,
    model: OpenaiChatModelName,
    # actual make agent and env arguments
    proposition_command: str,
    hint: t.Optional[str],
    lemma_location: t.Optional[LemmaLocation],
    proof_prefix: t.Optional[str],
) -> t.Tuple[ZeroShotToolAgent, Environment]:
    agent = ZeroShotToolAgent(
        proposition_command,
        config=ZeroShotToolAgentConfig(
            include_reasoning=True,
            chat_config=OpenaiChatPromptConfig(model=model, temperature=temperature),
        ),
    )
    environment = Environment(
        proposition_command,
        lemma_location,
        proof_prefix,
        config=EnvironmentConfig(lemma_context=lemma_context),
    )

    return agent, environment


__TYPE_CHECK: MakeAgentAndEnvironment = partial(
    make_agent_and_environment, "preceding-lemmas-only", 1, "gpt-4"
)
