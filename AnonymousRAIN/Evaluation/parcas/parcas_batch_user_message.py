"""User message for Parcas batch runs (ProofAgent, OpenCode, Claude Code)."""

from __future__ import annotations

_TASK_INTRO = (
    "In {target_coq_file}, there is a theorem containing Admitted. Complete the theorem such that "
    "running make in the project root directory succeeds. Note that you must not modify the statements "
    "of the theorems, and you are not allowed to use Admitted, Abort, Axiom, or similar constructs to "
    "bypass the proofs. "
)

_ACCESS_PROJECT_ONLY = (
    "You may only access the current project; access to any other local files or "
    "external resources, including the internet, is strictly prohibited. "
)

_ACCESS_PROJECT_AND_PARCAS_OPAM_COQ = (
    "You may read source files only under the project root directory and under "
    "~/.opam/parcas/lib/coq; reading code from any other local path is strictly prohibited. Access to "
    "external resources, including the internet, is strictly prohibited. "
)

_CLOSING = (
    "I am testing your proving ability, so do not attempt to look for answers elsewhere. "
    "All responses must be in English. Finally, only "
    'output: whether it is successful. If successful, provide the generated proofs; if failed, only output '
    '"failed".'
)


def format_parcas_batch_user_message(target_coq_file: str) -> str:
    """OpenCode / Claude Parcas: project + Parcas OPAM Coq lib."""
    return (
        _TASK_INTRO.format(target_coq_file=target_coq_file)
        + _ACCESS_PROJECT_AND_PARCAS_OPAM_COQ
        + _CLOSING
    )


def format_parcas_proofagent_batch_user_message(target_coq_file: str, *, extra_read: bool) -> str:
    """ProofAgent Parcas: OPAM Coq lib path only when --extra-read is set."""
    access_rule = (
        _ACCESS_PROJECT_AND_PARCAS_OPAM_COQ
        if extra_read
        else _ACCESS_PROJECT_ONLY
    )
    return _TASK_INTRO.format(target_coq_file=target_coq_file) + access_rule + _CLOSING
