import json
import math
import datetime
import typing as t
import openai
import time
import openai.error
from datetime import datetime
import anthropic
import traceback

from src.llm.model_names import is_anthropic_model, is_deepseek_model
from src.config import CONFIG
from src.utils import get_logger
from src.llm.openai_compat import (
    assistant_message_from_openai,
    deepseek_thinking_mode_request_kwargs,
)
from src.llm.types import (
    ChatMessage,
    AssistantMessage,
    OPENAI_MAX_TOKENS,
    OpenaiChatPromptConfig,
    OpenaiToolConfig,
    OpenaiToolCall,
)
from src.llm.utils import fix_llm_json_errors, estimate_num_tokens
from src.llm.usage import Usage

LOGGER = get_logger("llm.gpt")
TIMEOUT_SEC = CONFIG.LLM_REQUEST_TIMEOUT_SEC


def _anthropic_client() -> anthropic.Anthropic:
    if not CONFIG.CLAUDE_API_KEY:
        raise RuntimeError("CLAUDE_API_KEY is required for Claude models")
    return anthropic.Anthropic(api_key=CONFIG.CLAUDE_API_KEY)


def _openai_chat_create_kwargs(
    config: OpenaiChatPromptConfig,
    **additional: t.Any,
) -> t.Dict[str, t.Any]:
    kwargs: t.Dict[str, t.Any] = {**config.__dict__, **additional}
    kwargs.update(deepseek_thinking_mode_request_kwargs(config.model))
    return kwargs


def setup_endpoints(config: OpenaiChatPromptConfig):
    if config.model == "meta-llama-3.1-405b-instruct":
        openai.api_base = "https://text.octoai.run/v1"
        openai.organization = ""
        openai.api_key = CONFIG.OCTO_API_KEY or ""
    elif is_deepseek_model(config.model) or CONFIG.DEEPSEEK_API_KEY:
        openai.api_base = CONFIG.DEEPSEEK_API_BASE
        openai.organization = ""
        openai.api_key = CONFIG.DEEPSEEK_API_KEY or CONFIG.OPENAI_SECRET or ""
    else:
        openai.api_base = "https://api.openai.com/v1"
        openai.organization = CONFIG.OPENAI_ORG or ""
        openai.api_key = CONFIG.OPENAI_SECRET or ""


def chat(
    messages: t.List[ChatMessage],
    config: OpenaiChatPromptConfig,
) -> t.Tuple[t.List[AssistantMessage], Usage]:
    """
    prompts the openai chat api

    messages: list of previous messages in the chat transcript
    config: OpenaiChatPromptConfig. the parameters with which to call the model
    return: a list of messages from the model, with len(return) = config.n
    """
    setup_endpoints(config)
    num_tokens = estimate_num_tokens(messages, config.model)
    LOGGER.debug(
        f"making chat request for num_tokens: {num_tokens}",
        extra={"num_tokens": num_tokens},
    )
    max_tokens = OPENAI_MAX_TOKENS[config.model]
    if num_tokens > max_tokens:
        LOGGER.warn(
            f"Warning: num tokens {num_tokens} exceeds "
            + f"max tokens {max_tokens} for model {config.model}.",
            extra={
                "num_tokens": num_tokens,
                "max_tokens": max_tokens,
                "model": config.model,
            },
        )

    if is_anthropic_model(config.model):
        system_message = next((message for message in messages if message.role == "system"), None)
        messages = [message for message in messages if message.role != "system"]
        
        assistant_messages: t.List[AssistantMessage] = []
        usage = Usage(name="chat", model=config.model)

        for i in range(config.n):
            start_time = datetime.now()
            if system_message:
                response = _anthropic_client().messages.create(
                    model=config.model,
                    messages=[message.anthropic_dict() for message in messages],
                    max_tokens=max_tokens,
                    system=system_message.content,
                    temperature=config.temperature,
                    top_p=config.top_p,
                )
            else:
                response = _anthropic_client().messages.create(
                    model=config.model,
                    messages=[message.anthropic_dict() for message in messages],
                    max_tokens=max_tokens,
                    temperature=config.temperature,
                    top_p=config.top_p,
                )
            end_time = datetime.now()
            assistant_messages.append(AssistantMessage(content=response.content))
            usage.add_child(Usage.from_anthropic_response(
                name="chat",
                config=config,
                response=response,
                start_time=start_time,
                end_time=end_time,
            ))

        return assistant_messages, usage
    else:
        start_time = datetime.now()
        response: t.Any = openai.ChatCompletion.create(
            messages=[message.openai_dict() for message in messages],
            timeout=TIMEOUT_SEC,
            **_openai_chat_create_kwargs(config),
        )
        end_time = datetime.now()

        assistant_messages = [
            assistant_message_from_openai(choice.message)
            for choice in response.choices
        ]

        usage = Usage.from_openai_response(
            name="chat",
            config=config,
            response=response,
            start_time=start_time,
            end_time=end_time,
        )

        LOGGER.debug(
            "chat() usage",
            extra={
                "usage": usage,
            },
        )

        return assistant_messages, usage


