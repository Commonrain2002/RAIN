from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
import traceback
import typing as t
from serde import serde
from serde.json import from_json, to_json
import coq_serapy as c

from src.utils import set_example_name
from src.agent import Agent
from src.agent.zero_shot_tool import ZeroShotToolAgent, ZeroShotToolAgentConfig
from src.dataset import Example
from src.environment import Environment
from src.environment.actions import EditAction
from src.environment.config import EnvironmentConfig
from src.llm.gpt import OpenaiChatPromptConfig
from src.llm.usage import Usage
from src.proof_script import read_tactics, Tactic, process_braces
from src.coq_serapy_util import (
    proof_context_to_str,
    proof_context_eq,
    CoqError,
    debug_proof_context_to_str,
)
from .utils import LOGGER


@serde
@dataclass(frozen=True)
class Attempt:
    tactics: str
    prefix_without_errors: str
    success: bool
    usage: Usage
    debug_preceding_proof_state: str


@serde
@dataclass
class RegenerateFromFailurePoint:
    state_file: Path
    example: Example

    max_num_attempts: int = 20
    try_hammer: bool = True

    attempts: t.List[Attempt] = field(default_factory=list)

    debug_proof: t.Optional[str] = None
    debug_success: bool = False

    @classmethod
    def from_state_file(cls, state_file: Path) -> RegenerateFromFailurePoint:
        with open(state_file, "r") as f:
            ans = from_json(cls, f.read())
            ans.state_file = state_file
            return ans

    @property
    def actual_proof_prefix(self) -> str:
        return "" if self.example.proof_prefix is None else self.example.proof_prefix

    @property
    def proof_in_progress(self) -> str:
        """
        The prefix of the overall proof that has no errors.
        If this reaches Qed without errors, then this is the entire proof.
        """
        ans = ""
        for attempt in reversed(self.attempts):
            ans = attempt.prefix_without_errors + " " + ans
        return ans

    @property
    def proof(self) -> t.Optional[str]:
        return self.proof_in_progress if self.done else None

    @property
    def usage(self) -> Usage:
        ans = Usage(name="regenerate_from_failure_point")
        for attempt in self.attempts:
            ans.add_child(attempt.usage)
        return ans

    @property
    def done(self) -> bool:
        return self.attempts[-1].success if len(self.attempts) > 0 else False

    def make_agent_and_environment(
        self, prefix_str: str
    ) -> t.Tuple[Agent, Environment]:
        agent = ZeroShotToolAgent(
            self.example.proposition_command,
            config=ZeroShotToolAgentConfig(
                include_reasoning=True,
                chat_config=OpenaiChatPromptConfig(model="gpt-4", n=1),
            ),
        )

        environment = Environment(
            self.example.proposition_command,
            lemma_location=self.example.location,
            # include latest prefix without errors in the proof prefix
            proof_prefix=self.actual_proof_prefix
            + self.proof_in_progress
            + " "
            + prefix_str,
            config=EnvironmentConfig(
                done_condition="initial-goal-only",
                lemma_context="preceding-lemmas-only",
            ),
        )
        return agent, environment

    def task(self, _arg: t.Tuple[()], tqdm_func: t.Any, global_tqdm: t.Any):
        set_example_name(self.example.name)
        try:
            return self.run(tqdm_func, global_tqdm)
        except Exception as e:
            traceback.print_exc()
            traceback.print_stack()
            LOGGER.error(traceback.format_exc())
            LOGGER.error("\n\n".join(traceback.format_stack()))
            LOGGER.critical(
                "uncaught error while running regenerate from failure point",
                extra={
                    "example": self.example.name,
                    "error": str(e),
                    "traceback": traceback.format_exc(),
                },
            )
            return self.example, None, Usage(name="regenerate_from_failure_point")
        finally:
            Environment.teardown_all()

    def run(
        self, tqdm_func: t.Any, global_tqdm: t.Any
    ) -> t.Tuple[Example, t.Optional[str], Usage]:
        if self.done:
            return self.example, self.proof, self.usage

        with tqdm_func(
            total=self.max_num_attempts - len(self.attempts),
            desc=self.example.name[: len("total progress")],
            dynamic_ncols=True,
        ) as bar:
            while len(self.attempts) < self.max_num_attempts:
                self.write_state()
                prefix = self.get_prefix_for_bullets()
                prefix_str = " ".join(tactic.text for tactic in prefix)
                LOGGER.info(
                    f"prefix: {prefix_str}",
                    extra={
                        "proof_state": debug_proof_context_to_str(
                            self.get_latest_environment().proof_context
                        )
                    },
                )
                if self.try_hammer:
                    self.run_hammer(prefix)
                if not self.done:
                    self.run_agent(prefix)

                if self.done:
                    break

                bar.update()
                global_tqdm.update()

        self.write_state()
        return self.example, self.proof, self.usage

    def write_state(self) -> None:
        with open(self.state_file, "w") as f:
            f.write(to_json(self))

    def run_hammer(self, prefix: t.List[Tactic]) -> None:
        prefix_str = " ".join(tactic.text for tactic in prefix)
        _, environment = self.make_agent_and_environment(prefix_str)
        while not environment.done:
            _, environment = self.make_agent_and_environment(prefix_str)
            preceding_context = environment.proof_context
            preceding_context_str = proof_context_to_str(environment.proof_context)
            LOGGER.info("trying hammer", extra={"proof_state": preceding_context_str})
            try:
                _, done = environment.step(EditAction(new_code="hammer."))
            except Exception as e:
                LOGGER.error(
                    "error while running hammer",
                    extra={"error": str(e), "stacktrace": traceback.format_exc()},
                )
                break
            if proof_context_eq(preceding_context, environment.proof_context):
                LOGGER.info(
                    "hammer did not make progress",
                    extra={"proof_state": preceding_context_str},
                )
                break
            LOGGER.info(
                "successfully applied hammer",
                extra={"proof_state": preceding_context_str},
            )
            self.add_attempt(
                Attempt(
                    tactics=prefix_str + " " + "hammer.",
                    prefix_without_errors=prefix_str + " " + "hammer.",
                    success=True,
                    usage=Usage(name="hammer"),
                    debug_preceding_proof_state=preceding_context_str,
                )
            )

    def run_agent(self, prefix: t.List[Tactic]) -> None:
        prefix_str = " ".join(tactic.text for tactic in prefix)
        agent, environment = self.make_agent_and_environment(prefix_str)
        preceding_proof_state = proof_context_to_str(environment.proof_context)

        actions, usage = agent.act(environment.base_observation)
        code = actions[0].new_code

        tactics = read_tactics(code)
        tactics = [
            tactic for tactic in tactics if tactic.text not in ["Abort.", "Admitted."]
        ]
        working_tactics = []
        current_code = ""
        for tactic in tactics:
            _, done = environment.step(
                EditAction(new_code=current_code + " " + tactic.text)
            )
            if done:
                LOGGER.info(
                    f"successfully applied tactic: {tactic.text} (done)",
                    extra={"proof_state": preceding_proof_state},
                )
                working_tactics.append(tactic.text)
                break
            if environment.error is not None and (
                "Attempt to save an incomplete proof" not in environment.error.message
            ):
                LOGGER.info(
                    f"tactic: {tactic.text}, error: {environment.error}",
                    extra={"proof_state": preceding_proof_state},
                )
                break
            LOGGER.info(
                f"successfully applied tactic: {tactic.text}",
                extra={"proof_state": preceding_proof_state},
            )
            working_tactics.append(tactic.text)
            current_code = current_code + " " + tactic.text

        self.add_attempt(
            Attempt(
                tactics=prefix_str + " " + code,
                prefix_without_errors=prefix_str + " " + " ".join(working_tactics),
                success=environment.done,
                usage=usage,
                debug_preceding_proof_state=preceding_proof_state,
            )
        )

    def add_attempt(self, attempt: Attempt) -> None:
        self.attempts.append(attempt)
        self.debug_success = self.debug_success or attempt.success
        self.debug_proof = self.proof if self.debug_success else None

    def get_latest_environment(self) -> Environment:
        # :( this is a pretty expensive operation to keep running
        environment = Environment(
            self.example.proposition_command,
            lemma_location=self.example.location,
            # include latest prefix without errors in the proof prefix
            proof_prefix=self.actual_proof_prefix,
            config=EnvironmentConfig(
                done_condition="initial-goal-only",
                lemma_context="preceding-lemmas-only",
            ),
        )
        environment.step(EditAction(new_code=self.proof_in_progress))
        return environment

    def get_prefix_for_bullets(self) -> t.List[Tactic]:
        environment = self.get_latest_environment()
        proof_state = environment.proof_context
        if not has_empty_fg_goals(proof_state):
            return []

        tactics = read_tactics(self.proof_in_progress)
        prefix: t.List[Tactic] = []

        # close any open braces
        # arbitrary max num iters. This should terminate well before we
        # run out of iterations
        for _ in range(10):
            try:
                process_braces(tactics + prefix)
                break
            except AssertionError as e:
                if "Mismatched braces" in str(e):
                    LOGGER.info(
                        "mismatched braces, closing",
                        extra={
                            "proof_state": debug_proof_context_to_str(
                                environment.proof_context
                            )
                        },
                    )
                    prefix.append(Tactic("}"))
                else:
                    raise e

        prefix_str = " ".join(tactic.text for tactic in prefix)
        environment.step(EditAction(new_code=self.proof_in_progress + " " + prefix_str))

        LOGGER.info(
            "no more mismatched braces",
            extra={
                "proof_state": debug_proof_context_to_str(environment.proof_context),
                "env_code": environment.editor.runnable_code,
            },
        )
        if not has_empty_fg_goals(environment.proof_context):
            LOGGER.info(
                "no more bullets to focus",
                extra={
                    "proof_state": debug_proof_context_to_str(
                        environment.proof_context
                    ),
                    "env_code": environment.editor.runnable_code,
                },
            )
            return prefix

        bullet_hierarchy: t.List[Tactic] = []
        for tactic in tactics:
            if tactic.is_bullet and not any(
                bullet.text == tactic.text for bullet in bullet_hierarchy
            ):
                bullet_hierarchy.append(tactic)

        LOGGER.info(
            f"bullet hierarchy: {' '.join(tactic.text for tactic in bullet_hierarchy)}"
        )

        for bullet in reversed(bullet_hierarchy):
            coq = environment.coq
            coq.run_code(environment.editor.runnable_code_without_qed)
            LOGGER.info(
                f"trying to focus next goal with bullet {bullet.text}",
                extra={
                    "proof_state": debug_proof_context_to_str(
                        environment.proof_context
                    ),
                    "coq_proof_state": debug_proof_context_to_str(
                        coq.coq.proof_context
                    ),
                },
            )
            result = bullet.run(coq)
            if isinstance(result, CoqError):
                LOGGER.info(
                    f"bullet {bullet.text} failed",
                    extra={
                        "proof_state": proof_context_to_str(environment.proof_context)
                    },
                )
                continue

            LOGGER.info(
                f"bullet {bullet.text} succeeded",
                extra={"proof_state": proof_context_to_str(environment.proof_context)},
            )
            coq.revert_command()
            prefix.append(bullet)
            break

        return prefix


def has_empty_fg_goals(proof_state: t.Optional[c.contexts.ProofContext]) -> bool:
    return (
        proof_state is not None
        and len(proof_state.fg_goals) == 0
        and len(proof_state.all_goals) > 0
    )
