import typing as t
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from src.llm.types import OpenaiChatModelName, OpenaiChatPromptConfig
from src.utils import JSON
import uuid


class UsageError(Exception):
    def __init__(self, message: str, usage: "Usage"):
        super().__init__(message)
        self.usage = usage


@dataclass
class Usage:
    name: str
    model: t.Optional[OpenaiChatModelName] = None

    end_time: datetime = field(default_factory=datetime.now)
    duration_millis: int = 0

    num_input_tokens: int = 0
    num_output_tokens: int = 0
    num_tokens: int = 0
    num_requests: int = 0
    num_cache_hit_read_tokens: int = 0
    num_cache_miss_read_tokens: int = 0
    num_cache_write_tokens: int = 0
    num_reasoning_tokens: int = 0

    children: t.List["Usage"] = field(default_factory=list)

    uuid: str = field(default_factory=lambda: str(uuid.uuid4()))

    @property
    def start_time(self) -> datetime:
        return self.end_time - timedelta(milliseconds=self.duration_millis)

    def add_child(self, child: "Usage"):
        assert self.model is None or self.model == child.model
        self.children.append(child)

        self.end_time = max(self.end_time, child.end_time)
        self.duration_millis += child.duration_millis

        self.num_input_tokens += child.num_input_tokens
        self.num_output_tokens += child.num_output_tokens
        self.num_tokens += child.num_tokens
        self.num_requests += child.num_requests
        self.num_cache_hit_read_tokens += child.num_cache_hit_read_tokens
        self.num_cache_miss_read_tokens += child.num_cache_miss_read_tokens
        self.num_cache_write_tokens += child.num_cache_write_tokens
        self.num_reasoning_tokens += child.num_reasoning_tokens

    def __add__(self, other: "Usage") -> "Usage":
        assert self.model is None or self.model == other.model
        return Usage(
            name=self.name,
            model=self.model or other.model,
            end_time=max(self.end_time, other.end_time),
            duration_millis=self.duration_millis + other.duration_millis,
            num_input_tokens=self.num_input_tokens + other.num_input_tokens,
            num_output_tokens=self.num_output_tokens + other.num_output_tokens,
            num_tokens=self.num_tokens + other.num_tokens,
            num_requests=self.num_requests + other.num_requests,
            num_cache_hit_read_tokens=(
                self.num_cache_hit_read_tokens + other.num_cache_hit_read_tokens
            ),
            num_cache_miss_read_tokens=(
                self.num_cache_miss_read_tokens + other.num_cache_miss_read_tokens
            ),
            num_cache_write_tokens=(
                self.num_cache_write_tokens + other.num_cache_write_tokens
            ),
            num_reasoning_tokens=self.num_reasoning_tokens
            + other.num_reasoning_tokens,
            children=self.children + other.children,
        )
    
    @classmethod
    def from_anthropic_response(
        cls,
        name: str,
        config: OpenaiChatPromptConfig,
        response: t.Any,
        start_time: datetime,
        end_time: datetime,
    ):
        duration_millis = int((end_time - start_time).total_seconds() * 1000)
        return cls(
            name=name,
            model=config.model,
            end_time=end_time,
            duration_millis=duration_millis,
            num_input_tokens=response.usage.input_tokens,
            num_output_tokens=response.usage.output_tokens,
            num_tokens=response.usage.input_tokens + response.usage.output_tokens,
            num_requests=1,
        )

    @classmethod
    def from_openai_response(
        cls,
        name: str,
        config: OpenaiChatPromptConfig,
        response: t.Any,
        start_time: datetime,
        end_time: datetime,
    ):
        duration_millis = int((end_time - start_time).total_seconds() * 1000)
        usage = response.usage
        return cls(
            name=name,
            model=config.model,
            end_time=end_time,
            duration_millis=duration_millis,
            num_input_tokens=_get_usage_int(usage, "prompt_tokens"),
            num_output_tokens=_get_usage_int(usage, "completion_tokens"),
            num_tokens=_get_usage_int(usage, "total_tokens"),
            num_requests=1,
            num_cache_hit_read_tokens=_get_usage_int(
                usage, "prompt_cache_hit_tokens"
            ),
            num_cache_miss_read_tokens=_get_usage_int(
                usage, "prompt_cache_miss_tokens"
            ),
            num_cache_write_tokens=_first_usage_int(
                usage,
                [
                    "prompt_cache_write_tokens",
                    "cache_write_tokens",
                    "cache_creation_input_tokens",
                ],
            ),
            num_reasoning_tokens=_get_nested_usage_int(
                usage, ["completion_tokens_details", "reasoning_tokens"]
            ),
        )

    def to_json(self) -> t.Dict[str, JSON]:
        return {
            "name": self.name,
            "model": self.model,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "duration_millis": self.duration_millis,
            "num_tokens": self.num_tokens,
            "num_input_tokens": self.num_input_tokens,
            "num_output_tokens": self.num_output_tokens,
            "num_requests": self.num_requests,
            "num_cache_hit_read_tokens": self.num_cache_hit_read_tokens,
            "num_cache_miss_read_tokens": self.num_cache_miss_read_tokens,
            "num_cache_write_tokens": self.num_cache_write_tokens,
            "num_reasoning_tokens": self.num_reasoning_tokens,
            "children": [child.to_json() for child in self.children],
            "uuid": self.uuid,
        }

    @classmethod
    def from_json(cls, data: t.Dict[str, JSON]):
        name = t.cast(str, data["name"])
        model = t.cast(t.Optional[OpenaiChatModelName], data["model"])
        end_time = datetime.fromisoformat(t.cast(str, data["end_time"]))
        duration_millis = t.cast(int, data["duration_millis"])
        num_input_tokens = t.cast(int, data["num_input_tokens"])
        num_output_tokens = t.cast(int, data["num_output_tokens"])
        num_tokens = t.cast(int, data["num_tokens"])
        num_requests = t.cast(int, data["num_requests"])
        num_cache_hit_read_tokens = t.cast(int, data["num_cache_hit_read_tokens"])
        num_cache_miss_read_tokens = t.cast(int, data["num_cache_miss_read_tokens"])
        num_cache_write_tokens = t.cast(int, data["num_cache_write_tokens"])
        num_reasoning_tokens = t.cast(int, data["num_reasoning_tokens"])
        uuid = t.cast(str, data["uuid"])

        children = [
            cls.from_json(child)
            for child in t.cast(t.List[t.Dict[str, JSON]], data["children"])
        ]

        return cls(
            name=name,
            model=model,
            end_time=end_time,
            duration_millis=duration_millis,
            num_input_tokens=num_input_tokens,
            num_output_tokens=num_output_tokens,
            num_tokens=num_tokens,
            num_requests=num_requests,
            num_cache_hit_read_tokens=num_cache_hit_read_tokens,
            num_cache_miss_read_tokens=num_cache_miss_read_tokens,
            num_cache_write_tokens=num_cache_write_tokens,
            num_reasoning_tokens=num_reasoning_tokens,
            children=children,
            uuid=uuid,
        )

    def compute_treemap(
        self,
        property: t.Literal[
            "num_tokens",
            "num_input_tokens",
            "num_output_tokens",
            "num_requests",
            "num_cache_hit_read_tokens",
            "num_cache_miss_read_tokens",
            "num_cache_write_tokens",
            "num_reasoning_tokens",
            "duration_millis",
        ],
        prefix: str = "",
    ) -> str:
        """
        outputs value in format for webtreemap
        https://github.com/danvk/webtreemap?tab=readme-ov-file
        """
        value = str(getattr(self, property))
        path = f"{prefix}/{self.name}_{self.uuid}" if prefix != "" else self.name
        ans = f"{value} {path}\n"
        for child in self.children:
            ans += child.compute_treemap(property, path)
        return ans


def _get_usage_value(usage: t.Any, key: str) -> t.Any:
    if isinstance(usage, dict):
        return usage.get(key)
    if hasattr(usage, key):
        return getattr(usage, key)
    try:
        return usage[key]
    except (KeyError, TypeError):
        return None


def _get_usage_int(usage: t.Any, key: str) -> int:
    value = _get_usage_value(usage, key)
    return int(value) if value is not None else 0


def _first_usage_int(usage: t.Any, keys: t.List[str]) -> int:
    for key in keys:
        value = _get_usage_value(usage, key)
        if value is not None:
            return int(value)
    return 0


def _get_nested_usage_int(usage: t.Any, keys: t.List[str]) -> int:
    value = usage
    for key in keys:
        value = _get_usage_value(value, key)
        if value is None:
            return 0
    return int(value)
