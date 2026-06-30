from dataclasses import dataclass, field
import itertools
from re import Match, Pattern
import re
import traceback
from typing import Dict, Optional, Set, Tuple, Union, List
import coq_serapy as c
import subprocess
import os
import sexpdata
from contextlib import contextmanager
from pathlib import Path
import typing as t
from serde import serde
from src.utils import get_logger, ensure_not_none
from src.config import CONFIG

from .feedback import FeedbackMessage
from .default_ltacs import DEFAULT_LTACS

"""
Wrappers around coq_serapy to make it easier to use
"""

LOGGER = get_logger("coq_serapy_util")
OPAM_SWITCH_LOGGER = get_logger("opam-switch")

ENDING_COMMANDS = ["Qed.", "Admitted.", "Abort."]


CoqVersion = t.Literal["8.10", "8.11", "8.12", "8.13", "8.18"]
COQ_VERSION = ["8.10", "8.11", "8.12", "8.13", "8.18"]

# Coq 8.18 removed the Add LoadPath / Add Rec LoadPath vernacular commands.
COQ_VERSIONS_WITHOUT_LOADPATH_VERNAC: t.FrozenSet[CoqVersion] = frozenset({"8.18"})


def sertop_load_path_args_from_coqproject(root_dir: str) -> List[str]:
    """
    Parse _CoqProject (or Make) into sertop CLI flags.
    Used for Coq versions that no longer accept Add LoadPath in SerAPI init.
    """
    includes_string = ""
    root = Path(root_dir)
    for name in ("_CoqProject", "Make"):
        try:
            includes_string = (root / name).read_text()
            break
        except FileNotFoundError:
            continue

    if not includes_string:
        return []

    q_pattern = r"-Q\s*(\S+)\s+(\S+)\s*"
    r_pattern = r"-R\s*(\S+)\s+(\S+)\s*"
    i_pattern = r"-I\s*(\S+)\s*"
    args: List[str] = []
    for includematch in re.finditer(
        rf"({q_pattern})|({r_pattern})|({i_pattern})", includes_string
    ):
        q_match = re.fullmatch(q_pattern, includematch.group(0))
        if q_match:
            physical, logical = q_match.group(1), q_match.group(2)
            if logical == '""':
                args.extend(["-Q", f"{physical},"])
            else:
                args.extend(["-Q", f"{physical},{logical}"])
            continue
        r_match = re.fullmatch(r_pattern, includematch.group(0))
        if r_match:
            args.extend(["-R", f"{r_match.group(1)},{r_match.group(2)}"])
            continue
        i_match = re.fullmatch(i_pattern, includematch.group(0))
        if i_match:
            args.extend(["-I", i_match.group(1)])
    return args


@contextmanager
def _skip_serapy_enter_directory_loadpath():
    """
    coq_serapy enterDirectory emits Add LoadPath, which Coq 8.18 rejects.
    Load paths must be passed on the sertop command line instead.
    """
    cls = c.serapi_backend.CoqSeraPyInstance
    original = cls.enterDirectory

    def enter_directory_noop(self, root_dir: str) -> None:
        del self, root_dir

    cls.enterDirectory = enter_directory_noop  # type: ignore[method-assign]
    try:
        yield
    finally:
        cls.enterDirectory = original


section_regex = re.compile(r"Section\s+(\w+)")


def get_section_name_from_command(command: str) -> t.Optional[str]:
    section_match = section_regex.match(command)
    if section_match:
        return section_match.group(1)
    return None


@serde
@dataclass(frozen=True)
class LemmaLocation:
    project_name: str
    file_name: str
    lemma_name: str
    section_names: List[str] = field(default_factory=list)
    coq_version: CoqVersion = "8.12"

    def __hash__(self):
        return hash(
            (
                self.project_name,
                self.file_name,
                self.lemma_name,
                tuple(self.section_names),
                self.coq_version,
            )
        )

    @property
    def prelude(self) -> str:
        """the directory of the project that we want access to.
        we are running in a new module that lives inside this project"""
        path = Path(CONFIG.ROOT_DIR) / CONFIG.PROJECTS_ROOT / self.project_name
        return str(path.resolve())

    @property
    def module_name(self) -> str:
        return self.file_name.split("/")[-1].split(".")[0]

    @property
    def path(self) -> Path:
        return (
            Path(CONFIG.ROOT_DIR)
            / CONFIG.PROJECTS_ROOT
            / self.project_name
            / self.file_name
        )

    def preceding_lemmas(self, proposition_command: Optional[str] = None) -> List[str]:
        path = self.path
        commands = self.file_commands(proposition_command)
        # TODO: i'm currently assuming all lemmas are proven. filter out aborts and admits
        return [
            lemma
            for _, lemma in c.coq_util.lemmas_in_file(str(path.resolve()), commands)
        ]

    def __commands_before_lemma(self, proposition_command: Optional[str] = None):
        path = self.path
        with open(path, "r") as file:
            file_contents: str = file.read()
            commands_and_line_numbers = read_commands(file_contents)

        LOGGER.info(f"got {len(commands_and_line_numbers)} commands from {path}")
        LOGGER.info(f"section names: {self.section_names}")
        LOGGER.info(f"proposition command: {proposition_command}")

        seen_section_names = []
        seen_lemma_name = False

        while (
            len(seen_section_names) < len(self.section_names)
        ) or not seen_lemma_name:
            command, line_number = commands_and_line_numbers.pop(0)
            orig_command = command
            command = c.coq_util.kill_comments(command).strip()

            lemma_name = None
            try:
                lemma_name = c.coq_util.lemma_name_from_statement(command)
                LOGGER.info(
                    f"lemma name: {lemma_name}, self.lemma_name: {self.lemma_name}, \norig_command:\n{normalize_whitespace(orig_command)}, \nproposition_command:\n{normalize_whitespace(proposition_command)}"
                )
            except Exception:
                pass

            # print(f"command: {json.dumps(orig_command)}")
            if lemma_name == self.lemma_name and (
                proposition_command is None
                or orig_command == proposition_command
                or normalize_whitespace(orig_command)
                == normalize_whitespace(proposition_command)
                or normalize_whitespace(kill_comments(orig_command))
                == normalize_whitespace(kill_comments(proposition_command))
            ):
                seen_lemma_name = True
                LOGGER.info(f"seen lemma name: {lemma_name}")
                # stop short of executing the lemma
                return command, line_number

            section_name = get_section_name_from_command(command)
            if (
                len(seen_section_names) > 0
                and section_name == self.section_names[len(seen_section_names) - 1]
            ):
                LOGGER.info(f"seen section name: {section_name}")
                seen_section_names.append(section_name)

            yield command, line_number

    def file_commands(self, proposition_command: Optional[str] = None) -> List[str]:
        ans: t.List[str] = []
        for command, _ in self.__commands_before_lemma(proposition_command):
            ans.append(command)
        return ans

    def lemma_line_number(self, proposition_command: Optional[str] = None) -> int:
        # the 2nd element of the return value of __commands_before_lemma is the line number
        try:
            gen = self.__commands_before_lemma(proposition_command)
            while True:
                next(gen)
        except StopIteration as e:
            return e.value[1]

    def preceding_contents(self, proposition_command: Optional[str] = None) -> str:
        # all file contents before lemma_line_number
        path = self.path
        with open(path, "r") as file:
            file_contents: str = file.read()
            lines = file_contents.split("\n")

        return "\n".join(lines[: self.lemma_line_number(proposition_command)])


