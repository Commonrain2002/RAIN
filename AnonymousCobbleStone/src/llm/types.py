from dataclasses import dataclass, field
import typing as t

from src.utils import JSON
from src.config import CONFIG
from src.llm.model_names import is_deepseek_model


@dataclass
class ChatMessage:
    # one of "user", "assistant" or "system"
    role: t.Literal["user", "assistant", "system"] = "user"
    content: str = ""

    def anthropic_dict(self):
        raise NotImplementedError("anthropic_dict not implemented for base ChatMessage class")

    def openai_dict(self):
        raise NotImplementedError("openai_dict not implemented for base ChatMessage class")


@dataclass
class UserMessage(ChatMessage):
    role: t.Literal["user"] = "user"

    def anthropic_dict(self):
        return {
            "role": "user",
            "content": self.content,
        }
    
    def openai_dict(self):
        return {
            "role": "user",
            "content": self.content,
        }


@dataclass
class AssistantMessage(ChatMessage):
    role: t.Literal["assistant"] = "assistant"
    reasoning_content: t.Optional[str] = None

    def anthropic_dict(self):
        return {
            "role": "assistant",
            "content": self.content,
        }

    def openai_dict(self):
        payload: t.Dict[str, t.Any] = {
            "role": "assistant",
            "content": self.content or "",
        }
        if self.reasoning_content:
            payload["reasoning_content"] = self.reasoning_content
        return payload


@dataclass
class SystemMessage(ChatMessage):
    role: t.Literal["system"] = "system"

    def anthropic_dict(self):
        return {
            "role": "user",
            "content": self.content,
        }
    
    def openai_dict(self):
        return {
            "role": "system",
            "content": self.content,
        }


@dataclass
class ChatTrace:
    system_message: t.Optional[SystemMessage]
    final_user_message: UserMessage
    interactions: t.List[t.Tuple[UserMessage, AssistantMessage]] = field(
        default_factory=list
    )


LLMSampler = t.Callable[[ChatTrace], t.List[AssistantMessage]]

Config = t.TypeVar("Config")
LLM = t.Callable[[Config], LLMSampler]


OpenaiChatModelName = t.Literal[
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
    "claude-3-opus-20240229",
    "deepseek-chat",
    "deepseek-reasoner",
    "deepseek-v4-flash",
]

OpenaiPromptModelName = t.Literal["ada", "babbage", "curie", "davinci"]
OPENAI_COMPLETION_MODEL_NAMES = ["ada", "babbage", "curie", "davinci"]

OpenaiModelName = t.Union[OpenaiChatModelName, OpenaiPromptModelName]

OPENAI_MAX_TOKENS = {
    "meta-llama-3.1-405b-instruct": 128_000,
    "gpt-3.5-turbo-1106": 16_385,
    "gpt-3.5-turbo-0125": 16_385,
    "gpt-3.5-turbo": 4_096,
    "gpt-4": 8_192,
    "deepseek-chat": 64_000,
    "deepseek-reasoner": 64_000,
    "deepseek-v4-flash": 1_000_000,
    "ada": 2_049,
    "babbage": 2_049,
    "curie": 2_049,
    "davinci": 2_049,
    "claude-3-opus-20240229": 10_000
}

# from the table in https://platform.openai.com/account/rate-limits
RATE_LIMIT_TOKENS_PER_MINUTE: t.Dict[OpenaiChatModelName, int] = {
    "meta-llama-3.1-405b-instruct": 10_000,
    "gpt-3.5-turbo": 350_000,
    "gpt-4": 10_000,
    "deepseek-chat": 10_000,
    "deepseek-reasoner": 10_000,
    "deepseek-v4-flash": 350_000,
    "gpt-3.5-turbo-1106": 350_000,
    "gpt-3.5-turbo-0125": 350_000,
    "claude-3-opus-20240229": 20_000
}

RATE_LIMIT_REQUESTS_PER_MINUTE: t.Dict[OpenaiChatModelName, int] = {
    "meta-llama-3.1-405b-instruct": 10,
    "gpt-3.5-turbo": 4_000,
    "gpt-3.5-turbo-1106": 4_000,
    "gpt-4": 200,
    "deepseek-chat": 200,
    "deepseek-reasoner": 200,
    "deepseek-v4-flash": 4000,
    "gpt-3.5-turbo-0125": 4_000,
    "claude-3-opus-20240229": 50
}


@dataclass(frozen=True)
class OpenaiChatPromptConfig:
    model: OpenaiChatModelName = "gpt-4"
    # max_tokens: t.Optional[int] = None
    max_tokens: int = CONFIG.MAX_CHAT_COMPLETION_TOKENS
    temperature: float = 1
    top_p: float = 1
    n: int = 1


@dataclass(frozen=True)
class OpenaiTool:
    description: str
    name: str
    parameters: t.Dict[str, JSON]

    def as_dict(self):
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
    
    def as_anthropic_dict(self):
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters,
        }


OpenaiToolChoice = t.Union[t.Literal["auto", "none"], OpenaiTool]


@dataclass
class OpenaiToolConfig:
    tool_choice: OpenaiToolChoice = "auto"
    tools: t.Optional[t.List[OpenaiTool]] = None

    def as_dict(self, model: t.Optional[str] = None):
        if self.tools is None:
            return {}
        if isinstance(self.tool_choice, OpenaiTool):
            # DeepSeek thinking mode + tools: API rejects forced function tool_choice.
            if model is not None and is_deepseek_model(model):
                tool_choice: t.Union[str, t.Dict[str, JSON]] = "auto"
            else:
                tool_choice = {
                    "type": "function",
                    "function": {"name": self.tool_choice.name},
                }
        else:
            tool_choice = self.tool_choice
        return {
            "tools": [tool.as_dict() for tool in self.tools],
            "tool_choice": tool_choice,
        }
    
    def as_anthropic_dict(self):
        if self.tools is None:
            return {}
        else:
            return (
                {
                    "tools": [tool.as_anthropic_dict() for tool in self.tools],
                    "tool_choice": (
                        {
                            "type": "tool",
                            "name": self.tool_choice.name,
                        }
                            if isinstance(self.tool_choice, OpenaiTool)
                            else self.tool_choice
                        ),
                    }
        )


@dataclass
class OpenaiToolCall:
    name: str
    arguments: t.Dict[str, JSON]
    id: str
