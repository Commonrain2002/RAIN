import typing as t
from dataclasses import dataclass

from src.llm.types import AssistantMessage, ChatMessage, SystemMessage, UserMessage
from src.agent.agent import Agent
from src.utils import get_logger
from src.llm import (
    OpenaiToolCall,
    chat_with_tools,
    OpenaiChatPromptConfig,
    OpenaiTool,
    OpenaiToolConfig,
    Usage,
)
from src.environment import (
    Action,
    DefinitionsAction,
    EditAction,
    Observation,
    SearchAction,
)

LOGGER = get_logger("agent.single_message_tool")


PREAMBLE_WITHOUT_REASONING = """You are an expert at writing code for the Coq theorem prover.
You will be given a theorem, definitions, and useful lemmas in a user message.
Using this information, choose one of the following actions to make progress on the proof.
Be terse."""

PREAMBLE = """You are an expert at writing code for the Coq theorem prover.
You will be given a theorem, definitions, and useful lemmas in a user message.
Using this information, choose one of the following actions to make progress on the proof.
Always reason before acting. Be terse."""

REASONING_PROMPT = """Express your reasoning for what the best action is to take next. Be terse.

[REASONING]"""

TOOLS: t.List[OpenaiTool] = [
    OpenaiTool(
        name="edit",
        description="Edit the code in the 'CURRENT CODE' section",
        parameters={
            "type": "object",
            "properties": {
                "new_code": {
                    "type": "string",
                    "description": "a new version of the current code section, which incorporates the changes you made. This code describes a proof script and should only use tactics from the Coq tactic language. This code should only mention identifiers from the user message. ",
                }
            },
        },
    ),
    OpenaiTool(
        name="define",
        description="Get definitions of identifiers",
        parameters={
            "type": "object",
            "properties": {
                "identifiers": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "a list of identifiers to define. These identifiers should be mentioned in the user message, and not already defined.",
                    },
                }
            },
        },
    ),
    OpenaiTool(
        name="search",
        description="Search for proven theorems and lemmas",
        parameters={
            "type": "object",
            "properties": {
                "identifiers": {
                    "type": "array",
                    "items": {
                        "type": "string",
                        "description": "a list of identifiers to search for. These identifiers should be mentioned in the user message.",
                    },
                }
            },
        },
    ),
]


@dataclass
class SingleMessageToolAgentConfig:
    include_reasoning: bool = False
    edit_only: bool = False
    openai_config: OpenaiChatPromptConfig = OpenaiChatPromptConfig()


MAX_REASONING_TOKENS = 200


class SingleMessageToolAgent(Agent[Action, Observation]):
    """
    Similar functionality to SingleMessageAgent, but zero shot, with tool use
    """

    messages: t.List[ChatMessage]
    config: SingleMessageToolAgentConfig
    system_prompt: str
    lemma: str
    tools: t.List[OpenaiTool]

    def __init__(
        self,
        lemma: str,
        config: SingleMessageToolAgentConfig = SingleMessageToolAgentConfig(),
    ):
        super().__init__()
        self.lemma = lemma
        self.config = config
        self.system_prompt = (
            PREAMBLE_WITHOUT_REASONING if not config.include_reasoning else PREAMBLE
        )
        self.messages = [SystemMessage(content=self.system_prompt)]
        self.tools = [TOOLS[0]] if config.edit_only else TOOLS

    def act(self, observation: Observation) -> t.Tuple[t.List[Action], Usage]:
        messages = [
            SystemMessage(content=self.system_prompt),
            UserMessage(content=observation),
        ]

        if self.config.include_reasoning:
            reasoning, r_usage = self.__prompt_for_reasoning(observation)
            LOGGER.debug(
                "got reasoning",
                extra={
                    "reasoning": reasoning,
                },
            )
        else:
            reasoning = None
            r_usage = None

        if reasoning:
            messages.append(AssistantMessage(content=reasoning))

        response, a_usage = chat_with_tools(
            messages,
            self.config.openai_config,
            OpenaiToolConfig(TOOLS[0] if self.config.edit_only else "auto", TOOLS),
        )

        result = response[0]

        if isinstance(result, AssistantMessage):
            LOGGER.error(
                "expected GPT to use tools, not to respond with a message",
                extra={
                    "content": result.content,
                },
            )
            raise Exception("expected GPT to use tools, not to respond with a message")

        action = self.__parse_action(result)
        usage = a_usage + r_usage if r_usage else a_usage

        self.usage.add_child(a_usage)
        if r_usage:
            self.usage.add_child(r_usage)

        LOGGER.debug(
            "usage",
            extra={
                "usage": usage,
            },
        )

        return [action], usage

    def __prompt_for_reasoning(self, observation: Observation) -> t.Tuple[str, Usage]:
        reasoning_config = OpenaiChatPromptConfig(
            model=self.config.openai_config.model,
            max_tokens=MAX_REASONING_TOKENS,
            temperature=self.config.openai_config.temperature,
            top_p=self.config.openai_config.top_p,
            n=1,
        )

        messages = [
            SystemMessage(content=self.system_prompt),
            UserMessage(content=observation + "\n\n" + REASONING_PROMPT),
        ]

        tool_config = OpenaiToolConfig("none", TOOLS)

        response, usage = chat_with_tools(messages, reasoning_config, tool_config)

        result = response[0]

        if isinstance(result, list):
            LOGGER.error(
                "expected GPT to return a single message, not use tools",
                extra={
                    "tool uses": result,
                },
            )
            raise Exception("expected GPT to return a single message, not use tools")

        return result.content, usage

    def __parse_action(self, result: t.List[OpenaiToolCall]) -> Action:
        call = result[0]

        if call.name == "edit":
            return EditAction(
                new_code=t.cast(str, call.arguments["new_code"]),
            )
        elif call.name == "define":
            return DefinitionsAction(
                identifiers=t.cast(t.List[str], call.arguments["identifiers"]),
            )
        elif call.name == "search":
            return SearchAction(
                identifiers=t.cast(t.List[str], call.arguments["identifiers"]),
            )
        else:
            LOGGER.error(
                "unknown tool",
                extra={
                    "tool": call.name,
                },
            )
            raise Exception(f"unknown tool {call.name}")