def chat_with_tools(
    messages: list[ChatMessage],
    config: OpenaiChatPromptConfig,
    tool_config: t.Optional[OpenaiToolConfig] = None,
    num_retries = 0
) -> t.Tuple[t.List[t.Union[AssistantMessage, t.List[OpenaiToolCall]]], Usage]:
    """
    prompts the openai chat api

    messages: list of previous messages in the chat transcript
    config: OpenaiChatPromptConfig. the parameters with which to call the model
    return: a list of messages from the model, with len(return) = config.n
    """
    setup_endpoints(config)
    if num_retries > MAX_RETRIES:
        raise Exception(f"retried {num_retries} times. giving up.")
    
    tool_config = tool_config or OpenaiToolConfig()

    num_tokens = estimate_num_tokens(messages, config.model)
    LOGGER.info(
        f"making chat request with tools for num_tokens: {num_tokens}",
        extra={"num_tokens": num_tokens},
    )
    max_tokens = OPENAI_MAX_TOKENS[config.model]
    if num_tokens > max_tokens:
        LOGGER.warn(
            f"num tokens {num_tokens} exceeds "
            + f"max tokens {max_tokens} for model {config.model}.",
            extra={
                "num_tokens": num_tokens,
                "max_tokens": max_tokens,
                "model": config.model,
            },
        )

    try:
        if is_anthropic_model(config.model):
            system_message = next((message for message in messages if message.role == "system"), None)
            messages = [message for message in messages if message.role != "system"]

            ans: t.List[t.Union[AssistantMessage, t.List[OpenaiToolCall]]] = []
            usage = Usage(name="chat_with_tools", model=config.model)

            for i in range(config.n):
                start_time = datetime.now()
                # todo: tool use
                if system_message:
                    response = _anthropic_client().messages.create(
                        model=config.model,
                        messages=[message.anthropic_dict() for message in messages],
                        max_tokens=config.max_tokens,
                        system=system_message.content,
                        temperature=config.temperature,
                        top_p=config.top_p,
                        **tool_config.as_anthropic_dict(),
                    )
                else:
                    response = _anthropic_client().messages.create(
                        model=config.model,
                        messages=[message.anthropic_dict() for message in messages],
                        max_tokens=config.max_tokens,
                        temperature=config.temperature,
                        top_p=config.top_p,
                        **tool_config.as_anthropic_dict(),
                    )
                end_time = datetime.now()

                if any(item.type == "tool_use" for item in response.content):
                    ans.append([
                        OpenaiToolCall(
                            name=item.name,
                            arguments=item.input,
                            id=item.id,
                        )
                        for item in response.content
                        if item.type == "tool_use"
                    ])
                else:
                    ans.append(AssistantMessage(content=response.content[0].text))

                usage.add_child(Usage.from_anthropic_response(
                    name="chat_with_tools",
                    config=config,
                    response=response,
                    start_time=start_time,
                    end_time=end_time,
                ))

            return ans, usage
        else:
            start_time = datetime.now()
            response= openai.ChatCompletion.create(
                messages=[message.openai_dict() for message in messages],
                timeout=TIMEOUT_SEC,
                **_openai_chat_create_kwargs(
                    config, **tool_config.as_dict(model=config.model)
                ),
            )
            end_time = datetime.now()

            ans: t.List[t.Union[AssistantMessage, t.List[OpenaiToolCall]]] = []
            for choice in response.choices:
                if "tool_calls" in choice.message and choice.message.tool_calls is not None:
                    try:
                        ans.append(
                            [
                                OpenaiToolCall(
                                    name=tool_call.function.name,
                                    arguments=json.loads(
                                        fix_llm_json_errors(tool_call.function.arguments)
                                    ),
                                    id=tool_call.id,
                                )
                                for tool_call in choice.message.tool_calls
                            ]
                        )
                    except Exception as e:
                        LOGGER.error(
                            "Error while parsing tool calls",
                            extra={
                                "arguments": [
                                    tool_call.function.arguments
                                    for tool_call in choice.message.tool_calls
                                ],
                            },
                        )
                        raise e
                else:
                    ans.append(assistant_message_from_openai(choice.message))

            usage = Usage.from_openai_response(
                name="chat_with_tools",
                config=config,
                response=response,
                start_time=start_time,
                end_time=end_time,
            )

            LOGGER.debug(
                "chat_with_tools() usage",
                extra={
                    "usage": usage,
                },
            )

            return ans, usage
    except (openai.error.RateLimitError, openai.error.Timeout) as e:
            sleep_duration_ms = 60_000
            sleep_duration = math.ceil(sleep_duration_ms / 1000.0)

            LOGGER.warning(
                f"Rate limit reached for model {config.model}."
                + f" Sleeping for {sleep_duration} seconds...",
                extra={
                    "model": config.model,
                    "sleep_duration": sleep_duration,
                    "error_type": type(e),
                },
            )
            time.sleep(sleep_duration)
            return chat_with_tools(messages, config, tool_config, num_retries + 1)
    except Exception as e:
        sleep_duration_ms = 60_000
        sleep_duration = math.ceil(sleep_duration_ms / 1000.0)
        LOGGER.error(
            f"Error while calling chat_with_tools() for model {config.model}."
            + f" Sleeping for {sleep_duration} seconds...",
            extra={
                "model": config.model,
                "sleep_duration": sleep_duration,
                # "error": e,
                "stacktrace": traceback.format_exc(),
            },
        )
        time.sleep(60)
        return chat_with_tools(messages, config, tool_config, num_retries + 1)
    