NO_SUCH_GOAL_REGEX = re.compile(
    r"^No such goal. Focus next goal with bullet ([\-\+\*]+).$"
)
WRONG_BULLET_REGEX = re.compile(
    r"^\[Focus\] Wrong bullet (?:[\-\*\+]+): Expecting ([\-\*\+]+)\.$"
)
WRONG_BULLET_NOT_FINISHED_REGEX = re.compile(
    r"^\[Focus\] Wrong bullet (?:[\-\*\+]+): Current bullet (?:[\-\*'+]+) is not finished\.$"
)

ATTEMPT_TO_SAVE_INCOMPLETE_PROOF_REGEX = (
    r"^\s*\(in proof [A-Za-z_']+\): Attempt to save an incomplete proof[\s.]*$"
)
ATTEMPT_TO_SAVE_GIVEN_UP_REGEX = (
    r"^\s*\(in proof [A-Za-z_']+\): Attempt to save a proof with given up goals.[.\s]*$"
)


@dataclass(frozen=True)
class CoqError:
    message: str
    token: str
    line_number: int
    context: Optional[c.contexts.ProofContext] = None

    @property
    def is_bullet_error(self) -> bool:
        return self.expected_bullet is not None

    @property
    def expected_bullet(self) -> t.Optional[str]:
        match = NO_SUCH_GOAL_REGEX.match(self.normalized_message)
        if match is not None:
            return match.group(1)

        match = WRONG_BULLET_REGEX.match(self.normalized_message)
        if match is not None:
            return match.group(1)

        return None

    @property
    def normalized_message(self) -> str:
        return self.message.replace("\n", " ").strip()

    @property
    def normalized_token(self) -> str:
        return self.token.strip()

    @property
    def is_attempt_to_save_incomplete_proof(self) -> bool:
        return (
            re.match(ATTEMPT_TO_SAVE_INCOMPLETE_PROOF_REGEX, self.normalized_message)
            is not None
            or re.match(ATTEMPT_TO_SAVE_GIVEN_UP_REGEX, self.normalized_message)
            is not None
        ) and self.normalized_token == "Qed."

    @property
    def is_current_bullet_not_finished(self) -> bool:
        return (
            re.match(WRONG_BULLET_NOT_FINISHED_REGEX, self.normalized_message)
            is not None
        )


CoqResult = t.Union[c.contexts.ProofContext, CoqError]


