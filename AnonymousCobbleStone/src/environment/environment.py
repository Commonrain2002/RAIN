from functools import lru_cache, reduce
import traceback
from typing import (
    Literal,
    Optional,
    Tuple,
    List,
)
import typing as t
import coq_serapy as c
import re
from weakref import WeakSet

from src.format_prompt import (
    format_current_code,
    format_definitions,
    format_error,
    format_lemmas,
    format_preceding_lines,
    format_proof_state,
    format_proposition,
    format_global_error_user_message,
    num_gpt4_tokens,
)

from src.utils import get_logger
from src.coq_serapy_util import (
    Coq,
    CoqResult,
    CoqError,
    is_initial_goal_proven,
    normalize_whitespace,
    parse_identifiers_in_definition,
    proof_context_to_str,
    Definition,
    LemmaLocation,
)
from src.environment.actions import Action, DefinitionsAction, SearchAction
from src.environment.editor import TacticEditor
from src.environment.config import EnvironmentConfig
from src.config import CONFIG


LOGGER = get_logger("environment")

"""
This file represents the environment, which generates user messages
for the LLM to interact with
"""


PropositionType = Literal["Theorem", "Lemma", "Example"]

Observation = str
Done = bool

Identifier = str
CheckResult = str
PrintResult = str


class Environment:

    instances = WeakSet()

    proposition_command: str

    # code state
    editor: TacticEditor
    preamble: str
    has_run_preamble: bool = False

    # coq state
    coq: Coq
    preceding_file_contents: t.Optional[str]
    lemmas: t.Set[str]
    definitions: t.Dict[
        Identifier, t.Tuple[Optional[PrintResult], t.Optional[CheckResult]]
    ]
    tactic_definitions: t.List[str]
    initial_goal: str
    initial_proof_context: c.contexts.ProofContext

    config: EnvironmentConfig

    MAX_OBSERVATION_TOKENS = CONFIG.MAX_OBSERVATION_TOKENS

    @property
    def base_observation(self) -> Observation:
        try:
            result = self.run_code(self.runnable_code)

            lemmas = self.lemma_list
            definitions = self.definitions_list

            if (
                isinstance(result, CoqError)
                and self.editor.observation_code.strip() != ""
            ):
                error = (
                    result.token,
                    self.editor.runnable_line_number_to_observation_line_number(
                        result.line_number
                    ),
                    result.message,
                )
                ans = "The section of code that caused the error is delimited with the <ERROR> and </ERROR> tags.\n These tags are not part of the code, they just indicate where the error is. Make sure you do not include them in any new code you emit.\n\n"
                context = result.context
            else:
                error = None
                ans = ""
                context = (
                    result
                    if isinstance(result, c.contexts.ProofContext)
                    else result.context
                )

            if context is None:
                raise Exception(
                    "observing a none context. this means we're not inside a proof."
                )

            ans += format_proposition(self.initial_goal)
            ans += format_current_code(self.observation_code, error)
            ans += format_proof_state(proof_context_to_str(context), error)
            if error is not None:
                ans += format_error(error)

            num_tokens = num_gpt4_tokens(ans)
            token_budget = Environment.MAX_OBSERVATION_TOKENS - num_tokens

            if definitions is not None:
                ans += format_definitions(
                    definitions, self.tactic_definitions, token_budget
                )

            num_tokens = num_gpt4_tokens(ans)
            token_budget = Environment.MAX_OBSERVATION_TOKENS - num_tokens

            try:
                if self.config.lemma_context == "preceding-lines":
                    assert self.preceding_file_contents is not None
                    ans += format_preceding_lines(
                        self.preceding_file_contents, token_budget
                    )
                elif self.config.lemma_context != "none":
                    ans += format_lemmas(lemmas, token_budget)
            except ValueError as e:
                if str(e) != "Header too long to fit in token budget":
                    raise e

            return ans
        except Exception as e:
            LOGGER.error(
                f"Environment: Unexpected error while running code: {e}",
                extra={
                    "code": self.observation_code,
                    "error": e,
                    "traceback": traceback.format_exc(),
                },
            )
            return format_global_error_user_message(
                self.initial_goal,
                self.observation_code,
                str(e),
            )

    def step(self, action: Action) -> Tuple[Observation, Done]:
        extra_section: Optional[str] = None

        if action.type == "EDIT" or action.type == "APPEND" or action.type == "REPLACE":
            self.editor.step(action)
        elif action.type == "DEFINITIONS":
            definitions_looked_up = self.__get_definitions_section(action)
        elif action.type == "SEARCH":
            lemmas_looked_up = self.__get_search_section(action)
        else:
            raise Exception(f"unknown action type {action.type}")

        observation = self.base_observation
        if extra_section is not None:
            observation += "\n" + extra_section

        # roll back any statements that were executed as part of the observation
        # this may also be called in the next run, but reset should be idempotent
        self.coq.reset()

        return observation, self.done

    NUM_RETRIES = 3

    def step_retrying_on_uncaught_error(
        self, action: Action, num_retries=NUM_RETRIES
    ) -> Tuple[Observation, Done, "Environment"]:
        """
        sometimes, we get coq_serapy into a bad state over the course
        of a rollout.
        This method tries to mitigate issues with coq_serapy by creating
        a fresh environment and retrying the action on error.
        It may return an environment different from the one it was called on.
        """
        environment: "Environment" = self
        exception: Optional[Exception] = None
        observation: Optional[Observation] = None
        done: Optional[Done] = None
        for i in range(num_retries):
            # clone before stepping, so that we can reset
            # to the state before the step
            cloned_environment = environment.clone()
            try:
                observation, done = environment.step(action)
                break
            except Exception as e:
                exception = e
                LOGGER.error(
                    f"Environment: Unexpected error while running code, retrying: {e}",
                    extra={
                        "code": self.runnable_code,
                        "error": exception,
                        "traceback": traceback.format_exc(),
                        "try_number": i + 1,
                    },
                )
                environment = cloned_environment

        if exception is not None:
            raise Exception(
                f"Environment: exception thrown after {num_retries} retries."
            ) from exception

        if observation is None or done is None:
            raise Exception(
                f"Environment: observation is None after {num_retries} retries."
            )

        return observation, done, environment

    # region SETUP AND TEARDOWN

    def __init__(
        self,
        proposition_command: str,
        lemma_location: Optional[LemmaLocation] = None,
        proof_prefix: Optional[str] = None,
        config: t.Optional[EnvironmentConfig] = None,
    ) -> None:
        Environment.instances.add(self)

        if config is None:
            config = EnvironmentConfig()
        self.config = config

        self.proposition_command = normalize_whitespace(proposition_command)

        self.preamble = "\n".join(
            [
                # don't give search results from the standard library
                'Add Search Blacklist "Coq.".',
                "",
                "Require Import Lia.",
                "Require Import Coq.Arith.Gt.",
                "",
                "From Hammer Require Import Hammer.",
                "From Hammer Require Import Tactics.",
                "Create HintDb map.",
                "",
            ]
        )

        self.editor = TacticEditor(proposition_command, proof_prefix)

        self.coq = Coq(lemma_location=lemma_location, proposition_command=proposition_command)

        # sets the initial goal after executing the prefix string
        assert self.proof_context is not None, "proof_context is None"
        assert self.proof_context.fg_goals is not None, "fg_goals is None"
        assert len(self.proof_context.fg_goals) > 0, "fg_goals is empty"
        # doing this because verdi-raft-RefinedLogMatchingLemmasProof.v-entries_contiguous_nw_invariant doesn't focus the first goal when we use a bullet
        if len(self.proof_context.fg_goals) > 1:
            LOGGER.warning(
                f"there are {len(self.proof_context.fg_goals)} goals, expected 1. Will proceed, focusing on the first goal."
            )
        self.initial_goal = self.proof_context.fg_goals[0].goal
        self.initial_proof_context = self.proof_context

        self.preceding_file_contents = (
            None if lemma_location is None else lemma_location.preceding_contents(self.proposition_command)
        )
        self.lemmas = set()
        self.definitions = {}

        self.__get_definitions_in_lemma()
        self.__get_preceding_lemmas()

        # self.tactic_definitions = self.coq.ltac_definitions()
        # turning off tactic definitions for now
        # picking tactics is a premise selection problem
        self.tactic_definitions = []

    @classmethod
    def teardown_all(cls):
        LOGGER.debug(
            "tearing down all environments",
            extra={"num_environments": len(Environment.instances)},
        )
        for instance in cls.instances:
            try:
                instance.teardown()
            except:
                # usually, these are "pid not found" errors
                pass

    def __del__(self):
        self.teardown()

    def teardown(self):
        LOGGER.debug("tearing down environment")
        if hasattr(self, "coq"):
            self.coq.teardown()

    def clone(self) -> "Environment":
        ans = Environment(
            self.proposition_command,
            self.coq.lemma_location,
            config=self.config,
        )
        ans.editor = self.editor.clone()
        ans.lemmas = self.lemmas.copy()
        ans.definitions = {
            identifier: (print, check)
            for identifier, (print, check) in self.definitions.items()
        }
        return ans

    # endregion SETUP AND TEARDOWN

    # region CODE AND EXECUTION

    @property
    def observation_code(self) -> str:
        return self.editor.observation_code

    @property
    def runnable_code(self) -> str:
        return self.editor.runnable_code

    def run_code(self, code: str) -> CoqResult:
        if not self.has_run_preamble:
            self.coq.run_preamble(self.preamble)
            self.has_run_preamble = True
        return self.coq.run_code(code)

    @lru_cache
    def __coq_result(self, code: str) -> CoqResult:
        return self.run_code(code)

    @property
    def proof_context(self) -> t.Optional[c.contexts.ProofContext]:
        result = self.__coq_result(self.runnable_code)
        return result if isinstance(result, c.contexts.ProofContext) else result.context

    @property
    def error(self) -> t.Optional[CoqError]:
        result = self.__coq_result(self.runnable_code)
        return result if isinstance(result, CoqError) else None

    @property
    def done(self) -> Done:
        if self.config.done_condition == "initial-goal-only":
            return self.is_initial_goal_proven
        else:  # done_condition == "initial-goal-or-decomposition"
            return self.is_initial_goal_proven or self.at_goal_decomposition

    @property
    def is_initial_goal_proven(self) -> bool:
        return is_initial_goal_proven(
            self.initial_proof_context, self.proof_context, self.error
        )

    @property
    def at_goal_decomposition(self) -> bool:
        return self.compute_goal_decomposition() is not None

    def compute_goal_decomposition(
        self,
    ) -> Optional[Tuple[str, List[c.Obligation]]]:  # type: ignore
        if self.proof_context is None:
            return None

        return self.editor.compute_goal_decomposition(
            self.initial_proof_context, self.coq
        )

    # endregion CODE AND EXECUTION

    # region DEFINITIONS AND LEMMAS

    def clear_lemmas(self):
        self.lemmas = set()

    def add_lemmas(self, lemmas: List[str]):
        self.lemmas = self.lemmas.union(normalize_whitespace(lemma) for lemma in lemmas)
        self.lemmas = set(
            filter(
                lambda lemma: not lemma.startswith("Listing only ")
                and not lemma.startswith("In previous versions of Coq, ")
                and not lemma.startswith('(use "About"'),
                self.lemmas,
            )
        )
        self.lemmas = set(
            filter(
                lambda lemma: get_lemma_identifier(lemma)
                not in self.definitions.keys(),
                self.lemmas,
            )
        )

    @property
    def lemma_list(self) -> List[str]:
        return sorted(list(self.lemmas))

    @property
    def definitions_list(self) -> List[str]:
        return [
            definition
            for definition_item in sorted(self.definitions.items(), key=lambda x: x[0])
            for definition in definition_item[1]
            if definition is not None
        ]

    def __get_definitions_section(self, action: DefinitionsAction) -> List[str]:
        definitions = [
            self.__get_definitions(identifier) for identifier in action.identifiers
        ]
        definitions = [
            definition
            for definition_tuple in definitions
            for definition in definition_tuple
            if definition is not None
        ]
        return definitions

    def __get_definitions(self, identifier: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            print = self.coq.print(identifier)
            check = self.coq.check(identifier) if print is None else None

            hypotheses = (
                Definition.parse_hypotheses(
                    list(self.proof_context.fg_goals[0].hypotheses)
                )
                if self.proof_context is not None
                else []
            )

            print_def = Definition.parse(print) if print is not None else None
            check_def = Definition.parse(check) if check is not None else None

            if print_def is not None and any(
                Definition.matches(hypotheses, print_def) for hypotheses in hypotheses
            ):
                print = None

            if check_def is not None and any(
                Definition.matches(hypotheses, check_def) for hypotheses in hypotheses
            ):
                check = None

            if identifier not in self.definitions:
                self.definitions[identifier] = (print, check)

            return print, check
        except Exception as e:
            if identifier not in self.definitions:
                self.definitions[identifier] = (None, None)
            LOGGER.error(
                f"Environment: Unexpected error while getting definitions for {identifier}: {e}",
                extra={
                    "code": self.runnable_code,
                    "identifier": identifier,
                    "error": e,
                    "error_class": f"{type(e).__name__}",
                    "traceback": traceback.format_exc(),
                },
            )
            return None, None

    def __get_search_section(self, action: SearchAction) -> List[str]:
        # consider filtering out non-lemmas
        results = list(
            set(
                {
                    result.strip()
                    for identifier in action.identifiers
                    if " " not in identifier
                    for result in self.coq.search(identifier)
                }
            )
        )
        results.sort()

        self.lemmas = self.lemmas.union(
            normalize_whitespace(result) for result in results
        )

        return results

    def __get_preceding_lemmas(self):
        """
        looks up lemmas that precede the current lemma in the file
        """
        if self.coq.lemma_location is None:
            return

        preceding_lemmas = self.coq.lemma_location.preceding_lemmas(self.proposition_command)
        self.add_lemmas(preceding_lemmas)

    def __get_definitions_in_lemma(self):
        """
        looks up definitions for identifiers defined in the lemma
        """

        if self.proof_context is None:
            return

        identifiers = parse_identifiers_in_definition(
            self.proof_context.fg_goals[0].goal
            + "\n"
            + "\n".join(self.proof_context.fg_goals[0].hypotheses)
        )

        defined_identifiers = set(self.definitions.keys())
        identifiers_to_define = identifiers.difference(defined_identifiers)

        num_iters = 1
        while len(identifiers_to_define) > 0 and num_iters > 0:
            definitions = []
            for identifier in identifiers_to_define:
                # skip standard library definitions
                location = self.coq.locate(identifier)
                if location is None or "Coq." in location:
                    continue

                _print, check = self.__get_definitions(identifier)
                if _print is not None:
                    definitions.append(_print)
                if check is not None:
                    definitions.append(check)

            identifiers = reduce(
                lambda agg, definition: agg.union(
                    parse_identifiers_in_definition(definition)
                ),
                definitions,
                set(),
            )
            defined_identifiers = set(self.definitions.keys())
            identifiers_to_define = identifiers.difference(defined_identifiers)

            num_iters -= 1

    # endregion DEFINITIONS AND LEMMAS


# Lemma Comp_mon: monotonic TX TY (Comp G F). -> Comp_mon
# List.incl_tran: forall (A : Type) (l m n : list A) (_ : List.incl l m) (_ : List.incl m n), List.incl l n -> List.incl_tran
LEMMA_IDENTIFIER_REGEX = r"^(?:(?:Lemma|Theorem|Example)\s+)?([A-Za-z0-9_\.']+)\s*:"


def get_lemma_identifier(lemma: str) -> t.Optional[str]:
    match = re.match(LEMMA_IDENTIFIER_REGEX, lemma)
    if match is None:
        return None
    return match.group(1)
