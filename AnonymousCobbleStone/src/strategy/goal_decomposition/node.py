from dataclasses import dataclass
import typing as t
import coq_serapy as c
import traceback
from itertools import product, zip_longest

from .utils import (
    LOGGER,
    GoalDecomposition,
    GoalDecompositionConfig,
    GoalDecompositionNode__ValueJSON,
    GoalDecompositionNodeJSON,
    mark_session_wall_budget_exhausted_if_past_deadline,
)

from src.agent import Agent
from src.utils import JSON, run_generator_and_save_yields
from src.premise_selection import select_premises
from src.coq_serapy_util import (
    CoqError,
    is_initial_goal_proven,
    obligation_summary,
    proof_context_to_str,
)
from src.tree_search import Node
from src.environment import Environment, EditAction
from src.dataset import Example
from src.coq_serapy_util import LemmaLocation
from src.llm import Usage, UsageError
from src.proof_script import (
    CoqPartialResult,
    CoqPartialSuccess,
    ProofScript,
    Skip,
    Tactic,
)


@dataclass(frozen=True)
class GoalDecompositionNode__Value:
    obligation: c.contexts.Obligation
    decomposition: t.Optional[GoalDecomposition]
    example: Example
    proof_prefix: t.Optional[ProofScript]

    def to_json(self) -> GoalDecompositionNode__ValueJSON:
        return {
            "obligation": self.obligation.to_dict(),
            "decomposition": (
                None if self.decomposition is None else self.decomposition.to_json()
            ),
            "proof_prefix": (
                self.proof_prefix.to_json() if self.proof_prefix is not None else None
            ),
        }

    @classmethod
    def from_json(
        cls, json: t.Dict[str, JSON], example: Example
    ) -> "GoalDecompositionNode__Value":
        proof_prefix = (
            None
            if json.get("proof_prefix", None) is None
            else ProofScript.from_json(t.cast(str, json["proof_prefix"]))
        )

        return cls(
            obligation=c.contexts.Obligation.from_dict(json["obligation"]),
            decomposition=(
                None
                if json["decomposition"] is None
                else GoalDecomposition.from_json(
                    t.cast(t.Dict[str, JSON], json["decomposition"])
                )
            ),
            example=example,
            proof_prefix=proof_prefix,
        )


