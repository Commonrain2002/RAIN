from dataclasses import dataclass
from tqdm import tqdm
import typing as t

from src.dataset import Example
from src.strategy.types_renamed import MakeAgentAndEnvironment, Strategy
from src.utils import get_logger
from src.environment import Environment, EditAction
from src.llm import Usage, UsageError

LOGGER = get_logger("strategy.single_edit")


@dataclass
class SingleEditConfig:
    n: int = 5
    bar: bool = True


def single_edit(
    example: Example,
    make_agent_and_environment: MakeAgentAndEnvironment,
    config: t.Optional[SingleEditConfig] = None,
) -> t.Tuple[t.Optional[Environment], Usage]:
    """
    try to solve the given lemma with just one edit action.
    """

    config = config or SingleEditConfig()

    LOGGER.info(f"trying to solve {example} with a single action")

    bar = (
        tqdm(
            total=config.n,
            desc=f"single edit ({example.proposition_command[0:10]})",
            dynamic_ncols=True,
        )
        if config.bar
        else None
    )

    usage = Usage(
        name="single_edit",
    )

    try:
        for attempt_number in range(config.n):
            LOGGER.info(
                f"attempt {attempt_number + 1}", extra={"attempt": attempt_number}
            )
            try:
                result, attempt_usage = single_edit_attempt(
                    example, make_agent_and_environment
                )
            except UsageError as e:
                usage.add_child(e.usage)
                LOGGER.error(
                    "attempt failed after LLM usage; preserving usage",
                    extra={"error": str(e), "usage": e.usage},
                )
                if bar:
                    bar.update(1)
                continue
            usage.add_child(attempt_usage)
            LOGGER.debug("usage", extra={"usage": usage})

            if bar:
                bar.update(1)
            if result:
                return result, usage
            else:
                continue
        return None, usage
    finally:
        if bar:
            bar.close()


__TYPE_CHECK: Strategy[SingleEditConfig] = single_edit


def single_edit_attempt(
    example: Example, make_agent_and_environment: MakeAgentAndEnvironment
) -> t.Tuple[t.Optional[Environment], Usage]:
    agent, environment = make_agent_and_environment(
        example.proposition_command, example.hint, example.location, None
    )

    observation = environment.base_observation
    LOGGER.info("initial observation", extra={"observation": observation})

    actions, usage = agent.act(observation)
    action = actions[0]

    if not isinstance(action, EditAction):
        LOGGER.info("action is not an edit action", extra={"action": action})
        return None, usage

    try:
        observation, done = environment.step(action)

        LOGGER.info(
            "action and observation after action",
            extra={"action": action, "observation": observation},
        )

        return environment, usage
    except Exception as e:
        LOGGER.info(
            "exception applying action", extra={"exception": e, "action": action}
        )
        return None, usage
