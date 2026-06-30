import typing as t
from uuid import uuid4
import click
from src.utils import set_run_uuid
from src.dataset import DATASET_NAMES

from .utils import LEMMA_CONTEXTS
from .next_tactic import NextTacticEval


@click.group()
def cli():
    pass


@cli.command(help="run TBT search on the datset")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset to run TBT search on",
)
@click.option(
    "-l",
    "--lemma",
    type=str,
    required=False,
    multiple=True,
    help="a specific lemma in the dataset. If specified, only run TBT search for this lemma",
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
    help="the number of processes to use for running TBT search",
)
@click.option(
    "-u",
    "--uuid",
    type=str,
    required=False,
    help="the uuid of the run to resume. leave empty to start a new run",
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
):

    if uuid is None:
        uuid = uuid4().hex

    set_run_uuid(uuid)

    eval = NextTacticEval(
        uuid,
        dataset,
        context,
        try_hammer,
        max_depth,
        lemma,
    )

    eval.run(num_processes, max_nodes_to_expand=max_nodes_to_expand)


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
    runner = NextTacticEval(uuid, dataset_name, context, try_hammer, max_depth, lemma)
    runner.log_info(log_tree_states)


if __name__ == "__main__":
    cli()
