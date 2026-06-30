from pathlib import Path
import sys
import typing as t

from datetime import datetime
import sys
from tqdm import tqdm
import traceback

from src.environment import (
    Environment,
    MakeAgentAndEnvironment,
    Strategy,
    EnvironmentConfig,
)

from src.dataset import Result, Dataset
from src.config import CONFIG
from src.utils import get_logger, set_log_file


LOGGER = get_logger("evaluation")


def evaluate(
    strategy: Strategy,
    dataset: Dataset,
    make_agent_and_environment: MakeAgentAndEnvironment,
    name: str,
) -> t.Generator[t.Optional[Environment], t.Any, Result]:
    """
    evaluate the model on the given dataset
    """
    result = Result(name)
    set_log_file(result.log_file_path)
    LOGGER.info(
        f"evaluating strategy {strategy.__name__} using agent {make_agent_and_environment.__name__} on dataset with {len(dataset)} proofs."
        + f"Evaluation uuid {result.uuid}",
        extra={
            "strategy": strategy.__name__,
            "agent": make_agent_and_environment.__name__,
            "eval-name": name,
            "num_examples": len(dataset),
            "uuid": result.uuid,
            "examples": "\n".join([str(example) for example in dataset]),
        },
    )

    print(
        f"running evaluation. check {str(result.log_file_path)} for details on the runs",
        file=sys.stderr,
    )
    for example in tqdm(dataset):
        try:
            env = strategy(example, make_agent_and_environment, None)
            yield env
            if env is not None and env.done:
                LOGGER.info(
                    "successfully proved example",
                    extra={
                        "example": example.proposition_command,
                        "uuid": result.uuid,
                        "proof": env.observation_code,
                    },
                )
                result.successful_examples.append(example)
            else:
                LOGGER.info(
                    "failed to prove example",
                    extra={
                        "example": example.proposition_command,
                        "uuid": result.uuid,
                    },
                )
                result.failed_examples.append(example)
        except Exception as e:
            LOGGER.error(
                f"EVALUATION EXAMPLE FAILED WITH ERROR: {e}",
                extra={"error": e, "stacktrace": traceback.format_exc()},
            )
            result.errored_examples.append((example, str(e)))
        finally:
            result.write_csv_examples()
    result.write_csv_examples()
    return result
