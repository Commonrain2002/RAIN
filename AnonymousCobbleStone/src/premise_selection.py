import typing as t

from src.llm import (
    rate_limited_chat,
    chat_with_tools,
    OpenaiToolConfig,
    OpenaiTool,
    OpenaiChatPromptConfig,
    Usage,
)
from src.llm import SystemMessage, UserMessage, AssistantMessage
from src.coq_serapy_util import Coq
from src.utils import get_logger

LOGGER = get_logger("premise_selection")


def system_prompt(n_identifiers=5):
    return f"""You are an expert at proving theorems using the Coq theorem prover.
You are helping a colleague who is searching for lemmas that will help them proof a theorem.
Suggest {n_identifiers} identifiers from the following observation for your colleague to search about.
These identifiers should be ranked in order of importance for the proof.
Your colleague will use these identifiers to search for lemmas that will help them prove the theorem.

Always reason before acting.
Be terse."""


TOOL = OpenaiTool(
    "Search for lemmas that will help prove the theorem",
    "search_for_lemmas",
    {
        "type": "object",
        "properties": {
            "identifiers": {
                "type": "array",
                "items": {
                    "type": "string",
                    "description": "a list of identifiers to search for. These should be ranked in order of importance for the proof. Each identifier should be a valid coq identifier without spaces",
                },
            }
        },
    },
)


def select_premises(
    observation: str, coq: Coq, include_reasoning=False, n_identifiers=5
) -> t.Tuple[t.List[str], Usage]:
    reasoning: t.Optional[str] = None

    LOGGER.debug("selecting premises", extra={"observation": observation})

    if include_reasoning:
        reasoning, r_usage = get_reasoning(observation, n_identifiers)

    identifiers, i_usage = get_identifiers(observation, reasoning, n_identifiers)

    ans = [lemma for identifier in identifiers for lemma in coq.search(identifier)]

    LOGGER.debug(f"got {len(ans)} premises", extra={"premises": ans[0:10]})

    usage = Usage(name="select_premises")
    if r_usage is not None:
        usage.add_child(r_usage)
    usage.add_child(i_usage)

    return ans, usage


def get_reasoning(observation: str, n_identifiers: int) -> t.Tuple[str, Usage]:
    messages = [
        SystemMessage(content=system_prompt(n_identifiers)),
        UserMessage(
            content=f"""{observation}

[REASONING]"""
        ),
    ]

    response, usage = rate_limited_chat(
        messages, OpenaiChatPromptConfig(max_tokens=1000)
    )
    message = response[0]

    LOGGER.debug(
        "got reasoning",
        extra={
            "reasoning": message.content,
            "observation": observation,
            "n_identifiers": n_identifiers,
        },
    )

    return message.content, usage


def get_identifiers(
    observation: str, reasoning: t.Optional[str], n_identifiers: int
) -> t.Tuple[t.List[str], Usage]:
    messages = [
        SystemMessage(content=system_prompt(n_identifiers)),
        UserMessage(content=observation),
    ]

    if reasoning:
        messages.append(
            AssistantMessage(
                content=f"""[REASONING]
{reasoning}"""
            )
        )

    response, usage = chat_with_tools(
        messages,
        OpenaiChatPromptConfig(),
        OpenaiToolConfig(tools=[TOOL], tool_choice=TOOL),
    )
    tool_call = response[0]

    if isinstance(tool_call, AssistantMessage):
        raise ValueError("Tool call resulted in assistant message")

    LOGGER.debug(
        "got identifiers",
        extra={
            "identifiers": tool_call[0].arguments["identifiers"],
            "observation": observation,
            "reasoning": reasoning,
            "n_identifiers": n_identifiers,
        },
    )

    return t.cast(t.List[str], tool_call[0].arguments["identifiers"]), usage