class GoalDecompositionNode(Node[GoalDecompositionNode__Value]):
    parent: t.Optional["GoalDecompositionNode"]
    config: GoalDecompositionConfig
    usage: Usage

    __proof: t.Optional[ProofScript]
    failed_attempts: t.List[str]
    attempts: t.List[str]

    # the indexes of decompositions correspond to the indexes of children
    decompositions: t.List[GoalDecomposition]
    children: t.List[t.List["GoalDecompositionNode"]]

    lemmas: t.Optional[t.List[str]]

    tried_hammer: bool = False

    def __init__(
        self,
        value: GoalDecompositionNode__Value,
        parent: Node | None,
        config: GoalDecompositionConfig,
        uuid: t.Optional[str] = None,
    ):
        super().__init__(value, parent, uuid)
        self.__proof = None
        self.decompositions = []
        self.children = []
        self.lemmas = None
        self.config = config
        self.failed_attempts = []
        self.attempts = []
        self.usage = Usage(name="goal_decomposition_node")

    # the way this node is serialized, its children come after it in the list
    def to_json(self) -> t.List[GoalDecompositionNodeJSON]:
        self_json: GoalDecompositionNodeJSON = {
            "uuid": self.uuid,
            "parent_uuid": self.parent.uuid if self.parent is not None else None,
            "value": self.value.to_json(),
            "depth": self.depth,
            "num_failed_attempts_to_generate_children": self.num_failed_attempts_to_generate_children,
            "children_uuids": [
                [child.uuid for child in children] for children in self.children
            ],
            "decompositions": [
                decomposition.to_json() for decomposition in self.decompositions
            ],
            "proof": self.__proof.to_json() if self.__proof is not None else None,
            "lemmas": self.lemmas,
            "attempts": self.attempts,
            "failed_attempts": self.failed_attempts,
        }

        children_json = [
            child.to_json() for children in self.children for child in children
        ]

        flat_children_json = [
            child_json
            for children_json in children_json
            for child_json in children_json
        ]

        return [self_json] + flat_children_json

    # this from_json method requires children to be deserialized before parents
    @classmethod
    def from_json(
        cls,
        # a reversed version of the serialized list, with
        # children before parents
        jsons: t.List[t.Dict[str, JSON]],
        nodes: t.Dict[str, "GoalDecompositionNode"],
        config: GoalDecompositionConfig,
        example: Example,
    ) -> t.Dict[str, "GoalDecompositionNode"]:
        json = jsons.pop(0)

        node = cls(
            GoalDecompositionNode__Value.from_json(
                t.cast(t.Dict[str, JSON], json["value"]), example
            ),
            None,
            config,
            t.cast(str, json["uuid"]),
        )
        node.depth = t.cast(int, json["depth"])
        node.num_failed_attempts_to_generate_children = t.cast(
            int, json["num_failed_attempts_to_generate_children"]
        )
        node.children = [
            [nodes[uuid] for uuid in children_uuids]
            for children_uuids in t.cast(t.List[t.List[str]], json["children_uuids"])
        ]
        for children in node.children:
            for child in children:
                child.parent = node

        node.decompositions = [
            GoalDecomposition.from_json(decomposition)
            for decomposition in t.cast(
                t.List[t.Dict[str, JSON]], json["decompositions"]
            )
        ]
        node.__proof = (
            None
            if json.get("proof", None) is None
            else ProofScript.from_json(t.cast(str, json["proof"]))
        )
        node.lemmas = t.cast(t.Optional[t.List[str]], json["lemmas"])

        node.attempts = t.cast(t.List[str], json.get("attempts", []))
        node.failed_attempts = t.cast(t.List[str], json.get("failed_attempts", []))

        nodes = {**nodes, node.uuid: node}

        if len(jsons) > 0:
            return cls.from_json(jsons, nodes, config, example)
        else:
            return nodes

    @property
    def proof(self) -> t.Optional[ProofScript]:
        if self.__proof is not None:
            return self.__proof

        if not any(
            all(goal.proven for goal in decomposition_children)
            for decomposition_children in self.children
        ):
            return None

        proven_decomposition, proven_children = next(
            (
                (decomposition, children)
                for decomposition, children in zip(self.decompositions, self.children)
                if all(goal.proven for goal in children)
            ),
            (None, None),
        )

        assert proven_decomposition is not None
        assert proven_children is not None

        return ProofScript(
            list(proven_decomposition.proofs)[0].contents
            + [
                # each child must have a proof for it to be a proven decomposition
                t.cast(ProofScript, child.proof)
                for child in proven_children
            ]
        )

    @proof.setter
    def proof(self, proof: ProofScript) -> None:
        environment = self.__make_environment()
        result = proof.run_until_end_or_error(environment.coq)
        if proof.has_admit:
            LOGGER.error(
                "proof script has an admit",
                extra={
                    "proof": proof.pretty_print(),
                    "result": result,
                    "goal": self.value.obligation.goal,
                },
            )
            raise ValueError("proof script has an admit.")
        if not isinstance(result, c.contexts.ProofContext):
            LOGGER.error(
                "proof script did not prove goal",
                extra={
                    "proof": proof.pretty_print(),
                    "result": result,
                    "goal": self.value.obligation.goal,
                },
            )
            raise ValueError("proof script did not prove goal")
        if not is_initial_goal_proven(
            environment.initial_proof_context, result, None, ignore_given_up_goals=True
        ):
            LOGGER.error(
                "proof script did not prove goal",
                extra={
                    "proof": proof.pretty_print(),
                    "result": result,
                    "goal": self.value.obligation.goal,
                },
            )
            raise ValueError("proof script did not prove goal")

        self.__proof = proof

    @property
    def proven(self) -> bool:
        return self.proof is not None

    def _generate_new_children(
        self, discard_children: bool
    ) -> t.Optional[t.List["GoalDecompositionNode"]]:
        LOGGER.info(f"generating new children for {self.value.obligation.goal}")

        # make sure we try to hammer away the root
        if self.parent is None:
            self.__try_hammer()

        if mark_session_wall_budget_exhausted_if_past_deadline(self.config):
            return None

        if self.proven:
            return []

        environments = self.__run_agents()
        if mark_session_wall_budget_exhausted_if_past_deadline(self.config):
            return None
        childrens = [
            self.__make_children_from_environment(environment, discard_children)
            for environment in environments
        ]
        # if all are none, we completely failed and should count it as a failure
        if all(child is None for child in childrens):
            return None

        # try hammering away children so that we don't have to expand them
        for children in childrens:
            if children is not None:
                for child in children:
                    child.__try_hammer()

        return [
            child
            for children in childrens
            if children is not None
            for child in children
        ]

    def is_goal(self) -> t.Optional[bool]:
        """
        Always returns False, because no individual node, even if proven, is a goal. We conduct the search until the root node is proven.
        """
        if self.proven:
            return True
        else:
            # we don't know if the node is a goal, as it could be proven
            # the only way a node is actually not a goal is if it's proven false, which we currently don't do
            return None

    @property
    def num_children(self) -> int:
        return len(self.children)

    @property
    def children_to_visualize(self) -> t.List[t.Union["GoalDecompositionNode", str]]:
        """
        conceputally, the children of this node are "goal decompositions".
        But here, we flatten the decompositions into a list of nodes
        for visualization purposes.
        """
        ans: t.List[t.Union["GoalDecompositionNode", str]] = []
        if self.proven and self.__proof is not None:
            ans.append(f"# successful proof: {self.__proof}")

        for idx, child in enumerate(self.children):
            goal_decomposition = self.decompositions[idx]
            proof_example = list(goal_decomposition.proofs)[0].pretty_print()
            ans.append(
                f"# {len(goal_decomposition.proofs)} prefixes like {proof_example}"
            )
            ans.extend(child)

        return ans

    @property
    def label(self) -> str:
        """
        returns a string representation of the goal
        """
        return (
            obligation_summary(self.value.obligation)
            if not self.proven
            else f"{obligation_summary(self.value.obligation)} (proven)"
        )

    def ancestors(self) -> t.Generator["GoalDecompositionNode", t.Any, None]:
        node = self.parent
        while node is not None:
            yield node
            node = node.parent

    @property
    def redundant_to_ancestor(self) -> bool:
        def is_redundant(
            o_prime: c.contexts.Obligation, o: c.contexts.Obligation
        ) -> bool:
            # no need to alpha normalize if comparing with the same variable names
            # i.e. not accross decompositions
            return o_prime.goal == o.goal and all(
                hypothesis in o.hypotheses for hypothesis in o_prime.hypotheses
            )

        return any(
            is_redundant(self.value.obligation, ancestor.value.obligation)
            for ancestor in self.ancestors()
        )

    @property
    def same_goal_as_ancestor(self) -> bool:
        return any(
            self.value.obligation.goal == ancestor.value.obligation.goal
            for ancestor in self.ancestors()
        )

    def decomposition_nodes(
        self, decomposition: GoalDecomposition
    ) -> t.List["GoalDecompositionNode"]:
        """
        returns all nodes that are part of the given decomposition
        """
        idx = self.decompositions.index(decomposition)
        return self.children[idx]

    def decomposition_sibling_nodes(self) -> t.List["GoalDecompositionNode"]:
        """
        returns all nodes (including this node) that are part of the same decomposition
        """
        if self.value.decomposition is None:
            return [self]

        if self.parent is None:
            return [self]

        idx = self.parent.decompositions.index(self.value.decomposition)
        return self.parent.children[idx]

    @property
    def proof_prefix_with_open_brace(self) -> t.Optional[str]:
        if self.value.proof_prefix is None:
            return None

        # using a curly brace like this should help us avoid any errors associated with
        # incorrect bullet levels generated by the LLM
        return self.value.proof_prefix.pretty_print() + " { "

    def __make_environment(self):
        _, ans = self.config.make_agent_and_environment(
            False,
            False,
            # ---
            self.value.example.proposition_command,
            None,
            self.value.example.location,
            self.proof_prefix_with_open_brace,
        )
        return ans

    def __try_hammer(self):
        """
        attempt to prove the goal with the hammer tactic
        If the tactic is successful, then this node is set to proven, and will be expanded no further. This method will return the successful environment.
        If the tactic fails, this method will return None.
        """
        if not self.config.try_hammer:
            return
        if self.tried_hammer:
            return

        LOGGER.info(
            "trying hammer",
            extra={
                "goal": self.value.obligation.goal,
                "prefix": self.proof_prefix_with_open_brace,
            },
        )
        environment = self.__make_environment()

        try:
            environment.step(EditAction(new_code=f"hammer."))

            if environment.is_initial_goal_proven:
                self.__proof = ProofScript([Tactic("hammer.")])
                LOGGER.info(
                    "successfully proved goal with hammer",
                    extra={"goal": self.value.obligation.goal, "proof": self.__proof},
                )
            else:
                LOGGER.info(
                    "failed to prove goal with hammer",
                    extra={"goal": self.value.obligation.goal},
                )
        except Exception as e:
            LOGGER.error(
                "failed to prove goal with hammer due to exception",
                extra={
                    "exception": e,
                    "goal": self.value.obligation.goal,
                    "traceback": traceback.format_exc(),
                },
            )
            return None
        finally:
            self.tried_hammer = True

    def __run_agents(self) -> t.List[t.Optional[Environment]]:
        """
        attempts to prove the current goal by running an ensemble of agents.
        Returns a list of environments, one for each agent's result
        """
        ans: t.List[t.Optional[Environment]] = []

        for include_lemma_context, include_reasoning in product(
            [True, False], repeat=2
        ):
            if mark_session_wall_budget_exhausted_if_past_deadline(self.config):
                break
            try:

                def make_agent_and_environment(
                    proposition_command: str,
                    hint: t.Optional[str],
                    lemma_location: t.Optional[LemmaLocation] = None,
                    _: t.Optional[str] = None,
                ) -> t.Tuple[Agent, Environment]:
                    agent, environment = self.config.make_agent_and_environment(
                        include_lemma_context,
                        include_reasoning,
                        # ---
                        proposition_command,
                        hint,
                        lemma_location,
                        self.proof_prefix_with_open_brace,
                    )
                    if include_lemma_context:
                        self.__add_lemmas(environment)
                    return agent, environment

                LOGGER.info(
                    "running strategy",
                    {
                        "goal": self.value.obligation.goal,
                        "include_lemma_context": include_lemma_context,
                        "include_reasoning": include_reasoning,
                    },
                )
                environment, usage = self.config.run_strategy(
                    self.value.example, make_agent_and_environment
                )
                self.root.usage.add_child(usage)
                LOGGER.debug("usage", extra={"usage": usage})

                ans.append(environment)

                # exit early if we successfully proved this goal
                if environment is not None and environment.is_initial_goal_proven:
                    break
            except UsageError as e:
                self.root.usage.add_child(e.usage)
                LOGGER.error(
                    "failed to prove goal after LLM usage; preserving usage",
                    extra={
                        "exception": e,
                        "goal": self.value.obligation.goal,
                        "traceback": traceback.format_exc(),
                        "include_lemma_context": include_lemma_context,
                        "include_reasoning": include_reasoning,
                        "usage": e.usage,
                    },
                )
            except Exception as e:
                LOGGER.error(
                    "failed to prove goal due to exception",
                    extra={
                        "exception": e,
                        "goal": self.value.obligation.goal,
                        "traceback": traceback.format_exc(),
                        "include_lemma_context": include_lemma_context,
                        "include_reasoning": include_reasoning,
                    },
                )

        return ans

    def __make_children_from_environment(
        self, environment: t.Optional[Environment], discard_children: bool
    ) -> t.Optional[t.List["GoalDecompositionNode"]]:
        """
        returns a list of new children nodes, or None if no children were generated
        """
        # TODO: since this is called multiple times in a single expansion,
        #   each failure should count as one failed attempt
        if environment is None:
            LOGGER.info(
                "failed to attempt proving goal (no environment returned)",
                extra={
                    "num_failed_attempts": self.num_failed_attempts_to_generate_children,
                    "goal": self.value.obligation.goal,
                },
            )
            return None

        # TODO: do we need this? won't it be covered by line 526?
        if environment.is_initial_goal_proven:
            self.attempts.append(environment.observation_code)

            self.proof = ProofScript.parse(environment.observation_code)
            LOGGER.info(
                "proved goal",
                extra={"goal": self.value.obligation.goal, "proof": self.__proof},
            )
            return []

        # if we're discarding children, skip computing a goal decomposition
        if discard_children:
            return None

        try:
            code = environment.observation_code
            script = ProofScript.parse(code)
        except Exception as e:
            LOGGER.error(
                "failed to parse observation code",
                extra={
                    "exception": e,
                    "observation_code": environment.observation_code,
                    "goal": self.value.obligation.goal,
                },
            )
            return None

        fresh_environment = self.__make_environment()
        coq = fresh_environment.coq
        proof_script = ProofScript.parse(code)

        try:
            yields, result = run_generator_and_save_yields(
                proof_script.run_admitting_failed_subgoals(
                    coq, try_hammer_on_error=self.config.try_hammer
                ),
                max_steps=1_000,
            )
            executed_tactics = [tactic for tactic, _ in yields]
        except AssertionError as e:
            LOGGER.error(
                "assertion error while running script admitting failed subgoals",
                extra={
                    "exception": e,
                    "goal": self.value.obligation.goal,
                    "script": script.pretty_print(),
                },
            )
            result = CoqError(
                "assertion error while running script admitting failed subgoals",
                "Qed.",
                0,
                None,
            )

        LOGGER.info(
            "ran script admitting failed subgoals",
            extra={
                "result": (
                    result
                    if not isinstance(result, c.contexts.ProofContext)
                    else proof_context_to_str(result)
                ),
                "resultClass": result.__class__.__name__,
                "goal": self.value.obligation.goal,
                "script": script.pretty_print(),
            },
        )
        if isinstance(result, CoqPartialSuccess):
            return self.__process_partial_result(script, result)
        elif isinstance(result, c.contexts.ProofContext):
            # the actual script that worked may not be `script`, since we might run hammers on error
            return self.__process_partial_result(
                ProofScript.from_tactics(executed_tactics), result
            )

        fresh_environment = self.__make_environment()
        coq = fresh_environment.coq
        result = proof_script.run_until_goal_decomposition(coq)
        LOGGER.info(
            "ran script until goal decomposition",
            extra={
                "result": result,
                "goal": self.value.obligation.goal,
                "script": script.pretty_print(),
            },
        )

        return self.__process_partial_result(script, result)

    def __process_partial_result(
        self, script: ProofScript, result: CoqPartialResult
    ) -> t.Optional[t.List["GoalDecompositionNode"]]:
        """
        None -> failed to decompose
        [] -> successfully decomposed, no children
        [children] -> successfully decomposed, children
        """
        LOGGER.info(
            "processing partial result",
            extra={
                "goal": self.value.obligation.goal,
                "result": (
                    result
                    if not isinstance(result, c.contexts.ProofContext)
                    else proof_context_to_str(result)
                ),
                "script": script.pretty_print(),
            },
        )

        if isinstance(result, Skip):
            # it may be odd to think that an un-run script should be considered a failure.
            # however, I suspect that we should only see a Skip show up as a subgoal
            # if the script has too few tactics to run, and so we should consider it a failure to expand
            return None

        self.attempts.append(script.pretty_print())

        if isinstance(result, CoqError):
            self.failed_attempts.append(script.pretty_print())
            return None

        if isinstance(result, c.contexts.ProofContext):
            self.proof = script
            return []

        return self.__process_partial_success(result)

    def __process_partial_success(
        self, result: CoqPartialSuccess
    ) -> t.Optional[t.List["GoalDecompositionNode"]]:
        """
        None -> failed to decompose or existing decomposition
        [] -> successfully decomposed, no children
        [children] -> successfully decomposed, children
        """

        # these may not all be immediate children of this node
        # since children are added in __merge_goal_decomposition, we don't need to
        # worry about differentiating immediate children from other children
        # we just want to make sure that we return children in the order they are created.
        new_nodes: t.List["GoalDecompositionNode"] = []

        new_or_existing, decomposition, decomposition_nodes = (
            self.__merge_goal_decomposition(
                GoalDecomposition.from_partial_success(result)
            )
        )

        if new_or_existing == "new":
            new_nodes += decomposition_nodes

        for (
            decomp_node,
            decomp_result,
            decomp_script,
            decomp_executed_script,
        ) in zip_longest(
            decomposition_nodes,
            result.subgoal_results,
            result.subgoal_scripts,
            result.subgoal_executed_scripts,
            fillvalue=None,
        ):
            if (
                decomp_node is None
                or decomp_result is None
                or decomp_script is None
                or decomp_executed_script is None
            ):
                continue
            subgoal_new_nodes = decomp_node.__process_partial_result(
                # sometimes, execution runs a slightly different script than what was written. if we succeed, we use what actually worked
                (
                    decomp_executed_script
                    if isinstance(decomp_result, c.contexts.ProofContext)
                    else decomp_script
                ),
                decomp_result,
            )
            if subgoal_new_nodes is not None:
                new_nodes += subgoal_new_nodes

        return new_nodes

    def __add_lemmas(self, environment: Environment) -> None:
        if self.config.lemma_context not in [
            "preceding-lemmas-and-selected-premises",
            "perfect-premises",
        ]:
            return

        if self.lemmas is None:
            if self.config.premise_names is not None:
                self.lemmas = environment.coq.get_lemmas_for_identifiers(
                    self.config.premise_names
                )
                LOGGER.debug(
                    "perfect premise selection premises",
                    extra={
                        "lemmas": self.lemmas,
                        "premise_names": self.config.premise_names,
                    },
                )
            else:
                self.lemmas, premise_selection_usage = select_premises(
                    environment.base_observation,
                    environment.coq,
                    include_reasoning=True,
                    n_identifiers=5,
                )
                self.root.usage.add_child(premise_selection_usage)

        if self.config.premise_names is not None:
            environment.clear_lemmas()
        LOGGER.debug("adding lemmas", extra={"lemmas": self.lemmas})
        environment.add_lemmas(self.lemmas)

    def __merge_goal_decomposition(
        self, goal_decomposition: GoalDecomposition
    ) -> t.Tuple[
        t.Literal["new", "existing"], GoalDecomposition, t.List["GoalDecompositionNode"]
    ]:
        """
        merges the given goal decomposition into this node and
        returns a new child node
        """

        # if we've discovered a new path to an existing decomposition, then we don't need to create a new child, just add the path to the existing decomposition
        matching_decomposition = next(
            (
                decomposition
                for decomposition in self.decompositions
                if decomposition == goal_decomposition
            ),
            None,
        )
        if matching_decomposition is not None:
            LOGGER.info(
                "found existing decomposition",
                extra={
                    "goal": self.value.obligation.goal,
                    "tactics": list(goal_decomposition.proofs)[0].pretty_print(),
                    "decomposition": matching_decomposition,
                },
            )
            matching_decomposition.proofs = matching_decomposition.proofs.union(
                goal_decomposition.proofs
            )
            return (
                "existing",
                matching_decomposition,
                self.decomposition_nodes(matching_decomposition),
            )

        # if the decomposition is truly new, then add it to our list of decompositions and create a new child node for each of its goals

        goal_decomposition_tactics = list(goal_decomposition.proofs)[0]
        children = []

        for idx, obligation in enumerate(goal_decomposition.goals):
            child = GoalDecompositionNode(
                GoalDecompositionNode__Value(
                    obligation,
                    goal_decomposition,
                    self.value.example,
                    self.__compute_child_proof_prefix(
                        goal_decomposition_tactics,
                        num_preceding_siblings=idx,
                    ),
                ),
                self,
                self.config,
            )
            children.append(child)

        self.decompositions.append(goal_decomposition)
        self.children.append(children)

        LOGGER.info(
            "found new decomposition",
            extra={
                "goal": self.value.obligation.goal,
                "tactics": list(goal_decomposition.proofs)[0].pretty_print(),
                "decomposition": goal_decomposition,
            },
        )

        return ("new", goal_decomposition, children)

    def __compute_child_proof_prefix(
        self,
        goal_decomposition_tactics: ProofScript,
        num_preceding_siblings: int,
    ) -> ProofScript:
        prefix = (
            self.value.proof_prefix.contents
            if self.value.proof_prefix is not None
            else []
        )

        return ProofScript(
            prefix
            + goal_decomposition_tactics.contents
            + [Tactic("admit.") for i in range(num_preceding_siblings)]
        )