class Coq:
    """
    This class wraps the coq_serapy context manager, and provides a more sane interface
    for interacting with it.
    """

    coq: c.coq_agent.CoqAgent
    lemma_location: Optional[LemmaLocation]
    proposition_command: Optional[str]
    num_statements_executed = 0

    # Yousef mentioned and issue that crops up every ~3000 `cancel_last`s
    # where we get a Coq Anomaly.
    # at that point, we should reset the environment and restart
    # not sure if this is to do with executing lots of coq code in parallel
    # or a normal part of execution
    num_cancel_lasts_executed = 0

    exited = False

    __notations_on = False

    def __init__(
        self,
        lemma_location: Optional[LemmaLocation] = None,
        proposition_command: Optional[str] = None,
    ) -> None:
        self.lemma_location = lemma_location
        self.proposition_command = proposition_command
        self.__setup_coq()

    @property
    def __coq_version(self) -> CoqVersion:
        return self.lemma_location.coq_version if self.lemma_location else "8.12"

    def __setup_coq(self):
        if self.lemma_location is None:
            prelude = "."
        else:
            prelude = self.lemma_location.prelude

        module_name = (
            self.lemma_location.module_name if self.lemma_location else "MyModule"
        )
        coq_version = self.__coq_version
        sertop_cmd: List[str] = ["sertop", "--implicit"]
        if coq_version in COQ_VERSIONS_WITHOUT_LOADPATH_VERNAC:
            sertop_cmd.extend(sertop_load_path_args_from_coqproject(prelude))
        with switch(coq_version) as _:
            # since coq_serapy spawns a subprocess, we only need the correct
            # environment variables when we spawn the subprocess, and can
            # reset them afterwards
            if coq_version in COQ_VERSIONS_WITHOUT_LOADPATH_VERNAC:
                with _skip_serapy_enter_directory_loadpath():
                    self.coq = c.SerapiInstance(sertop_cmd, module_name, prelude)
            else:
                self.coq = c.SerapiInstance(sertop_cmd, module_name, prelude)

        if self.lemma_location is None:
            return

        file_commands = self.lemma_location.file_commands(self.proposition_command)
        if file_commands is None:
            return

        for command in file_commands:
            LOGGER.debug('running file prefix command: "' + command + '"')
            self.coq.run_stmt(command)

    def teardown(self):
        if self.exited:
            return

        LOGGER.debug(
            "tearing down coq_serapy",
            extra={"pid": t.cast(t.Any, self.coq.backend)._proc.pid},
        )
        self.coq.backend.close()
        self.coq.kill()
        self.exited = True

    def __del__(self):
        self.teardown()

    def run_preamble(self, preamble: str) -> None:
        """
        Run the preamble, and throw away the result
        don't increment num_statements or num_cancel_lasts
        cancel lasts shouldn't revert the preamble
        """
        commands = code_commands(preamble)
        while len(commands) > 0:
            command, _ = commands.pop(0)
            LOGGER.debug('running command: "' + command + '"')
            self.coq.run_stmt(command)

    @property
    def notations_on(self) -> bool:
        return self.__notations_on

    @notations_on.setter
    def notations_on(self, on: bool):
        self.__notations_on = on
        if on:
            self.run_preamble("Set Printing Notations.")
        else:
            self.run_preamble("Unset Printing Notations.")

    def run_code(self, code: str) -> CoqResult:
        """
        Run the code as far as it will go, and return the last working context.
        If there are still goals at Qed, or Admitted, return None.

        Returns a CoqResult, which contains:
        - the last working context
        - the error message
        - the error command
        """

        run_iterator = self.run_code_iter(code)
        try:
            while True:
                result = next(run_iterator)
                if isinstance(result, CoqError):
                    return result
        except StopIteration as e:
            return e.value

    def run_code_iter(self, code: str):
        """
        Run the code as far as it will go, and return the last working context.
        If there are still goals at Qed, or Admitted, return None.

        At each step, yield a CoqResult, which contains:
        - the last working context
        - the error message
        - the error command
        """
        self.reset()

        commands = code_commands(code)
        context = self.coq.proof_context
        LOGGER.debug("context before running code: " + proof_context_to_str(context))

        while len(commands) > 0:
            (command, line_number) = commands.pop(0)

            # if comments in the command become an issue, consider doing this:
            # command = c.kill_comments(command).strip()

            # stop short of executing the ending command, so that
            # we can do further queries inside the proof
            if len(commands) == 0:
                if (
                    any(ending_command in command for ending_command in ENDING_COMMANDS)
                    and "Qed." not in command
                ):
                    LOGGER.debug("stopping short of ending command")
                    return context
                elif (
                    "Qed." in command
                    and context is not None
                    and len(context.all_goals) == 0
                ):
                    LOGGER.debug("stopping short of Qed")
                    return context

            LOGGER.debug(
                'running command: "' + command + '"',
                extra={
                    "context": proof_context_to_str(context),
                },
            )

            try:
                self.run_command(command)

                raw_feedbacks = t.cast(
                    c.serapi_backend.CoqSeraPyInstance, self.coq.backend
                ).feedbacks
                messages = [
                    FeedbackMessage.from_sexp_array(feedback)
                    for feedback in raw_feedbacks
                ]
                LOGGER.debug(
                    "got feedbacks",
                    extra={
                        "feedbacks": messages,
                    },
                )

                context = self.coq.proof_context
                LOGGER.debug(
                    'after running command "' + command + '"',
                    extra={
                        "command": command,
                        "context": proof_context_to_str(context),
                    },
                )
                yield (command, line_number, context)
            except c.coq_backend.CoqException as e:
                LOGGER.debug("Coq Exception: " + str(e))
                LOGGER.debug(
                    "num cancel lasts executed: " + str(self.num_cancel_lasts_executed)
                )
                yield (
                    command,
                    line_number,
                    CoqError(str(e), command, line_number, context),
                )
                context = self.coq.proof_context
                return CoqError(str(e), command, line_number, context)

        return context

    def run_command(self, command: str, timeout_seconds: t.Optional[int] = None):
        """
        Run a single command
        """
        LOGGER.debug(
            'running command: "' + command + '"',
            extra={
                # "context": proof_context_to_str(self.coq.proof_context),
                "command": command,
                "timeout_seconds": timeout_seconds,
            },
        )
        self.coq.run_stmt(command, timeout=timeout_seconds)
        # LOGGER.debug(
        #     "after running command",
        #     extra={
        #         "command": command,
        #         "context": proof_context_to_str(self.coq.proof_context),
        #     },
        # )
        self.num_statements_executed += 1

    def get_feedbacks(self) -> t.List[FeedbackMessage]:
        """
        get the feedback messages from the last command.
        make sure you run this immediately after "run_command"
        """
        raw_feedbacks = t.cast(
            c.serapi_backend.CoqSeraPyInstance, self.coq.backend
        ).feedbacks
        messages = [
            FeedbackMessage.from_sexp_array(feedback) for feedback in raw_feedbacks
        ]
        LOGGER.debug(
            "got feedbacks",
            extra={
                "raw": raw_feedbacks,
                "feedbacks": messages,
                "str": str(raw_feedbacks),
            },
        )
        return [message for message in messages if message is not None]

    @property
    def proof_context(self) -> t.Optional[c.contexts.ProofContext]:
        return self.coq.proof_context

    def revert_command(self):
        """
        Revert the last command
        """
        if self.num_statements_executed == 0:
            LOGGER.warn("no commands left to revert")
            return
        LOGGER.debug("reverting last command")
        self.coq.cancel_last()
        self.num_cancel_lasts_executed += 1

    def reset(self):
        if self.num_statements_executed == 0:
            return

        LOGGER.debug(f"resetting {self.num_statements_executed} statements")
        for _ in range(self.num_statements_executed):
            self.revert_command()
        self.num_statements_executed = 0

    # errors that look like this should result in returning none
    CHECK_OR_PRINT_ERRORS = [
        "not a defined object",
        "Fetching opaque proofs from disk",
        "Can't print",
        "Can't check",
        "not found in the current environment",
    ]

    def check(self, identifier: str) -> Optional[str]:
        """
        Check the type of the given identifier
        """
        try:
            return remove_unnecessary_lines_from_definition(
                self.coq.check_term(identifier)
            )
        except ValueError as e:
            if any(error in str(e) for error in self.CHECK_OR_PRINT_ERRORS):
                return None
            else:
                raise e
        except c.coq_backend.CompletedError as e:
            return None
        except c.coq_backend.BadResponse as e:
            if any(error in str(e) for error in self.CHECK_OR_PRINT_ERRORS):
                return None
            else:
                raise e

    def get_lemmas_for_identifiers(self, identifiers: List[str]) -> t.List[str]:
        """
        Get the lemmas for the given identifiers
        """
        lemmas = []
        for identifier in identifiers:
            try:
                lemma = self.check(identifier)
                LOGGER.info("lemma", extra={"identifier": identifier, "lemma": lemma})
                if lemma is not None:
                    lemmas.append(lemma)
            except Exception as e:
                LOGGER.error(
                    f"caught error while checking {identifier}: {str(e)}. will continue checking, ignoring this error",
                    extra={
                        "identifier": identifier,
                        "error": str(e),
                        "stacktrace": traceback.format_exc(),
                    },
                )
                # TODO: move flushing queue to print/check rather than their callers
                # flush queue
                self.coq.backend.interrupt()
        return lemmas

    def print(self, identifier: str) -> Optional[str]:
        """
        Print the given identifier
        """
        try:
            return remove_unnecessary_lines_from_definition(
                self.coq.print_term(identifier)
            )
        except ValueError as e:
            self.coq.backend.interrupt()
            if any(error in str(e) for error in self.CHECK_OR_PRINT_ERRORS):
                return None
            else:
                raise e
        except c.coq_backend.CompletedError as e:
            self.coq.backend.interrupt()
            return None
        except c.coq_backend.BadResponse as e:
            self.coq.backend.interrupt()
            if any(error in str(e) for error in self.CHECK_OR_PRINT_ERRORS):
                return None
            else:
                raise e

    def __search_arguments(self, identifier: str) -> List[str]:
        identifier_pieces = identifier.split(".")

        # we quote the identifier, to just search for that
        # string in the names of definitions
        # queryvernac accesses serapi using a command like this:
        #   (Query () (Vernac \"{vernac}\"))
        # so naively quoting the identifier leads to a command like this:
        #   (Query () (Vernac "Search "A". "))
        # which has bad quotes
        # so we need to escape the quotes
        #   (Query () (Vernac "Search \"A\". "))
        quoted_identifier_pieces = [f'\\"{piece}\\"' for piece in identifier_pieces]

        arguments_without_qualifiers = [identifier, " ".join(quoted_identifier_pieces)]
        if self.__coq_version != "8.12":
            # qualifiers like is:Lemma and is:Theorem were added in 8.12
            return arguments_without_qualifiers

        ans = []
        ans.append(f"{identifier} is:Lemma")
        ans.append(f"{identifier} is:Theorem")

        # we join all pieces into a single query, so we search for lemmas that
        # have all of the pieces in their name
        ans.append(
            " ".join([f"{piece} is:Lemma" for piece in quoted_identifier_pieces])
        )
        ans.append(
            " ".join(
                [f'\\"{piece}\\" is:Theorem' for piece in quoted_identifier_pieces]
            )
        )

        return ans

    def search(self, identifier: str) -> List[str]:
        """
        Search for the given identifier
        """

        search_arguments = self.__search_arguments(identifier)
        LOGGER.debug(
            f"searching for {identifier}",
            extra={"identifier": identifier, "search_arguments": search_arguments},
        )

        results = []
        for search_argument in search_arguments:
            try:
                results += self.coq.search_about(search_argument)
            except Exception as e:
                LOGGER.error(
                    f"caught error while searching for {search_argument}: {str(e)}. will continue searching, ignoring this error",
                    extra={
                        "search_argument": search_argument,
                        "identifier": identifier,
                        "error": str(e),
                        "stacktrace": traceback.format_exc(),
                    },
                )
                # flush queue
                self.coq.backend.interrupt()

        return list(set(results))[0:30]

    def locate(self, identifier: str) -> t.Optional[str]:
        try:
            return self.coq.backend.queryVernac(f"Locate {identifier}.")[0].split("\n")[
                0
            ]
        except Exception as e:
            LOGGER.error(
                f"caught error while locating {identifier}: {str(e)}. ignoring this error and returning None",
                extra={
                    "identifier": identifier,
                    "error": str(e),
                    "stacktrace": traceback.format_exc(),
                },
            )
            # flush queue
            self.coq.backend.interrupt()

    def ltac_definitions(self) -> List[str]:
        """
        Get the names of all the ltac definitions
        """
        messages = self.coq.backend.queryVernac("Print Ltac Signatures.")
        assert len(messages) == 1
        signatures = messages[0].split("\n")

        # filter out as many coq library ltacs as possible
        signatures = [
            signature for signature in signatures if not signature in DEFAULT_LTACS
        ]
        names = [signature.split(" ")[0] for signature in signatures]
        names = [name for name in names if not name.strip() == ""]

        # get the full names of the ltacs
        locations = []
        for name in names:
            locations.append(self.locate(name))

        # filter out any ltacs from the standard library
        locations_in_this_project = [
            location for location in locations if not location.startswith("Ltac Coq.")
        ]

        # map locations back to simplified names from the original signatures
        tactic_names = [
            location.split(" ")[1].split(".")[-1]
            for location in locations_in_this_project
        ]
        tactic_signatures = [
            signature
            for signature in signatures
            if any(tactic_name in signature for tactic_name in tactic_names)
        ]
        tactic_names = [signature.split(" ")[0] for signature in tactic_signatures]

        tactic_definitions = []
        for name in tactic_names:
            try:
                tactic_definitions.append(
                    self.coq.backend.queryVernac(f"Print Ltac {name}.")[0]
                )
            except c.coq_backend.BadResponse as e:
                LOGGER.error(
                    f"caught error while getting definition of {name}: {str(e)}. ignoring this error and continuing",
                    extra={
                        "name": name,
                        "error": str(e),
                        "stacktrace": traceback.format_exc(),
                    },
                )
                continue
        return tactic_definitions


