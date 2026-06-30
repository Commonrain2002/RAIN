import typing as t
from dataclasses import dataclass, field
import re
import coq_serapy as c

from src.coq_serapy_util import (
    kill_comments,
    Coq,
    CoqResult,
    proof_context_to_str,
    CoqError,
    is_initial_goal_proven,
    additional_bg_goals,
    IDENTIFIER_REGEX,
    NON_IDENTIFIERS,
)
from src.utils import get_logger, step_generator_and_save_yields

LOGGER = get_logger("proof_script")

BULLET_REGEX = re.compile(r"^\++|\*+|\-+$")


@dataclass(frozen=True)
class CoqPartialSuccess:
    # the prefix that led to the decomposition
    prefix: "ProofScript"
    subgoal_obligations: t.List[t.Optional[c.contexts.Obligation]]
    subgoal_results: t.List["CoqPartialResult"]
    subgoal_scripts: t.List["ProofScript"]
    subgoal_executed_scripts: t.List["ProofScript"]
    end_context: c.contexts.ProofContext

    @property
    def is_success(self) -> bool:
        return all(
            isinstance(result, c.contexts.ProofContext)
            or isinstance(result, CoqPartialSuccess)
            and result.is_success
            for result in self.subgoal_results
        )


@dataclass(frozen=True)
class Skip:
    """
    if a subgoal is skipped (e.g. never executed), we return this.
    this should not occur at the toplevel, only as a result of admitted subgoals
    """

    pass


CoqPartialResult = t.Union[c.contexts.ProofContext, CoqError, CoqPartialSuccess, Skip]


class Tactic:
    src: str
    start_idx: int
    end_idx: int

    def __init__(self, src: str, start_idx: int = 0, end_idx: t.Optional[int] = None):
        if end_idx is None:
            end_idx = len(src)

        self.src = src
        self.start_idx = start_idx
        self.end_idx = end_idx

        assert self.start_idx >= 0, "Start index must be non-negative"
        assert self.end_idx <= len(src), "End index must be within the source string"
        assert self.start_idx <= self.end_idx, "Start index must be less than end index"
        assert (
            self.is_bullet
            or self.is_open_brace
            or self.is_close_brace
            or self.text.count(".") >= 1
        ), f"Invalid tactic: '{self.raw_text}'. Must be a bullet, brace, or contain one or more periods."

    @property
    def raw_text(self) -> str:
        return self.src[self.start_idx : self.end_idx]

    @property
    def start_line_number(self) -> int:
        # count the number of newlines before the start of the tactic
        return self.src[: self.start_idx].count("\n") + 1

    @property
    def end_line_number(self) -> int:
        # count the number of newlines before the end of the tactic
        return self.src[: self.end_idx].count("\n") + 1

    @property
    def text(self) -> str:
        return kill_comments(self.raw_text).strip()

    def pretty_print(self) -> str:
        return self.text

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Tactic):
            return False
        return self.text == other.text

    def __hash__(self) -> int:
        return hash(self.text)

    def __repr__(self) -> str:
        return (
            f"Tactic({self.text!r}, {self.start_line_number}, {self.end_line_number})"
        )

    @property
    def is_bullet(self) -> bool:
        return BULLET_REGEX.match(self.text) is not None

    @property
    def is_open_brace(self) -> bool:
        return self.text == "{"

    @property
    def is_close_brace(self) -> bool:
        return self.text == "}"

    @property
    def is_admit(self) -> bool:
        return self.text == "admit."

    @property
    def is_assert(self) -> bool:
        # TODO: might need to make this smarter and have it use a regex
        return "assert " in self.text

    def run(self, coq: Coq, timeout_seconds: t.Optional[int] = None) -> CoqResult:
        assert (
            coq.coq.proof_context is not None
        ), f"tactic {self.text}: Context should not be None before running tactic"
        try:
            coq.run_command(self.text, timeout_seconds=timeout_seconds)
            assert (
                coq.coq.proof_context is not None
            ), f"tactic ${self.text}: Context should not be None after running tactic"
            return coq.coq.proof_context
        except c.coq_backend.CoqException as e:
            LOGGER.info(
                "Error running tactic",
                extra={
                    "tactic": self.text,
                    "line_number": self.start_line_number,
                    "error": e,
                },
            )
            return CoqError(
                str(e), self.text, self.start_line_number, coq.coq.proof_context
            )

    @property
    def identifiers(self) -> t.Set[str]:
        identifiers = set(re.findall(IDENTIFIER_REGEX, self.text))
        identifiers = identifiers.difference(NON_IDENTIFIERS)
        identifiers = set(
            identifier
            for identifier in identifiers
            if not (
                self.text.startswith(identifier + " ") or self.text == f"{identifier}."
            )
        )
        return identifiers

    @property
    def is_hammer(self) -> bool:
        return self.text == "hammer."

    def run_hammer_and_get_reconstruction_tactic(
        self, coq: Coq
    ) -> t.Tuple[CoqResult, t.Optional["Tactic"]]:
        assert self.is_hammer, "This function should only be called on a hammer tactic"
        result = self.run(coq)
        if isinstance(result, CoqError):
            return result, None
        else:
            feedbacks = coq.get_feedbacks()
            hammer_reconstruction_tactics = [
                feedback.hammer_reconstruction_tactic() for feedback in feedbacks
            ]
            hammer_reconstruction_tactics = [
                tactic for tactic in hammer_reconstruction_tactics if tactic is not None
            ]
            assert (
                len(hammer_reconstruction_tactics) > 0
            ), "No hammer reconstruction tactic found"
            return result, Tactic(hammer_reconstruction_tactics[0])

    # TODO: parse and normalize semicolon/try tacticals
    # TODO: detect if it's an apply and figure out what the lemma applied is


