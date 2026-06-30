import typing

OpenaiChatModelName = typing.Literal[
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    "meta-llama-3.1-405b-instruct",
    "claude-3-opus-20240229",
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v4-flash",
]
OPENAI_CHAT_MODEL_NAMES = [
    "gpt-3.5-turbo",
    "gpt-4",
    "gpt-3.5-turbo-1106",
    "gpt-3.5-turbo-0125",
    "meta-llama-3.1-405b-instruct",
    "claude-3-opus-20240229",
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v4-flash",
]


def is_anthropic_model(model_name: str) -> bool:
    return model_name == "claude-3-opus-20240229"


def is_deepseek_model(model_name: str) -> bool:
    return model_name.startswith("deepseek-")

OpenaiPromptModelName = typing.Literal["ada", "babbage", "curie", "davinci"]
OPENAI_COMPLETION_MODEL_NAMES = ["ada", "babbage", "curie", "davinci"]

OpenaiModelName = typing.Union[OpenaiChatModelName, OpenaiPromptModelName]
