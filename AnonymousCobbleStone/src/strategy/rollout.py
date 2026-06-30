"""
the simplest way to use an LLM agent:
the agent takes an action, 
which goes into the environment,
which returns an observation,
which goes into the agent,
and so on
"""

from dataclasses import dataclass
import traceback
from tqdm import tqdm
import typing as t

from src.coq_serapy_util import obligation_summary
from src.dataset import Example
from src.utils import get_logger
from src.strategy.types_renamed import MakeAgentAndEnvironment, Strategy
from src.environment import Environment
from src.llm import Usage

LOGGER = get_logger("strategy.rollout")


@dataclass
class RolloutConfig:
    max_num_actions: int = 15
    num_attempts: int = 3

    @property
    def bar_length(self):
        return self.max_num_actions * self.num_attempts


def rollout(
    example: Example,
    make_agent_and_environment: MakeAgentAndEnvironment,
    config: t.Optional[RolloutConfig] = None,
    show_bar=False,
) -> t.Tuple[t.Optional[Environment], Usage]:
    """try to solve the lemma using a rollout"""

    config = config or RolloutConfig()

    LOGGER.info(
        f"trying to solve {example.proposition_command} using a rollout",
        extra={"example": example},
    )

    bar = (
        tqdm(
            total=config.bar_length,
            desc=example.proposition_command[0:10],
            dynamic_ncols=True,
        )
        if show_bar
        else None
    )

    usage = Usage(name="rollout")

    try:
        for attempt_number in range(config.num_attempts):
            LOGGER.info(
                f"attempt {attempt_number + 1}", extra={"attempt": attempt_number + 1}
            )
            try:
                result = rollout_attempt(
                    example, make_agent_and_environment, config, usage, bar
                )

                LOGGER.debug("usage", extra={"usage": usage})

                if result:
                    return result, usage
                else:
                    continue
            except Exception as e:
                LOGGER.error(
                    f"error during attempt {attempt_number + 1}. trying again",
                    extra={
                        "attempt": attempt_number + 1,
                        "error": e,
                        "traceback": traceback.format_exc(),
                    },
                )
                continue
        return None, usage
    finally:
        if bar is not None:
            bar.close()


__TYPE_CHECK: Strategy[RolloutConfig] = rollout


def rollout_attempt(
    example: Example,
    make_agent_and_environment: MakeAgentAndEnvironment,
    config: RolloutConfig,
    usage: Usage,
    bar: t.Optional[tqdm],
) -> t.Optional[Environment]:
    agent, environment = make_agent_and_environment(
        example.proposition_command, example.hint, example.location, None
    )

    num_actions = 0

    observation = environment.base_observation
    LOGGER.info(
        "initial observation",
        extra={
            "observation": observation,
            "obligation": (
                obligation_summary(environment.proof_context.fg_goals[0])
                if environment.proof_context
                else None
            ),
            "proof": environment.observation_code,
        },
    )

    done = False
    while num_actions < config.max_num_actions and not done:
        actions, action_usage = agent.act(observation)
        action = actions[0]

        usage.add_child(action_usage)

        LOGGER.info(
            f"action {num_actions + 1}",
            extra={"action number": num_actions + 1, "action": action},
        )
        observation, done = environment.step(action)
        LOGGER.info(
            f"observation after action {num_actions + 1}",
            extra={
                "action": action,
                "observation": observation,
                "done": done,
                "action number": num_actions + 1,
                "obligation": (
                    obligation_summary(environment.proof_context.fg_goals[0])
                    if environment.proof_context
                    and len(environment.proof_context.fg_goals) >= 1
                    else None
                ),
                "proof": environment.observation_code,
                "usage": action_usage,
            },
        )
        if done:
            LOGGER.info("solved the example using a rollout")
            return environment

        num_actions += 1
        if bar:
            bar.update(1)
    return None