@dataclass(frozen=True)
class ProofScript:
    contents: t.List[t.Union[Tactic, "ProofScript"]]

    def to_json(self) -> str:
        return self.pretty_print()

    @classmethod
    def from_json(cls, data: str) -> "ProofScript":
        return cls.parse(data)

    # TODO: script edits
    #   swap a bullet for a different script

    def __str__(self) -> str:
        return self.pretty_print()

    def __repr__(self) -> str:
        return f"ProofScript({self.contents!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProofScript):
            return False
        return self.pretty_print() == other.pretty_print()

    def __hash__(self) -> int:
        return hash(self.pretty_print())

    @property
    def prefix(self) -> t.List[Tactic]:
        ans: t.List[Tactic] = []
        for item in self.contents:
            if isinstance(item, ProofScript):
                break
            else:
                ans.append(item)
        return ans
    
    @property
    def depth(self) -> int:
        if all(isinstance(item, Tactic) for item in self.contents):
            return 1
        else:
            return 1 + max(item.depth for item in self.contents if isinstance(item, ProofScript))
    
    @property
    def tactics(self) -> t.List[Tactic]:
        return list(self.walk())

    def pretty_print(self, bullet_level=0, use_braces=False) -> str:
        ans = ""

        for idx, item in enumerate(self.contents):
            if isinstance(item, ProofScript):
                if idx > 0 and not isinstance(self.contents[idx - 1], ProofScript):
                    ans = ans.strip() + "\n"

                rest = self.contents[idx + 1 :]
                ans += (
                    item.pretty_print(
                        bullet_level + 1,
                        not all(isinstance(x, ProofScript) for x in rest),
                    )
                    + "\n"
                )
            else:
                ans += item.pretty_print() + " "

        ans = ans.strip()

        if use_braces:
            ans = "{ " + ans + " }"
        elif bullet_level > 0:
            ans = bullet_str(bullet_level) + " " + ans

        return ans

    @staticmethod
    def parse(src: str) -> "ProofScript":
        tactics = read_tactics(src)
        return ProofScript.from_tactics(tactics)

    @staticmethod
    def from_tactics(tactics: t.List[Tactic]) -> "ProofScript":
        try:
            return process_bullets_and_braces(tactics)
        except Exception as e:
            LOGGER.error(
                "Error parsing proof script",
                extra={
                    "error": e,
                    "tactics": [tactic.text for tactic in tactics],
                },
            )
            raise e

    def walk(
        self, bullet_level=0, use_braces=False
    ) -> t.Generator[Tactic, t.Optional[t.Literal["skip"]], None]:
        """
        yields each tactic in the script, in order, with correct focusing of the current bullet.
        if you call `generator.send('skip')`, it will skip to the end of the current bullet.
        """

        try:
            if use_braces:
                command = yield Tactic("{")
                if command == "skip":
                    return
            elif bullet_level > 0:
                command = yield Tactic(bullet_str(bullet_level))
                if command == "skip":
                    return

            for idx, item in enumerate(self.contents):
                if isinstance(item, ProofScript):
                    rest = self.contents[idx + 1 :]
                    yield from item.walk(
                        bullet_level + 1,
                        not all(isinstance(x, ProofScript) for x in rest),
                    )
                else:
                    command = yield item
                    if command == "skip":
                        return
        finally:
            if use_braces:
                yield Tactic("}")

    def run_until_end_or_error(self, coq: Coq) -> CoqResult:
        context = coq.coq.proof_context
        LOGGER.debug(
            "context before running code",
            extra={
                "context": proof_context_to_str(context),
            },
        )

        for tactic in self.walk():
            result = tactic.run(coq)
            if isinstance(result, CoqError):
                return result
            else:
                context = result

        assert (
            context is not None
        ), "Context should not be None after running proof script to the end"
        return context

    # TODO: factor out common state, allowing for decomposition into helper fns
    # TODO: this is broken rn. it treats a {} subgoal as a decomposition point, but it's not. it's part of the prefix.
    def run_admitting_failed_subgoals(
        self,
        coq: Coq,
        bullet_level=0,
        use_braces=False,
        try_hammer_on_error: bool = False,
    ) -> t.Generator[t.Tuple[Tactic, c.contexts.ProofContext], t.Any, CoqPartialResult]:
        return RunAdmittingFailedSubgoals(
            self,
            coq,
            bullet_level=bullet_level,
            use_braces=use_braces,
            try_hammer_on_error=try_hammer_on_error,
        ).run()

    def revert(self, coq: Coq):
        for _ in self.walk():
            coq.revert_command()

    def run_until_goal_decomposition(
        self, coq: Coq
    ) -> t.Union[CoqPartialSuccess, CoqError]:
        """
        runs the script until it decomposes into subgoals. Unlike run_admitting_failed_subgoals, this function will not attempt to execute any further tactics after the decomposition.
        """
        assert (
            coq.coq.proof_context is not None
        ), "Context should not be None before running proof script"
        context: c.contexts.ProofContext = coq.coq.proof_context
        initial_context = context

        def get_qed_error(context: c.contexts.ProofContext) -> CoqError:
            nonlocal coq
            try:
                coq.run_command("Qed.")
                LOGGER.error(
                    "We should never get here",
                    extra={
                        "context": proof_context_to_str(coq.coq.proof_context),
                    },
                )
                raise Exception("We should never get here")
            except c.coq_backend.CoqException as e:
                LOGGER.info(
                    "Error running Qed after script",
                    extra={
                        "error": e,
                        "script": self.pretty_print(),
                    },
                )
                return CoqError(str(e), "Qed.", 0, context)

        prefix: t.List[Tactic] = []
        for item in self.contents:
            if isinstance(item, ProofScript):
                # give up if we haven't found a decomp by the first bullet
                # creating an error by running a bullet type we never produce
                return get_qed_error(context)
            elif isinstance(item, Tactic):
                result = item.run(coq)
                if isinstance(result, c.contexts.ProofContext):
                    context = result
                    prefix.append(item)
                else:
                    return result

                if is_decomposition(context):
                    return CoqPartialSuccess(
                        ProofScript(
                            t.cast(t.List[t.Union[Tactic, "ProofScript"]], prefix)
                        ),
                        t.cast(
                            t.List[t.Optional[c.contexts.Obligation]], context.fg_goals
                        ),
                        [Skip() for _ in context.fg_goals],
                        [ProofScript([]) for _ in context.fg_goals],
                        [ProofScript([]) for _ in context.fg_goals],
                        context,
                    )

        return get_qed_error(context)

    def first_tactic(self) -> Tactic:
        item = self.contents[0]
        if isinstance(item, ProofScript):
            return item.first_tactic()
        else:
            return item

    @property
    def start_line_number(self):
        return self.first_tactic().start_line_number

    @property
    def has_assert(self):
        return any(tactic.is_assert for tactic in self.walk())

    @property
    def has_admit(self) -> bool:
        return any(tactic.is_admit for tactic in self.walk())

    @property
    def identifiers(self):
        return set(
            identifier for tactic in self.walk() for identifier in tactic.identifiers
        )


