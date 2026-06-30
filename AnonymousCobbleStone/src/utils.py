import sys
import logging
import logging.config
import logging.handlers
from uuid import uuid4
from pythonjsonlogger import jsonlogger
import os
from pathlib import Path
import re
from typing import Optional, Dict, Union
import typing as t
from word2number import w2n
import __main__
import tqdm

from src.config import CONFIG

JSON = t.Dict[str, "JSON"] | t.List["JSON"] | str | int | float | bool | None
ToplevelJSON = t.Union[t.Dict[str, JSON], t.List[JSON]]

Tqdm = tqdm.tqdm


Yielded = t.TypeVar("Yielded")
Returned = t.TypeVar("Returned")


def step_generator_and_save_yields(
    generator: t.Generator[Yielded, t.Any, Returned], max_steps: t.Optional[int] = None
) -> t.Generator[Yielded, t.Any, t.Tuple[t.List[Yielded], Returned]]:
    """
    transforms a generator into a generator that also returns the yielded values
    """
    yielded: t.List[Yielded] = []
    while True if max_steps is None else len(yielded) < max_steps:
        try:
            y = next(generator)
            yielded.append(y)
            yield y
        except StopIteration as e:
            return yielded, e.value

    raise ValueError("max_steps exceeded")


def run_generator_and_save_yields(
    generator: t.Generator[Yielded, t.Any, Returned], max_steps: t.Optional[int] = None
) -> t.Tuple[t.List[Yielded], Returned]:
    """
    runs a generator and returns the yielded values
    """
    g = step_generator_and_save_yields(generator)
    num_steps = 0
    while True if max_steps is None else num_steps < max_steps:
        try:
            next(g)
            num_steps += 1
        except StopIteration as e:
            return e.value

    raise ValueError("max_steps exceeded")


def remove_extra_curly_brace(text: str) -> str:
    """
    remove extra curly brace that sometimes gets added when repairing incorrect JSON from GPT
    """
    # if text ends with a curly brace, and curly braces are unbalanced, remove the last curly brace
    text = text.strip()
    if text.endswith("}") and text.count("{") > text.count("}"):
        text = text[:-1]
    return text


class TqdmFunc(t.Protocol):
    def __call__(self, total: int, desc: str, dynamic_ncols: bool) -> Tqdm:  # type: ignore
        pass


A = t.TypeVar("A")


def ensure_not_none(value: t.Optional[A]) -> A:
    if value is None:
        raise ValueError("value is None")
    return value


# based on
# https://github.com/cvlab-columbia/viper/blob/main/image_patch.py#L437
def coerce_to_numeric(string: str) -> Union[int, float]:
    """
    This function takes a string as input and returns a float after removing any non-numeric characters.
    If the input string contains a range (e.g. "10-15"), it returns the first value in the range.
    """
    try:
        # If it is a word number (e.g. 'zero')
        numeric: Union[int, float] = w2n.word_to_num(string)
        return numeric
    except ValueError:
        pass

    # Remove any non-numeric characters except the decimal point and the negative sign
    string_re = re.sub("[^0-9\\.\\-]", "", string)

    if string_re.startswith("-"):
        string_re = "&" + string_re[1:]

    # Check if the string includes a range
    if "-" in string_re:
        # Split the string into parts based on the dash character
        parts = string_re.split("-")
        return coerce_to_numeric(parts[0].replace("&", "-"))
    else:
        string_re = string_re.replace("&", "-")

    try:
        # Convert the string to a float or int depending on whether it has a decimal point
        if "." in string_re:
            numeric = float(string_re)
        else:
            numeric = int(string_re)
    except:
        raise ValueError
    return numeric


# region LOGGER


running_file = (
    os.path.basename(__main__.__file__)
    if "__file__" in dir(__main__)
    else "notebook.test.py"
)
test_file_regex = re.compile(r"\.test\.py")
in_test = test_file_regex.search(running_file)

format = "%(asctime)s %(levelname)s %(name)s: %(message)s"
datefmt = "%Y-%m-%d %H:%M:%S"


RUN_UUID = uuid4().hex


def configure_logger(filename: Optional[str] = None):
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    handlers = []

    if in_test:
        handlers.append(logging.StreamHandler(sys.stdout))
    handlers.append(
        logging.handlers.TimedRotatingFileHandler(CONFIG.LOG_FILE, when="D")
    )

    if filename is not None:
        handlers.append(logging.FileHandler(filename))

    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        "%Y-%m-%d %H:%M:%S",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
        },
    )

    for handler in handlers:
        handler.setFormatter(formatter)
        handler.setLevel(logging.DEBUG)
        logging.root.addHandler(handler)

    logging.root.setLevel(logging.DEBUG)

    logger = get_logger()
    logger.info(
        f"Starting a new session",
        extra={
            "log_filename": filename,
            "command": " ".join(sys.argv),
            "run_uuid": RUN_UUID,
        },
    )


def set_run_uuid(uuid: str):
    global RUN_UUID
    RUN_UUID = uuid
    return RUN_UUID


def set_log_file(path: Path):
    configure_logger(str(path.absolute()))


example_name: t.Optional[str] = None


def set_example_name(name: t.Optional[str]):
    global example_name
    example_name = name


class ExampleLogAdapter(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.get("extra", {})
        if example_name is not None:
            extra["example_name"] = example_name
        if "run_uuid" not in extra:
            extra["run_uuid"] = RUN_UUID
        kwargs["extra"] = extra
        return msg, kwargs


def get_logger(tag: Optional[str] = None):
    logger = logging.getLogger(
        "prompts-for-proofs" if tag is None else f"prompts-for-proofs.{tag}"
    )
    ans = ExampleLogAdapter(logger)
    return ans


configure_logger()


def my_except_hook(exctype, value, traceback):
    logger = get_logger()
    logger.error(
        "Uncaught exception",
        extra={
            "exception": {
                "type": exctype.__name__,
                "value": str(value),
                "traceback": traceback,
            }
        },
    )


sys.__excepthook__ = my_except_hook

# endregion LOGGER
