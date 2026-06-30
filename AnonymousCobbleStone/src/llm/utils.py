import tiktoken
import typing as t
import json
import os
from functools import lru_cache
from pathlib import Path
from pprint import pprint
from json_repair import repair_json

from src.llm.types import ChatMessage, OpenaiModelName, AssistantMessage


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DEEPSEEK_TOKENIZER_DIR = REPO_ROOT / "deepseek_v3_tokenizer"


def fix_llm_json_errors(json_str: str) -> str:
    """
    GPT often returns invalid JSON, but in a predictable way. this function
    fixes those errors.
    """
    ans = replace_weird_control_characters(json_str)
    # ans = escape_newlines_in_quotes(json_str)
    ans = t.cast(str, repair_json(ans))
    return ans


def replace_weird_control_characters(json_str: str) -> str:
    """
    replaces weird control characters that are sometimes returned by GPT
    """
    return json_str.replace("\r\\n", "\n")


def get_parse_error(json_str: str) -> t.Optional[str]:
    try:
        json.loads(json_str)
        return None
    except json.JSONDecodeError as e:
        return str(e)


def escape_newlines_in_quotes(json_str: str) -> str:
    """
    escapes newlines in quotes. this is a common error in GPT's JSON output
    """
    original_str = json_str
    inside_quotes = False
    fixed_string = ""

    while len(json_str) > 0:
        char = json_str[0]
        to_add = char
        prefix = char

        # print("inside_quotes", inside_quotes)
        # pprint(json_str[:20])

        if char == '"':
            inside_quotes = not inside_quotes
        elif inside_quotes and json_str.startswith("\r\\n"):
            prefix = "\r\\n"
            to_add = "\\r\\n"
        elif inside_quotes and json_str.startswith("\r\n"):
            prefix = "\r\n"
            to_add = "\\r\\n"
        elif inside_quotes and json_str.startswith("\r"):
            prefix = "\r"
            to_add = "\\r"
        elif inside_quotes and json_str.startswith("\n"):
            prefix = "\n"
            to_add = "\\n"
        elif inside_quotes and json_str.startswith("\\"):
            prefix = "\\"
            to_add = "\\\\"

        # pprint(to_add)
        # print()
        fixed_string += to_add
        json_str = json_str[len(prefix) :]

    return fixed_string


# TODO: delete this
# based on https://github.com/openai/openai-cookbook/blob/main/examples/How_to_count_tokens_with_tiktoken.ipynb
def estimate_num_tokens(
    messages: t.List[ChatMessage],
    model: t.Union[OpenaiModelName, t.Literal["gpt-3.5-turbo-0613", "gpt-4-0613"]],
) -> int:
    """Return the number of tokens used by a list of messages."""
    if "deepseek" in model:
        return _estimate_deepseek_num_tokens(messages)

    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        encoding = tiktoken.get_encoding("cl100k_base")
    if model in {
        "gpt-3.5-turbo-0613",
        "gpt-3.5-turbo-16k-0613",
        "gpt-4-0314",
        "gpt-4-32k-0314",
        "gpt-4-0613",
        "gpt-4-32k-0613",
    }:
        tokens_per_message = 3
        tokens_per_name = 1
    elif model == "gpt-3.5-turbo-0301":
        tokens_per_message = (
            4  # every message follows <|start|>{role/name}\n{content}<|end|>\n
        )
        tokens_per_name = -1  # if there's a name, the role is omitted
    elif "gpt-3.5-turbo" in model:
        # print(
        #     "Warning: gpt-3.5-turbo may update over time. Returning num tokens assuming gpt-3.5-turbo-0613."
        # )
        return estimate_num_tokens(messages, model="gpt-3.5-turbo-0613")
    elif "gpt-4" in model:
        # print(
        #     "Warning: gpt-4 may update over time. Returning num tokens assuming gpt-4-0613."
        # )
        return estimate_num_tokens(messages, model="gpt-4-0613")
    else:
        return estimate_num_tokens(messages, model="gpt-4")
    num_tokens = 0
    for message in messages:
        num_tokens += tokens_per_message
        num_tokens += len(encoding.encode(message.content))
        if (
            isinstance(message, AssistantMessage)
            and message.reasoning_content
            and message.reasoning_content != message.content
        ):
            num_tokens += len(encoding.encode(message.reasoning_content))
    num_tokens += 3  # every reply is primed with <|start|>assistant<|message|>
    return num_tokens


@lru_cache(maxsize=1)
def _load_deepseek_tokenizer() -> t.Any:
    tokenizer_dir = Path(
        os.getenv("DEEPSEEK_TOKENIZER_DIR", str(DEFAULT_DEEPSEEK_TOKENIZER_DIR))
    ).expanduser()
    if not tokenizer_dir.exists():
        return None

    try:
        from transformers import AutoTokenizer
        from transformers import logging as transformers_logging

        transformers_logging.set_verbosity_error()

        return AutoTokenizer.from_pretrained(
            str(tokenizer_dir),
            local_files_only=True,
            trust_remote_code=True,
        )
    except Exception:
        pass

    tokenizer_json = tokenizer_dir / "tokenizer.json"
    if not tokenizer_json.exists():
        return None

    try:
        from tokenizers import Tokenizer

        return Tokenizer.from_file(str(tokenizer_json))
    except Exception:
        return None


def _message_content_for_tokenizer(message: ChatMessage) -> str:
    content = message.content or ""
    if (
        isinstance(message, AssistantMessage)
        and message.reasoning_content
        and message.reasoning_content != content
    ):
        return f"{message.reasoning_content}\n{content}"
    return content


def _estimate_deepseek_num_tokens(messages: t.List[ChatMessage]) -> int:
    tokenizer = _load_deepseek_tokenizer()
    if tokenizer is None:
        return estimate_num_tokens(messages, model="gpt-4-0613")

    tokenizer_messages = [
        {
            "role": message.role,
            "content": _message_content_for_tokenizer(message),
        }
        for message in messages
    ]

    if hasattr(tokenizer, "apply_chat_template"):
        try:
            tokens = tokenizer.apply_chat_template(
                tokenizer_messages,
                tokenize=True,
                add_generation_prompt=True,
            )
            return len(tokens)
        except Exception:
            pass

    rendered = "\n".join(
        f"{message['role']}: {message['content']}" for message in tokenizer_messages
    )
    encoded = tokenizer.encode(rendered)
    if hasattr(encoded, "ids"):
        return len(encoded.ids)
    return len(encoded)
