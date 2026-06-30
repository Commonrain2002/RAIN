import typing as t
from uuid import uuid4
import click

from src.utils import set_run_uuid
from src.config import CONFIG, DEFAULT_CHAT_MODEL
from src.llm.model_names import OpenaiChatModelName, OPENAI_CHAT_MODEL_NAMES
from .utils import DATASET_NAMES, LEMMA_CONTEXTS
from .goal_decomposition import GoalDecompositionEval


@click.group()
def cli():
    pass


@cli.command(help="run goal decomposition on the datset")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset to run goal decomposition on",
)
@click.option(
    "-l",
    "--lemma",
    type=str,
    required=False,
    multiple=True,
    help="a specific lemma in the dataset. If specified, only run goal decomposition for this lemma",
)
@click.option(
    "-t",
    "--try-hammer",
    is_flag=True,
    help="try to prove the lemma with hammer",
)
@click.option(
    "-c",
    "--context",
    type=click.Choice(LEMMA_CONTEXTS),
    default="preceding-lemmas-only",
    help="the context to use when sampling",
)
@click.option(
    "-m",
    "--max-depth",
    type=int,
    default=5,
    help="the maximum depth to search for a proof",
)
@click.option(
    "-o",
    "--model",
    type=click.Choice(OPENAI_CHAT_MODEL_NAMES),
    default=DEFAULT_CHAT_MODEL,
    help="the model to use for generating proofs",
)
@click.option(
    "-x",
    "--max-nodes-to-expand",
    type=int,
    default=10,
    help="the maximum number of nodes to expand in the search tree",
)
@click.option(
    "-n",
    "--num-processes",
    type=int,
    default=1,
    help="the number of processes to use for running goal decomposition",
)
@click.option(
    "-u",
    "--uuid",
    type=str,
    required=False,
    help="the uuid of the run to resume. leave empty to start a new run",
)
@click.option(
    "--example-wall-timeout-sec",
    type=float,
    default=None,
    help="per-lemma cumulative wall-clock limit in seconds (overrides GOAL_DECOMPOSITION_EXAMPLE_WALL_TIMEOUT_SEC; <=0 disables)",
)
def run(
    dataset,
    lemma,
    try_hammer,
    context,
    max_depth,
    max_nodes_to_expand,
    num_processes,
    uuid,
    model,
    example_wall_timeout_sec,
):

    if uuid is None:
        uuid = uuid4().hex

    set_run_uuid(uuid)

    goal_decomposition = GoalDecompositionEval(
        uuid,
        dataset,
        context,
        try_hammer,
        max_depth,
        lemma,
        model
    )

    wall_timeout = example_wall_timeout_sec
    if wall_timeout is None:
        wall_timeout = CONFIG.GOAL_DECOMPOSITION_EXAMPLE_WALL_TIMEOUT_SEC

    goal_decomposition.run(
        num_processes,
        max_nodes_to_expand=max_nodes_to_expand,
        example_wall_timeout_sec=wall_timeout,
    )


@cli.command(help="log information about a run")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset to sample solutions for",
)
@click.option(
    "-c",
    "--context",
    type=click.Choice(LEMMA_CONTEXTS),
    default="preceding-lemmas-only",
    help="the context to use when sampling",
)
@click.option(
    "-m",
    "--max-depth",
    type=int,
    default=5,
    help="the maximum depth to search for a proof",
)
@click.option(
    "-t",
    "--try-hammer",
    is_flag=True,
    help="try to prove the lemma with hammer",
)
@click.option(
    "-u",
    "--uuid",
    type=str,
    required=False,
    help="the uuid of the run to resume. leave empty to start a new run",
)
@click.option(
    "-l",
    "--lemma",
    type=str,
    required=False,
    multiple=True,
    help="a specific lemma in the dataset. If specified, only run goal decomposition for this lemma",
)
@click.option(
    "-s",
    "--log-tree-states",
    is_flag=True,
    help="log the tree states",
)
def info(dataset, context, max_depth, try_hammer, uuid, lemma, log_tree_states):
    dataset_name = dataset
    if uuid is not None:
        set_run_uuid(uuid)
    runner = GoalDecompositionEval(
        uuid, dataset_name, context, try_hammer, max_depth, lemma
    )
    runner.log_info(log_tree_states)


if __name__ == "__main__":
    cli()
