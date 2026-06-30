from typing import Tuple, TypeVar, Generic, List, Optional
from abc import ABC, abstractmethod
import coq_serapy as c

from src.coq_serapy_util import (
    kill_non_tactic_commands,
    Coq,
    CoqError,
    non_fg_goals_match,
)
from src.environment.actions import CodeAction
from src.utils import get_logger

LOGGER = get_logger("environment.editor")


A = TypeVar("A")


class Editor(ABC, Generic[A]):
    """
    This class represents a Coq code snippet that the LLM can edit.
    It constrains the ways in which the LLM can edit the code.
    """

    proposition_command: str

    def __init__(
        self,
        proposition_command: str,
    ) -> None:
        self.proposition_command = proposition_command

    @property
    @abstractmethod
    def observation_code(self) -> str:
        """
        returns the code to be used for observation
        """
        pass

    @property
    @abstractmethod
    def runnable_code(self) -> str:
        """
        returns the code
        """
        pass

    @abstractmethod
    def runnable_line_number_to_observation_line_number(
        self, runnable_line_number: int
    ) -> int:
        """
        returns the line number in the observation code that corresponds to the given line number in the runnable code
        """
        pass

    @abstractmethod
    def step(self, action: A) -> str:
        """
        takes an action and returns the new code
        """
        pass

    @abstractmethod
    def clone(self) -> "Editor[A]":
        """
        returns a copy of the editor
        """
        pass