@contextmanager
def switch(coq_version: CoqVersion):
    command = f"opam env --switch coq-{coq_version} --set-switch --sexp"
    output = subprocess.run(
        command, shell=True, check=True, capture_output=True, text=True
    ).stdout

    OPAM_SWITCH_LOGGER.debug(command, extra={"output": output})

    environment_assignments_sexp = sexpdata.loads(output)
    OPAM_SWITCH_LOGGER.debug(
        "environment assignments sexp",
        extra={"value": environment_assignments_sexp},
    )

    environment_assignments: Dict[str, str] = {
        assignment[0]: assignment[1] for assignment in environment_assignments_sexp
    }
    old_environment_assignments = {
        variable: os.environ.get(variable) for variable in environment_assignments
    }

    def set_env(variable: str, value: Optional[str]):
        if value is None and os.environ.get(variable) is not None:
            del os.environ[variable]
        elif value is None:
            return
        else:
            os.environ[variable] = value

    try:
        for variable, value in environment_assignments.items():
            old_value = old_environment_assignments[variable]
            OPAM_SWITCH_LOGGER.debug(
                "setting environment variable",
                extra={
                    "variable": variable,
                    "old_value": old_value,
                    "new_value": value,
                },
            )
            set_env(variable, value)

        command = "coqc -v"
        output = subprocess.run(
            command, shell=True, check=True, capture_output=True, text=True
        ).stdout
        OPAM_SWITCH_LOGGER.debug("coqc -v", extra={"output": output})

        yield environment_assignments
    finally:
        for variable, value in old_environment_assignments.items():
            OPAM_SWITCH_LOGGER.debug(
                "restoring environment variable",
                extra={
                    "variable": variable,
                    "value": value,
                    "current_value": os.environ.get(variable),
                },
            )
            set_env(variable, value)