def read_tactics(src: str, max_commands: t.Optional[int] = None) -> t.List[Tactic]:
    ans: t.List[Tactic] = []

    current_command = ""
    current_start_idx = 0
    current_end_idx = 0

    comment_depth = 0
    in_quote = False
    current_position = 0
    line_number = 1

    def search_pat(pat: re.Pattern) -> t.Tuple[t.Optional[re.Match], int]:
        nonlocal src, current_position
        match = pat.search(src, current_position)
        return match, match.end() if match else len(src) + 1

    def append_to_result():
        nonlocal src, ans, current_command, line_number, current_start_idx, current_end_idx
        tactic = Tactic(src, current_start_idx, current_end_idx)
        assert (
            tactic.raw_text == current_command
        ), "Tactic text doesn't match the source text"
        ans.append(tactic)
        current_command = ""
        current_start_idx = current_end_idx

    while current_position < len(src) and (
        max_commands is None or len(ans) < max_commands
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

        # pick out the next chunk
        next_position = min(
            next_quote,
            next_open_comment,
            next_close_comment,
            next_bracket,
            next_bullet,
            next_period,
        )
        assert current_position < next_position

        next_chunk = src[current_position:next_position]
        current_command += next_chunk
        current_end_idx = next_position

        # update state based on the delimiter we just read
        if next_position == next_quote:
            if comment_depth == 0:
                in_quote = not in_quote
        elif next_position == next_open_comment:
            if not in_quote:
                comment_depth += 1
        elif next_position == next_close_comment:
            if not in_quote and comment_depth > 0:
                comment_depth -= 1
        elif next_position == next_bracket:
            if (
                not in_quote
                and comment_depth == 0
                and re.match(
                    r"\s*(?:\d+\s*:)?\s*$", kill_comments(current_command[:-1])
                )
            ):
                append_to_result()
        elif next_position == next_bullet:
            assert next_bullet_match
            match_length = next_bullet_match.end() - next_bullet_match.start()
            if (
                not in_quote
                and comment_depth == 0
                # i.e. removing the bullet from the command gives us whitespace
                and re.match(r"\s*$", kill_comments(current_command[:-match_length]))
            ):
                append_to_result()
            assert next_bullet_match.end() >= next_position
        elif next_position == next_period:
            if not in_quote and comment_depth == 0:
                append_to_result()

        current_position = next_position

    assert kill_comments(current_command).strip() == "", (
        "Couldn't parse command list! Are you sure you didn't forget an ending period?"
        + (src if len(src) < 64 else "[too long to print]")
    )
    return ans


def process_braces(tactics: t.List[Tactic]) -> ProofScript:
    scripts: t.List[t.List[t.Union[Tactic, ProofScript]]] = [[]]

    for tactic in tactics:
        if not tactic.is_open_brace and not tactic.is_close_brace:
            scripts[-1].append(tactic)
        elif tactic.is_open_brace:
            scripts.append([])
        elif tactic.is_close_brace:
            script = scripts.pop()
            scripts[-1].append(ProofScript(script))

    assert len(scripts) == 1, "Mismatched braces in proof script!"
    return ProofScript(scripts[0])


def process_bullets(script: ProofScript, current_bullet_level=0) -> ProofScript:
    bullets: t.List[str] = [""]
    bullet_scripts: t.Dict[str, t.List[t.Union[Tactic, ProofScript]]] = {"": []}

    def add_item(item: t.Union[Tactic, ProofScript], bullet: str):
        if bullet not in bullet_scripts:
            bullet_scripts[bullet] = []
        bullet_scripts[bullet].append(item)

    def next_bullet(bullet: str):
        try:
            bullet_idx = bullets.index(bullet)
        except ValueError as e:
            bullet_idx = -1

        if bullet_idx != -1:
            while len(bullets) > bullet_idx:
                bullet = bullets.pop()
                add_item(
                    ProofScript(bullet_scripts.pop(bullet)),
                    bullets[-1],
                )

        bullets.append(bullet)
        bullet_scripts[bullet] = []

    for item in script.contents:
        current_bullet = bullets[-1]
        if isinstance(item, ProofScript):
            add_item(
                process_bullets(item, current_bullet_level + len(bullets)),
                current_bullet,
            )
        elif not item.is_bullet:
            add_item(item, current_bullet)
        else:
            next_bullet(item.text)

    if len(bullets) > 1:
        next_bullet(bullets[1])

    return ProofScript(bullet_scripts[""])


def process_bullets_and_braces(
    tactics: t.List[Tactic], current_bullet_level=0
) -> ProofScript:
    bullets: t.List[str] = [""]
    bullet_scripts: t.Dict[str, t.List[t.Union[Tactic, ProofScript]]] = {"": []}

    def add_item(item: t.Union[Tactic, ProofScript], bullet: str):
        if bullet not in bullet_scripts:
            bullet_scripts[bullet] = []
        bullet_scripts[bullet].append(item)

    def start_next_bullet(bullet: str):
        try:
            bullet_idx = bullets.index(bullet)
        except ValueError as e:
            bullet_idx = -1

        if bullet_idx != -1:
            while len(bullets) > bullet_idx:
                bullet = bullets.pop()
                add_item(
                    ProofScript(bullet_scripts.pop(bullet)),
                    bullets[-1],
                )

        bullets.append(bullet)
        bullet_scripts[bullet] = []

    iterator = enumerate(tactics)
    while True:
        try:
            idx, tactic = next(iterator)
        except StopIteration as e:
            break

        current_bullet = bullets[-1]
        if tactic.is_bullet:
            start_next_bullet(tactic.text)
        elif tactic.is_open_brace:
            brace_contents = [tactic]
            num_open_braces = 1
            while num_open_braces > 0:
                try:
                    idx, tactic = next(iterator)
                except StopIteration as e:
                    raise Exception("Mismatched braces in proof script.")
                if tactic.is_open_brace:
                    num_open_braces += 1
                elif tactic.is_close_brace:
                    num_open_braces -= 1
                brace_contents.append(tactic)

            add_item(
                process_bullets_and_braces(
                    brace_contents[1:-1], current_bullet_level + len(bullets)
                ),
                current_bullet,
            )
        elif tactic.is_close_brace:
            raise Exception("Mismatched braces in proof script.")
        else:
            add_item(tactic, current_bullet)

    if len(bullets) > 1:
        start_next_bullet(bullets[1])

    return ProofScript(bullet_scripts[""])


def bullet_str(bullet_level: int) -> str:
    return "-" * bullet_level


def is_decomposition(context: c.contexts.ProofContext) -> bool:
    return len(context.fg_goals) > 1


class RunAdmittingFailedSubgoals:
    # args
    script: ProofScript
    coq: Coq
    bullet_level: int
    use_braces: bool
    try_hammer_on_error: bool
    admit_failed_subgoals: bool

    initial_context: c.contexts.ProofContext
    context: c.contexts.ProofContext

    prefix: t.List[t.Union[Tactic, ProofScript]]

    # None means there is no obligation for this bullet
    subgoal_obligations: t.List[t.Optional[c.contexts.Obligation]]
    subgoal_results: t.List[CoqPartialResult]
    subgoal_scripts: t.List[ProofScript]
    subgoal_executed_scripts: t.List[ProofScript]

    def __init__(
        self,
        script: ProofScript,
        coq: Coq,
        bullet_level: int = 0,
        use_braces: bool = False,
        try_hammer_on_error: bool = False,
        admit_failed_subgoals: bool = True,
    ):
        self.script = script
        self.coq = coq
        self.bullet_level = bullet_level
        self.use_braces = use_braces
        self.try_hammer_on_error = try_hammer_on_error
        self.admit_failed_subgoals = admit_failed_subgoals

        assert (
            coq.coq.proof_context is not None
        ), "Context should not be None before running proof script"
        self.context: c.contexts.ProofContext = coq.coq.proof_context

        self.prefix = []

        self.subgoal_obligations = []
        self.subgoal_results = []
        self.subgoal_scripts = []
        self.subgoal_executed_scripts = []

    def run(
        self,
    ) -> t.Generator[t.Tuple[Tactic, c.contexts.ProofContext], t.Any, CoqPartialResult]:
        """
        walks through the script, executing as many tactics as possible.
        if a tactic throws an error in a subgoal, it will admit the subgoal and continue.
        it yields the tactic and the context after each tactic is run.
        it returns the final result of the computation
        """

        LOGGER.info(
            "running script admitting failed subgoals",
            extra={
                "script": self.script.pretty_print(),
                "admit_failed_subgoals": self.admit_failed_subgoals,
                "try_hammer_on_error": self.try_hammer_on_error,
            },
        )

        try:
            if self.use_braces:
                brace = Tactic("{")
                yield from self.__run_tactic(brace, should_run_without_error=True)
            if self.bullet_level > 0:
                result = yield from self.__run_bullet_and_fix_mismatched_levels()
                if not isinstance(result, c.contexts.ProofContext):
                    return result

            # this guarantees us that the initial context focuses only 1 bullet
            self.initial_context = self.context
            assert (
                len(self.initial_context.fg_goals) == 1
            ), f"self.initial_context must have exactly one fg_goal. it has {len(self.initial_context.fg_goals)} fg_goals.\n\n{proof_context_to_str(self.initial_context)}\n\n{[o.goal for o in self.initial_context.fg_goals]}"

            for idx, item in enumerate(self.script.contents):
                if isinstance(item, Tactic):
                    result = yield from self.__run_tactic(item)
                    repair_result = yield from self.__repair_after_prefix_result(
                        item, result
                    )
                    if isinstance(repair_result, CoqError):
                        return repair_result
                    elif isinstance(repair_result, c.contexts.ProofContext):
                        # hammer succeeded, skip to the end.
                        break
                else:
                    # confirm that this subproof occurs at a decomposition point
                    if len(self.subgoal_obligations) == 0 and not is_decomposition(
                        self.context
                    ):
                        first_tactic = item.first_tactic()
                        LOGGER.error(
                            "Error running script with no goals to decompose",
                            extra={
                                "script": self.script.pretty_print(),
                                "first_tactic": first_tactic.text,
                                "line_number": first_tactic.start_line_number,
                            },
                        )
                        return CoqError(
                            "No subgoals to focus",
                            first_tactic.text,
                            first_tactic.start_line_number,
                            self.context,
                        )

                    # concatenate fg and bg goals because we might have finished all the
                    # fg goals and are now working on the first bg goal
                    remaining_goals = self.context.fg_goals + self.context.bg_goals
                    if len(remaining_goals) == 0:
                        # we no longer have any goals, but we're trying to run a script. skip it
                        self.__add_subgoal(None, Skip(), item, ProofScript([]))
                        continue

                    rest = self.script.contents[idx + 1 :]
                    in_prefix = not all(isinstance(x, ProofScript) for x in rest)
                    admit_failed_subgoals = (
                        False if in_prefix else self.admit_failed_subgoals
                    )
                    generator = RunAdmittingFailedSubgoals(
                        item,
                        self.coq,
                        bullet_level=(self.bullet_level + 1) if not in_prefix else 0,
                        use_braces=in_prefix,
                        try_hammer_on_error=self.try_hammer_on_error,
                        admit_failed_subgoals=admit_failed_subgoals,
                    ).run()
                    yielded, result = yield from step_generator_and_save_yields(
                        generator
                    )

                    executed_tactics = [
                        tactic
                        for idx, (tactic, _) in enumerate(yielded)
                        if not (
                            (idx == 0 and tactic.is_bullet)
                            or (idx == 0 and in_prefix and tactic.is_open_brace)
                            or (
                                idx == len(yielded) - 1
                                and in_prefix
                                and tactic.is_close_brace
                            )
                        )
                    ]
                    executed_script = ProofScript.from_tactics(executed_tactics)

                    if len(yielded) > 0:
                        self.context = yielded[-1][1]

                    if not admit_failed_subgoals:
                        assert isinstance(
                            result, c.contexts.ProofContext
                        ) or isinstance(
                            result, CoqError
                        ), f"Because we aren't admitting failed subgoals, result should only be a context or an error, but got {result}"

                    if in_prefix:
                        repair_result = yield from self.__repair_after_prefix_result(
                            executed_script, t.cast(CoqResult, result)
                        )
                        if isinstance(repair_result, CoqError):
                            return repair_result
                        elif isinstance(repair_result, c.contexts.ProofContext):
                            # hammer succeeded, skip to the end.
                            break
                    else:
                        # set self.context to the right context to continue executing
                        if isinstance(result, CoqError):
                            if not self.admit_failed_subgoals:
                                return result
                            # the error should have been admitted here, so we will use the
                            # context from the coq object which should be a good context to continue from
                            assert (
                                self.coq.coq.proof_context
                            ), "Context should not be None after admitting errored section"
                            self.context = self.coq.coq.proof_context
                        elif isinstance(result, c.contexts.ProofContext):
                            self.context = result
                        elif isinstance(result, CoqPartialSuccess):
                            self.context = result.end_context

                        self.__add_subgoal(
                            remaining_goals[0],
                            result,
                            item,
                            ProofScript.from_tactics(executed_tactics),
                        )

            # if the current proof isn't finished, count this result as an error.
            if len(self.context.fg_goals) > 0:
                error: CoqError = self.__get_error_for_unfinished_proof()
                return error

            # for each extra goal, find the right bullet level and admit it.
            # TODO: blow up if this runs more than 10 times?
            while len(additional_bg_goals(self.initial_context, self.context)) > 0:
                yield from self.__admit_additional_bg_goal()

            assert is_initial_goal_proven(
                self.initial_context, self.context, None, ignore_given_up_goals=True
            ), f"Initial goal not proven. The script may have introduced new goals that were not proven or admitted.\n\n# initial context\n{proof_context_to_str(self.initial_context)}\n\n# current context\n{proof_context_to_str(self.context)}"

            # if this script didn't decompose, we succeeded
            if len(self.subgoal_obligations) == 0:
                return self.context

            # otherwise, we decomposed. return the decomposition
            ans = CoqPartialSuccess(
                ProofScript(
                    t.cast(t.List[t.Union[Tactic, "ProofScript"]], self.prefix)
                ),
                self.subgoal_obligations,
                self.subgoal_results,
                self.subgoal_scripts,
                self.subgoal_executed_scripts,
                self.context,
            )

            if ans.is_success:
                return self.context
            else:
                return ans

        finally:
            if self.use_braces:
                brace = Tactic("}")
                # I left "should run without error" as False here because an error in the script might make it hard to close the brace.
                yield from self.__run_tactic(brace)

    def __run_bullet_and_fix_mismatched_levels(self) -> t.Generator[
        t.Tuple[Tactic, c.contexts.ProofContext],
        t.Any,
        t.Union[CoqError, Skip, c.contexts.ProofContext],
    ]:
        """
        attempts to run the bullet tactic at the given level,
        admitting any subgoals that are at a lower level than the bullet level,
        and skipping if a higher level bullet is expected
        """
        assert self.bullet_level > 0, "Bullet level must be greater than 0"

        # handle mismatched bullet levels
        while True:
            tactic = Tactic(bullet_str(self.bullet_level))
            result = yield from self.__run_tactic(tactic)
            if isinstance(result, c.contexts.ProofContext):
                break

            if result.expected_bullet is None:
                return result

            expected_bullet_depth = len(result.expected_bullet)
            # a higher than expected bullet should have been handled in a previous script.
            assert (
                expected_bullet_depth < self.bullet_level
            ), f'expected bullet level "{expected_bullet_depth}" must be less than the current bullet level "{self.bullet_level}"'

            return Skip()

        return self.context

    def __get_error_for_unfinished_proof(self) -> CoqError:
        if self.use_braces:
            closing_tactic = Tactic("}")
        elif self.bullet_level == 0:
            # TODO: technically, Qed. is not a tactic. this is a hack to get the thing to work
            closing_tactic = Tactic("Qed.")
        else:
            closing_tactic = Tactic(self.__bullet_str)

        result = closing_tactic.run(self.coq)
        assert isinstance(
            result, CoqError
        ), "We should have gotten an error here, as the initial goal was not proven"
        return result

    def __repair_after_prefix_result(
        self, item: t.Union[Tactic, ProofScript], result: CoqResult
    ) -> t.Generator[
        t.Tuple[Tactic, c.contexts.ProofContext], t.Any, t.Optional[CoqResult]
    ]:
        """
        attempts to repair the proof state after a prefix result
        """
        if isinstance(result, c.contexts.ProofContext):
            self.prefix.append(item)
            return None

        if isinstance(item, ProofScript):
            item.revert(self.coq)

        ans = result
        # if we somehow errored out of the proof itself, don't try to repair
        if ans.context is None:
            return ans

        # if we actually successfully proved with the prefix, treat this as a success
        if is_initial_goal_proven(self.initial_context, self.context, None, True):
            return self.context

        # try hammer here. if it works, the result is actually a success
        if self.try_hammer_on_error:
            result = yield from self.__run_hammer()
            if isinstance(result, c.contexts.ProofContext):
                return result

        if self.bullet_level > 0 and self.admit_failed_subgoals:
            # admit, so that the next proof state is in good shape
            admit = Tactic("admit.")
            yield from self.__run_tactic(admit, should_run_without_error=True)

        # still return the result as an error
        return ans

    def __admit_additional_bg_goal(self):
        num_bg_goals = len(self.context.bg_goals)

        # TODO: assuming I'll only ever encounter a bg goal for bullet level + 1. is this the case?
        expected_bullet = bullet_str(self.bullet_level + 1)

        obligation = self.context.bg_goals[0]
        yield from self.__run_tactic(
            Tactic(expected_bullet), should_run_without_error=True
        )
        yield from self.__run_tactic(Tactic("admit."), should_run_without_error=True)

        self.__add_subgoal(obligation, Skip(), ProofScript([]), ProofScript([]))

        assert (
            len(self.context.bg_goals) == num_bg_goals - 1
        ), f"Expected admitting a bg goal to remove one bg goal from {num_bg_goals}, but got {len(self.context.bg_goals)} bg goals"

    def __add_subgoal(
        self,
        obligation: t.Optional[c.contexts.Obligation],
        result: CoqPartialResult,
        script: ProofScript,
        executed_script: ProofScript,
    ):
        self.subgoal_obligations.append(obligation)
        self.subgoal_results.append(result)
        self.subgoal_scripts.append(script)
        self.subgoal_executed_scripts.append(executed_script)

    def __run_tactic(
        self,
        tactic: Tactic,
        should_run_without_error: bool = False,
    ) -> t.Generator[t.Tuple[Tactic, c.contexts.ProofContext], t.Any, CoqResult]:
        result = tactic.run(self.coq)
        if should_run_without_error:
            assert isinstance(
                result, c.contexts.ProofContext
            ), f"Tactic {tactic.text} should run without error"
        if isinstance(result, c.contexts.ProofContext):
            self.context = result
            yield tactic, self.context
        return result

    def __run_hammer(
        self,
    ) -> t.Generator[t.Tuple[Tactic, c.contexts.ProofContext], t.Any, CoqResult]:
        result, reconstruction_tactic = Tactic(
            "hammer."
        ).run_hammer_and_get_reconstruction_tactic(self.coq)

        if isinstance(result, c.contexts.ProofContext):
            assert (
                reconstruction_tactic is not None
            ), "no reconstruction tactic for successful hammer run. try raising the verbosity of coq_serapy.CoqSeraPyInstance to 4."
            self.context = result
            yield reconstruction_tactic, self.context
        return result

    @property
    def __bullet_str(self) -> str:
        return bullet_str(self.bullet_level)
