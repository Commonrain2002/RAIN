from uuid import uuid4
import click
from src.utils import set_run_uuid

from .regenerate_from_failure_point import RegenerateFromFailurePointEval
from .utils import DATASET_NAMES

@click.group()
def cli():
    pass


@cli.command(help="run regenerate from failure point evaluation on the dataset")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset to run regenerate from failure point evaluation on",
)
@click.option(
    "-l",
    "--lemma",
    type=str,
    required=False,
    multiple=True,
    help="a specific lemma in the dataset. If specified, only run evaluation for this lemma",
)
@click.option(
    "-t",
    "--try-hammer",
    is_flag=True,
    help="try to prove the lemma with hammer",
)
@click.option(
    "-a",
    "--max-num-attempts",
    type=int,
    default=5,
    help="the maximum number of attempts to regenerate from failure point",
)
@click.option(
    "-n",
    "--num-processes",
    type=int,
    default=1,
    help="the number of processes to use for running regenerate from failure point evaluation",
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
    max_num_attempts,
    num_processes,
    uuid,
):

    if uuid is None:
        uuid = uuid4().hex

    set_run_uuid(uuid)

    eval = RegenerateFromFailurePointEval(
        uuid,
        dataset,
        try_hammer,
        max_num_attempts,
        lemma,
    )

    eval.run(num_processes)


@cli.command(help="log information about a run")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset to get information for",
)
@click.option(
    "-t",
    "--try-hammer",
    is_flag=True,
    help="try to prove the lemma with hammer",
)
@click.option(
    "-a",
    "--max-num-attempts",
    type=int,
    default=5,
    help="the maximum number of attempts to regenerate from failure point",
)
@click.option(
    "-u",
    "--uuid",
    type=str,
    required=False,
    help="the uuid of the run to get information for",
)
@click.option(
    "-l",
    "--lemma",
    type=str,
    required=False,
    multiple=True,
    help="a specific lemma in the dataset. If specified, only get information for this lemma",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="log verbose information",
)
def info(dataset, try_hammer, max_num_attempts, uuid, lemma, verbose):
    dataset_name = dataset
    if uuid is not None:
        set_run_uuid(uuid)
    runner = RegenerateFromFailurePointEval(
        uuid, dataset_name, try_hammer, max_num_attempts, lemma
    )
    runner.log_info(verbose=verbose)


if __name__ == "__main__":
    cli()