def obligation_summary(obligation: c.Obligation) -> str:  # type: ignore
    return f"({len(obligation.hypotheses)} HYPS)|-{obligation.goal}"


def code_commands(code: str) -> List[Tuple[str, int]]:
    return [(command[0].strip(), command[1]) for command in read_commands(code)]


def code_lemmas(code: str) -> List[str]:
    return list(
        itertools.chain.from_iterable(
            c.lemmas_defined_by_stmt(command[0]) for command in read_commands(code)  # type: ignore
        )
    )


IDENTIFIER_REGEX = r"([a-zA-Z_]+(?:(?:\.)?[a-zA-Z0-9_']+)*)"
NON_IDENTIFIERS = set(
    [
        # keywords
        "forall",
        "exists",
        "Lemma",
        "Theorem",
        "Example",
        "fun",
        "Record",
        "_",
        "Type",
        "Prop",
        "function_scope",
        "Set",
        "nat",
        "with",
        "end",
        "match",
        "in",
        "fix",
        "else",
        "if",
        "Definition",
        "Module",
        "as",
        "by",
        "let",
        "ltac",
        "proof",
        "generalize",
        "dependent",
        "functional",
        "induction",
        # these are not keywords. we want to skip them because they balloon the size of the definitions
        "Nat",
        "Term",
        "Ltac",
    ]
)


def parse_identifiers_in_lemma(lemma: str) -> Set[str]:
    """
    Return a list of identifiers in the lemma
    """
    words = c.coq_util.get_words(lemma)
    return set(
        ensure_not_none(re.match(IDENTIFIER_REGEX, word)).group(0)
        for word in words
        if re.match(IDENTIFIER_REGEX, word) and word not in NON_IDENTIFIERS
    )