MAX_RETRIES = CONFIG.LLM_MAX_RETRIES


def rate_limited_chat(
    messages: t.List[ChatMessage], config: OpenaiChatPromptConfig, num_retries=0
) -> t.Tuple[t.List[AssistantMessage], Usage]:
    """
    same as chat, but handles rate limiting from openai's API
    """
    setup_endpoints(config)
    if num_retries > MAX_RETRIES:
        raise Exception(f"retried {num_retries} times. giving up.")

    LOGGER.debug(
        f"requesting chat for model {config.model}",
        extra={
            "model": config.model,
        },
    )
    try:
        if is_anthropic_model(config.model):
            system_message = next((message for message in messages if message.role == "system"), None)
            messages = [message for message in messages if message.role != "system"]
            
            assistant_messages: t.List[AssistantMessage] = []
            usage = Usage(name="chat", model=config.model)

            for i in range(config.n):
                start_time = datetime.now()
                if system_message:
                    response = _anthropic_client().messages.create(
                        model=config.model,
                        messages=[message.anthropic_dict() for message in messages],
                        max_tokens=config.max_tokens,
                        system=system_message.content,
                        temperature=config.temperature,
                        top_p=config.top_p,
                    )
                else:
                    response = _anthropic_client().messages.create(
                        model=config.model,
                        messages=[message.anthropic_dict() for message in messages],
                        max_tokens=config.max_tokens,
                        temperature=config.temperature,
                        top_p=config.top_p,
                    )
                end_time = datetime.now()
                assistant_messages.append(AssistantMessage(content=response.content))
                usage.add_child(Usage.from_anthropic_response(
                    name="chat",
                    config=config,
                    response=response,
                    start_time=start_time,
                    end_time=end_time,
                ))

            return assistant_messages, usage
        else:
            start_time = datetime.now()
            response: t.Any = openai.ChatCompletion.create(
                messages=[message.openai_dict() for message in messages],
                timeout=TIMEOUT_SEC,
                **_openai_chat_create_kwargs(config),
            )
            end_time = datetime.now()

            assistant_messages = [
                assistant_message_from_openai(choice.message)
                for choice in response.choices
            ]

            usage = Usage.from_openai_response(
                name="chat",
                config=config,
                response=response,
                start_time=start_time,
                end_time=end_time,
            )

            LOGGER.debug(
                "chat() usage",
                extra={
                    "usage": usage,
                },
            )

            return assistant_messages, usage
    except (openai.error.RateLimitError, openai.error.Timeout) as e:
        sleep_duration_ms = 60_000
        sleep_duration = math.ceil(sleep_duration_ms / 1000.0)

        LOGGER.warning(
            f"Rate limit reached for model {config.model}."
            + f" Sleeping for {sleep_duration} seconds...",
            extra={
                "model": config.model,
                "sleep_duration": sleep_duration,
                "error_type": type(e),
            },
        )
        time.sleep(sleep_duration)
        return rate_limited_chat(messages, config, num_retries + 1)
    except Exception as e:
        sleep_duration_ms = 60_000
        sleep_duration = math.ceil(sleep_duration_ms / 1000.0)
        LOGGER.error(
            f"Error while calling rate_limited_chat() for model {config.model}."
            + f" Sleeping for {sleep_duration} seconds...",
            extra={
                "model": config.model,
                "sleep_duration": sleep_duration,
                "stacktrace": traceback.format_exc(),
            },
        )
        time.sleep(60)
        return rate_limited_chat(messages, config, num_retries + 1)