class TacticEditor(Editor[CodeAction]):
    """
    This editor only allows editing code in the proof section.
    It supports the EDIT, APPEND, and REPLACE actions.
    """

    proof_prefix: str
    tactics: str

    def __init__(
        self,
        proposition_command: str,
        proof_prefix: Optional[str] = None,
    ) -> None:
        super().__init__(proposition_command)
        self.proof_prefix = "" if proof_prefix is None else proof_prefix
        self.tactics = ""

    @property
    def observation_code(self) -> str:
        return self.tactics

    @property
    def runnable_code_without_qed(self) -> str:
        return "\n".join(
            [
                self.proposition_command,
                "Proof.",
            ]
            + ([] if self.proof_prefix == "" else [self.proof_prefix])
            + ([] if self.tactics == "" else [self.tactics])
        )

    @property
    def runnable_code(self) -> str:
        return "\n".join(
            [
                self.proposition_command,
                "Proof.",
            ]
            + ([] if self.proof_prefix == "" else [self.proof_prefix])
            + ([] if self.tactics == "" else [self.tactics])
            + ["Qed."]
        )

    def runnable_line_number_to_observation_line_number(
        self, runnable_line_number: int
    ) -> int:
        """
        returns the line number in the observation code that corresponds to the given line number in the runnable code
        """
        num_lines_in_proposition_command = len(self.proposition_command.split("\n"))
        num_lines_in_proof_command = 1  # `Proof.` is on a line of its own
        num_lines_in_proof_prefix = (
            len(self.proof_prefix.split("\n")) if self.proof_prefix.strip() != "" else 0
        )

        return (
            runnable_line_number
            - num_lines_in_proposition_command
            - num_lines_in_proof_command
            - num_lines_in_proof_prefix
        )

    def step(self, action: CodeAction) -> str:
        if action.type == "EDIT":
            tactics = action.new_code
        elif action.type == "APPEND":
            tactics = self.tactics + "\n" + action.tactics_to_append
        elif action.type == "REPLACE":
            start_index = action.start_index if action.start_index is not None else 0
            end_index = (
                action.end_index if action.end_index is not None else len(self.tactics)
            )
            tactics = (
                self.tactics[:start_index]
                + action.new_tactics
                + self.tactics[end_index:]
            )
        else:
            raise Exception(f"unknown action type {action.type}")

        tactics = kill_non_tactic_commands(tactics)
        self.tactics = tactics

        return self.runnable_code

    def clone(self) -> "TacticEditor":
        ans = TacticEditor(self.proposition_command)
        ans.tactics = self.tactics
        return ans

    # TODO: return a GoalDecomposition dataclass
    def compute_goal_decomposition(
        self, initial_proof_context: c.ProofContext, coq: Coq  # type: ignore
    ) -> Optional[Tuple[str, List[c.Obligation]]]:  # type: ignore
        """
        Steps through each prefix of tactics and checks if it is a valid goal decomposition, returning the first prefix that works as a goal decomposition.

        Returns a pair of the prefix and the goal decomposition that results from running the prefix, or None if no valid goal decomposition is found.
        """
        proof_prefix_commands = c.read_commands(self.proof_prefix)  # type: ignore

        prefix: List[str] = []
        seen_proof_start = False
        seen_proof_prefix = len(proof_prefix_commands) == 0

        run_iterator = coq.run_code_iter(self.runnable_code)
        for command, line_number, result in run_iterator:
            # don't consider any commands that come before the proof starts
            if not seen_proof_start and command.strip() == "Proof.":
                seen_proof_start = True
                continue
            if not seen_proof_start:
                continue

            # don't consider any commands in the proof /prefix
            if (
                not seen_proof_prefix
                and command.strip() == proof_prefix_commands[0].strip()
            ):
                proof_prefix_commands.pop(0)
                seen_proof_prefix = len(proof_prefix_commands) == 0
                continue
            if not seen_proof_prefix:
                continue

            prefix = prefix + [command]

            proof_context = result.context if isinstance(result, CoqError) else result
            error = result if isinstance(result, CoqError) else None

            if proof_context is not None and self.__is_valid_goal_decomposition(
                "\n".join(prefix), initial_proof_context, proof_context, error
            ):
                return ("\n".join(prefix), proof_context.fg_goals)

        return None

    def __is_valid_goal_decomposition(
        self,
        tactics_prefix: str,
        initial_proof_context: c.ProofContext,  # type: ignore
        proof_context: c.ProofContext,  # type: ignore
        error: Optional[CoqError],
    ) -> bool:
        """
        returns True if the `tactics_prefix` is a valid goal decomposition
        i.e. that it executes without error, is indeed a prefix of self.tactics, and that it results in multiple non-fg goals
        """
        if (
            len(proof_context.fg_goals) <= 1
            or not non_fg_goals_match(initial_proof_context, proof_context)
            or not (error is None or error.is_attempt_to_save_incomplete_proof)
            or tactics_include_admit_or_abort(tactics_prefix)
        ):
            LOGGER.debug(
                f"tactics_prefix `{tactics_prefix}` is not a goal decomposition",
                extra={
                    "tactics_prefix": tactics_prefix,
                    "num_fg_goals": len(proof_context.fg_goals),
                    "non_fg_goals_match": non_fg_goals_match(
                        initial_proof_context, proof_context
                    ),
                    "initial_goals": {
                        "fg": len(initial_proof_context.fg_goals),
                        "bg": len(initial_proof_context.bg_goals),
                        "shelved": len(initial_proof_context.shelved_goals),
                        "given_up": len(initial_proof_context.given_up_goals),
                    },
                    "goals": {
                        "fg": len(proof_context.fg_goals),
                        "bg": len(proof_context.bg_goals),
                        "shelved": len(proof_context.shelved_goals),
                        "given_up": len(proof_context.given_up_goals),
                    },
                    "error": error,
                    "tactics_include_admit_or_abort": tactics_include_admit_or_abort(
                        tactics_prefix
                    ),
                },
            )
            return False

        # verify that the tactics prefix is a prefix of self.tactics
        my_tactic_commands = c.read_commands(self.tactics)  # type: ignore
        tactics_prefix_commands = c.read_commands(tactics_prefix)  # type: ignore

        if len(my_tactic_commands) < len(tactics_prefix_commands):
            return False

        for i in range(len(tactics_prefix_commands)):
            if my_tactic_commands[i].strip() != tactics_prefix_commands[i].strip():
                return False

        return True


def tactics_include_admit_or_abort(tactics: str) -> bool:
    commands = c.coq_util.read_commands(tactics)
    return any(
        command.strip() == "Admitted."
        or command.strip() == "Abort."
        or command.strip() == "Admit."
        or command.strip() == "Abort"
        or command.strip() == "admit."
        or command.strip() == "abort."
        for command in commands
    )