IGNORE_LINE_REGEX = r"(^For|^Arguments|^Argument scope|^Expanded type for implicit arguments|^.*function_scope]\s*$|^.*type_scope]\s*$|^.* _]\s*$)"

MATCH_INDUCTIVE_REGEX = r"Inductive\s+([a-zA-Z_][a-zA-Z0-9_']*)\s+:"
INDUCTIVE_CONSTRUCTOR_REGEX = r"(?::=|\|)\s+([a-zA-Z_][a-zA-Z0-9_']*)"

MATCH_RECORD_REGEX = r"Record\s([a-zA-Z_][a-zA-Z0-9_']*)"
RECORD_ITEM_REGEX = r"(?:{|;)\s+([a-zA-Z_][a-zA-Z0-9_']*)\s+:"


def parse_identifiers_in_definition(definition: str) -> Set[str]:
    lines = definition.split("\n")
    lines_to_check = [line for line in lines if (not re.match(IGNORE_LINE_REGEX, line))]

    identifiers_to_ignore = set()

    # don't expand inductive constructors or record items, as they're already
    # in the definition of their parent
    if re.match(MATCH_INDUCTIVE_REGEX, definition):
        identifiers_to_ignore = set(re.findall(INDUCTIVE_CONSTRUCTOR_REGEX, definition))
    elif re.match(MATCH_RECORD_REGEX, definition):
        identifiers_to_ignore = set(re.findall(RECORD_ITEM_REGEX, definition))

    matches: List[List[str]] = [
        re.findall(IDENTIFIER_REGEX, line) for line in lines_to_check
    ]
    flat_matches = [
        match
        for line_matches in matches
        for match in line_matches
        if match is not None
        and len(match) > 0
        and match not in NON_IDENTIFIERS
        and match not in identifiers_to_ignore
    ]

    return set(match for match in flat_matches if match is not None)


def remove_unnecessary_lines_from_definition(definition: str) -> str:
    lines = definition.split("\n")
    ans = "\n".join(
        [line for line in lines if (not re.match(IGNORE_LINE_REGEX, line))]
    ).strip()
    return ans


def kill_non_tactic_commands(code: str) -> str:
    """
    Remove all commands that aren't tactics
    """
    commands = c.coq_util.read_commands(code)
    lemmas = code_lemmas(code)

    def select_lemma(lemma: str) -> List[str]:
        nonlocal commands
        result = []
        in_lemma = False
        for command in commands:
            command_lemmas = c.coq_util.lemmas_defined_by_stmt(command)
            simplified_command = command

            if len(command_lemmas) > 0:
                if command_lemmas[0] == lemma:
                    in_lemma = True
                    result.append(command)
                continue

            if simplified_command in ["Qed.", "Admitted.", "Abort."]:
                if in_lemma:
                    result.append(command)
                    return result
                continue

            if in_lemma:
                result.append(command)
        return result

    if len(lemmas) > 0:
        lemma = lemmas[-1]
        commands = select_lemma(lemma)

    result = ""
    for command in commands:
        command_lemmas = c.coq_util.lemmas_defined_by_stmt(command)
        simplified_command = c.coq_util.kill_comments(command).strip()

        if (
            len(command_lemmas) > 0
            or simplified_command in ["Proof."]
            or simplified_command in ["Qed.", "Admitted.", "Abort."]
        ):
            continue

        result += command
    return result.strip()


def proof_context_eq(
    proof_context: t.Union[c.contexts.ProofContext, None],
    other_proof_context: t.Union[c.contexts.ProofContext, None],
) -> bool:
    if proof_context == other_proof_context:
        return True

    if proof_context is None or other_proof_context is None:
        return False

    return (
        goals_match(proof_context.fg_goals, other_proof_context.fg_goals)
        and goals_match(proof_context.bg_goals, other_proof_context.bg_goals)
        and goals_match(proof_context.all_goals, other_proof_context.all_goals)
        and goals_match(proof_context.all_goals, other_proof_context.all_goals)
    )

def debug_proof_context_to_str(proof_context: Union[c.contexts.ProofContext, None]) -> str:
    if proof_context is None:
        return "No proof context."

    if len(proof_context.fg_goals) > 0:
        return obligation_to_str(proof_context.fg_goals[0])
    else:
        return "Proof finished." if len(proof_context.all_goals) == 0 else "No focused goal."


def proof_context_to_str(proof_context: Union[c.contexts.ProofContext, None]) -> str:
    if proof_context is None:
        return "No proof context."

    if len(proof_context.fg_goals) > 0:
        return obligation_to_str(proof_context.fg_goals[0])
    else:
        return "Proof finished."


def obligation_to_str(obligation: c.contexts.Obligation) -> str:
    return "\n".join(list(obligation.hypotheses) + ["\n---\n", obligation.goal])


def kill_comments(string: str) -> str:
    result = ""
    depth = 0
    in_quote = False
    for i in range(len(string)):
        if in_quote:
            if depth == 0:
                result += string[i]
            if string[i] == '"' and string[i - 1] != "\\":
                in_quote = False
        else:
            if string[i : i + 2] == "(*":
                depth += 1
            if depth == 0:
                result += string[i]
            if string[i - 1 : i + 1] == "*)" and depth > 0:
                depth -= 1
            if string[i] == '"' and string[i - 1] != "\\":
                in_quote = True
    return result


