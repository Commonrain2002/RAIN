import typing as t
from pathlib import Path
import click

from .utils import DATASET_NAMES
from .zero_shot_pass_at_k import ZeroShotPassAtK
from src.utils import RUN_UUID, set_run_uuid
from src.llm.model_names import OpenaiChatModelName, OPENAI_CHAT_MODEL_NAMES



@click.group()
def cli():
    pass


@cli.command(help="collect and save samples")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset to sample solutions for",
)
@click.option(
    "-l",
    "--lemma",
    type=str,
    required=False,
    multiple=True,
    help="a specific lemma in the dataset. If specified, only solutions for this lemma will be sampled",
)
@click.option(
    "-m",
    "--model",
    type=click.Choice(OPENAI_CHAT_MODEL_NAMES),
    default="gpt-4",
    help="the model to use when sampling",
)
@click.option(
    "-k",
    type=int,
    required=True,
    help="the number of samples to collect for each lemma",
)
@click.option(
    "-n",
    "--num-processes",
    type=int,
    default=1,
    help="the number of processes to use for sampling",
)
@click.option(
    "-c",
    "--context",
    type=click.Choice(
        [
            "preceding-lines",
            "preceding-lemmas-only",
            "preceding-lemmas-and-selected-premises",
            "perfect-premises",
        ]
    ),
    default="preceding-lemmas-only",
    help="the context to use when sampling",
)
@click.option(
    "-t",
    "--temperature",
    type=click.FloatRange(0, 2),
    default=1.0,
    help="the temperature to use when sampling",
)
@click.option(
    "-u",
    "--uuid",
    type=str,
    required=False,
    help="the uuid of the run to resume. leave empty to start a new run",
)
def sample(dataset, lemma, k, num_processes, context, temperature, uuid, model):
    dataset_name = dataset

    if uuid is not None:
        uuid = set_run_uuid(uuid)

    runner = ZeroShotPassAtK(uuid, dataset_name, context, temperature, lemma, model)
    runner.collect_samples(k, num_processes)


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
    type=click.Choice(
        [
            "preceding-lines",
            "preceding-lemmas-only",
            "preceding-lemmas-and-selected-premises",
            "perfect-premises",
        ]
    ),
    default="preceding-lemmas-only",
    help="the context to use when sampling",
)
@click.option(
    "-t",
    "--temperature",
    type=click.FloatRange(0, 2),
    default=1.0,
    help="the temperature to use when sampling",
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
    help="a specific lemma in the dataset. If specified, only solutions for this lemma will be sampled",
)
def info(dataset, context, uuid, lemma, temperature):
    dataset_name = dataset
    if uuid is not None:
        set_run_uuid(uuid)
    runner = ZeroShotPassAtK(uuid, dataset_name, context, temperature, lemma)
    runner.log_info()


@cli.command(help="evaluate samples using the pass@k metric")
@click.option(
    "-d",
    "--dataset",
    type=click.Choice(DATASET_NAMES),
    required=True,
    help="the dataset solutions were sampled for",
)
@click.option(
    "-c",
    "--context",
    type=click.Choice(
        [
            "preceding-lines",
            "preceding-lemmas-only",
            "preceding-lemmas-and-selected-premises",
            "perfect-premises",
        ]
    ),
    help="the context of the samples",
)
@click.option(
    "-t",
    "--temperature",
    type=click.FloatRange(0, 2),
    default=1.0,
    help="the temperature to use when sampling",
)
@click.option(
    "-u",
    "--uuid",
    type=str,
    help="the uuid of the run",
)
def evaluate(dataset, context, temperature, uuid):
    dataset_name = dataset
    if uuid is not None:
        set_run_uuid(uuid)
    runner = ZeroShotPassAtK(uuid, dataset_name, context, temperature)
    runner.output_evaluation()


if __name__ == "__main__":
    cli()