def normalize_whitespace(proposition: str) -> str:
    proposition = proposition.strip()
    proposition = proposition.replace("\n", "")
    proposition = re.sub(r"\s+", " ", proposition)
    return proposition


def normalize(code: str) -> str:
    """converts code into a list of tactics separated by newlines for easy comparison"""
    commands = [command for command, line in read_commands(code)]
    commands = [kill_comments(command).strip() for command in commands]
    commands = [command for command in commands if command != ""]
    return "\n".join(commands)


def read_commands(
    contents: str, max_commands: Optional[int] = None
) -> List[Tuple[str, int]]:
    """Reads commands from a string, returning a list of commands with their line numbers."""
    result: list[Tuple[str, int]] = []
    cur_command = ""
    comment_depth = 0
    in_quote = False
    curPos = 0
    line_number = 1

    def search_pat(pat: Pattern) -> Tuple[Optional[Match], int]:
        match = pat.search(contents, curPos)
        return match, match.end() if match else len(contents) + 1

    def append_to_result():
        nonlocal cur_command, line_number
        result.append((cur_command, line_number))
        line_number += cur_command.count("\n")
        cur_command = ""

    while curPos < len(contents) and (
        max_commands is None or len(result) < max_commands
    ):
        _, next_quote = search_pat(re.compile(r"\""))
        _, next_open_comment = search_pat(re.compile(r"\(\*"))
        _, next_close_comment = search_pat(re.compile(r"\*\)"))
        _, next_bracket = search_pat(re.compile(r"[\{\}]"))
        # next bullet match must also include any trailing spaces, as we want to include newlines as part of the bullet.
        next_bullet_match, next_bullet = search_pat(
            re.compile(r"[\+\-\*]+(?![\)\+\-\*])\s*")
        )
        _, next_period = search_pat(re.compile(r"(?<!\.)\.($|\s)|\.\.\.($|\s)"))
        nextPos = min(
            next_quote,
            next_open_comment,
            next_close_comment,
            next_bracket,
            next_bullet,
            next_period,
        )
        assert curPos < nextPos

        next_chunk = contents[curPos:nextPos]
        cur_command += next_chunk

        # update state based on what delimiter we just read
        if nextPos == next_quote:
            if comment_depth == 0:
                in_quote = not in_quote
        elif nextPos == next_open_comment:
            if not in_quote:
                comment_depth += 1
        elif nextPos == next_close_comment:
            if not in_quote and comment_depth > 0:
                comment_depth -= 1
        elif nextPos == next_bracket:
            if (
                not in_quote
                and comment_depth == 0
                and re.match(r"\s*(?:\d+\s*:)?\s*$", kill_comments(cur_command[:-1]))
            ):
                append_to_result()
        elif nextPos == next_bullet:
            assert next_bullet_match
            match_length = next_bullet_match.end() - next_bullet_match.start()
            if (
                not in_quote
                and comment_depth == 0
                and re.match(r"\s*$", kill_comments(cur_command[:-match_length]))
            ):
                append_to_result()
            assert next_bullet_match.end() >= nextPos
        elif nextPos == next_period:
            if not in_quote and comment_depth == 0:
                append_to_result()

        curPos = nextPos

    assert kill_comments(cur_command).strip() == "", (
        "Couldn't parse command list! Are you sure you didn't forget an ending period?"
        + (contents if len(contents) < 64 else "[too long to print]")
    )
    return result


DEFINITION_REGEX = r"^(\*\*\*\s+\[)?([a-zA-Z_][a-zA-Z0-9_', ]*)\s*:\s*([^]]*)(\])?"


@dataclass
class Definition:
    name: str
    value: str

    @staticmethod
    def parse_hypotheses(hypotheses: List[str]) -> List["Definition"]:
        defs_or_none = [Definition.parse(hypothesis) for hypothesis in hypotheses]
        return [definition for definition in defs_or_none if definition is not None]

    @staticmethod
    def parse(definition_str: str) -> Optional["Definition"]:
        match = re.match(DEFINITION_REGEX, definition_str)
        if match is None:
            return None

        name = match.group(2).strip()
        value = match.group(3).strip()
        return Definition(name, value)

    @property
    def name_identifiers(self) -> Set[str]:
        return set(item.strip() for item in self.name.split(","))

    def matches(self, other: "Definition") -> bool:
        self_identifiers = self.name_identifiers
        other_identifiers = other.name_identifiers

        smaller_set = (
            self_identifiers
            if len(self_identifiers) < len(other_identifiers)
            else other_identifiers
        )
        larger_set = (
            self_identifiers
            if len(self_identifiers) >= len(other_identifiers)
            else other_identifiers
        )

        return (
            smaller_set.issubset(larger_set)
            and self.value.strip() == other.value.strip()
        )


def is_redundant(o_prime: c.contexts.Obligation, o: c.contexts.Obligation) -> bool:
    """
    returns true if o_prime is redundant with respect to o.
    This means that anything that can be proven from o_prime can also be proven from o.
    """
    # no need to alpha normalize if comparing with the same variable names
    # i.e. not accross decompositions
    return o_prime.goal == o.goal and all(
        hypothesis in o.hypotheses for hypothesis in o_prime.hypotheses
    )


def goals_match(
    initial_goals: t.List[c.contexts.Obligation],
    current_goals: t.List[c.contexts.Obligation],
) -> bool:
    """
    returns True if the goals in current_goals are the same as the goals in initial_goals
    """
    for goal in current_goals:
        if goal not in initial_goals:
            return False

    return True


def non_fg_goals_match(
    initial_proof_context: c.contexts.ProofContext,
    proof_context: c.contexts.ProofContext,
    ignore_given_up_goals: bool = False,
) -> bool:
    if len(proof_context.bg_goals) != len(initial_proof_context.bg_goals):
        return False
    for bg_goal in proof_context.bg_goals:
        if bg_goal not in initial_proof_context.bg_goals:
            return False

    if len(proof_context.shelved_goals) != len(initial_proof_context.shelved_goals):
        return False
    for shelved_goal in proof_context.shelved_goals:
        if shelved_goal not in initial_proof_context.shelved_goals:
            return False

    if ignore_given_up_goals:
        return True

    if len(proof_context.given_up_goals) != len(initial_proof_context.given_up_goals):
        return False
    for given_up_goal in proof_context.given_up_goals:
        if given_up_goal not in initial_proof_context.given_up_goals:
            return False

    return True


def is_initial_goal_proven(
    initial_proof_context: c.contexts.ProofContext,
    current_proof_context: t.Optional[c.contexts.ProofContext],
    error: t.Optional[CoqError],
    ignore_given_up_goals: bool = False,
) -> bool:
    """
    returns True if the initial goal specified by the proposition command and
    proof prefix is proven
    """
    if len(initial_proof_context.fg_goals) != 1:
        LOGGER.warn(
            "initial_proof_context has multiple fg_goals",
            extra={
                "initial_proof_context": initial_proof_context,
                "num_fg_goals": len(initial_proof_context.fg_goals),
            },
        )
        return False

    return (
        current_proof_context is not None
        and (len(current_proof_context.fg_goals) == 0)
        and (
            non_fg_goals_match(
                initial_proof_context, current_proof_context, ignore_given_up_goals
            )
        )
        and (error is None or error.is_attempt_to_save_incomplete_proof)
    )


def is_initial_goal_proven_multiple_fg_goals(
    initial_proof_context: c.contexts.ProofContext,
    current_proof_context: t.Optional[c.contexts.ProofContext],
    error: t.Optional[CoqError],
    ignore_given_up_goals: bool = False,
) -> bool:
    """
    returns True if the initial goal specified by the proposition command and proof prefix is proven
    """
    return (
        current_proof_context is not None
        and (
            len(current_proof_context.fg_goals)
            == (len(initial_proof_context.fg_goals) - 1)
        )
        and (
            goals_match(initial_proof_context.fg_goals, current_proof_context.fg_goals)
        )
        and (
            non_fg_goals_match(
                initial_proof_context, current_proof_context, ignore_given_up_goals
            )
        )
        and (error is None or error.is_attempt_to_save_incomplete_proof)
    )


def additional_bg_goals(
    initial_proof_context: c.contexts.ProofContext,
    current_proof_context: t.Optional[c.contexts.ProofContext],
) -> t.List[c.contexts.Obligation]:
    """
    returns a list of bg_goals that are in current_proof_context but not in initial_proof_context
    """
    if current_proof_context is None:
        return []
    return [
        bg_goal
        for bg_goal in current_proof_context.bg_goals
        if bg_goal not in initial_proof_context.bg_goals
    ]


SECTION_REGEX = re.compile(r"Section\s+(\w+)")
END_SECTION_REGEX = re.compile(r"End\s+(\w+)")
LEMMA_TOKENS = [
    "Theorem",
    "Lemma",
    "Fact",
    "Remark",
    "Corollary",
    "Proposition",
    "Property",
]
LEMMA_REGEX = re.compile(
    r"(" + "|".join(LEMMA_TOKENS) + r")\s+(\w+)\s*(\{\w+\})?\s*:([\s\S]*)\."
)


def get_lemmas_from_commands(
    project_name: str,
    file_name: str,
    coq_version: CoqVersion,
    commands: List[Tuple[str, int]],
    debug=True,
):
    section_names: List[str] = []
    lemmas: List[LemmaLocation] = []
    lemma_commands: List[str] = []
    in_proof = False
    for command, line in commands:
        if debug:
            print(f"processing command: {command}")

        section_match = SECTION_REGEX.match(command)
        if section_match is not None:
            if debug:
                print(f"section match")
            section_name = section_match.group(1)
            section_names.append(section_name)
            continue

        end_section_match = END_SECTION_REGEX.match(command)
        if end_section_match is not None:
            if debug:
                print(f"end section match")
            section_name = end_section_match.group(1)
            if len(section_names) > 0 and section_name == section_names[-1]:
                section_names.pop()
            else:
                print(
                    f"warning: ending a section that wasn't started: {section_name}. section_names: {section_names}"
                )
            continue

        try:
            lemma_name = c.coq_util.lemma_name_from_statement(command)
            if lemma_name.strip() == "":
                continue
            if not any(token in command for token in LEMMA_TOKENS):
                continue
            lemma_location = LemmaLocation(
                project_name=project_name,
                file_name=file_name,
                lemma_name=lemma_name,
                section_names=section_names.copy(),
                coq_version=coq_version,
            )
            lemmas.append(lemma_location)
            lemma_commands.append(command)
        except:
            pass

        if command == "Proof.":
            in_proof = True

        # only keep proofs that end in Qed
        if in_proof and (
            command == "Admitted." or command == "Abort." or command == "Defined."
        ):
            if debug:
                print("admitted or abort")
            lemmas.pop()
            lemma_commands.pop()

        if (
            command == "Qed."
            or command == "Admitted."
            or command == "Abort."
            or command == "Proof."
        ):
            in_proof = False
    return lemmas, lemma_commands
