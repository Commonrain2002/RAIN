from typing import Dict, List, Tuple, Union, Literal, Optional
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from src.format_prompt import format_message_section


ActionType = Literal["EDIT", "DEFINITIONS", "SEARCH", "APPEND", "REPLACE"]


@dataclass
class BaseAction(ABC):
    type: ActionType

    @abstractmethod
    def format(
        self,
        action_type_to_description: Dict[ActionType, str],
        title_start_delimiter: str = "<<",
        title_end_delimiter: str = ">>",
    ) -> str:
        pass


@dataclass
class EditAction(BaseAction):
    type: Literal["EDIT"] = "EDIT"
    new_code: str = ""

    def format(
        self,
        action_type_to_description: Dict[ActionType, str],
        title_start_delimiter: str = "<<",
        title_end_delimiter: str = ">>",
    ) -> str:
        sections: List[Tuple[str, str]] = [
            ("BEST OPTION", action_type_to_description[self.type]),
            ("REVISED CODE", self.new_code),
        ]
        return "\n".join(
            format_message_section(
                title, content, title_start_delimiter, title_end_delimiter
            )
            for title, content in sections
        )


@dataclass
class AppendAction(BaseAction):
    type: Literal["APPEND"] = "APPEND"
    tactics_to_append: str = ""

    def format(
        self,
        action_type_to_description: Dict[ActionType, str],
        title_start_delimiter: str = "<<",
        title_end_delimiter: str = ">>",
    ) -> str:
        raise Exception("not implemented")


@dataclass
class ReplaceAction(BaseAction):
    type: Literal["REPLACE"] = "REPLACE"
    start_index: Optional[int] = None
    end_index: Optional[int] = None
    new_tactics: str = ""

    def format(
        self,
        action_type_to_description: Dict[ActionType, str],
        title_start_delimiter: str = "<<",
        title_end_delimiter: str = ">>",
    ) -> str:
        raise Exception("not implemented")


@dataclass
class DefinitionsAction(BaseAction):
    type: Literal["DEFINITIONS"] = "DEFINITIONS"
    identifiers: List[str] = field(default_factory=list)

    def format(
        self,
        action_type_to_description: Dict[ActionType, str],
        title_start_delimiter: str = "<<",
        title_end_delimiter: str = ">>",
    ) -> str:
        sections: List[Tuple[str, str]] = [
            ("BEST OPTION", action_type_to_description[self.type]),
            ("IDENTIFIERS", ", ".join(self.identifiers)),
        ]
        return "\n".join(
            format_message_section(
                title, content, title_start_delimiter, title_end_delimiter
            )
            for title, content in sections
        )


@dataclass
class SearchAction(BaseAction):
    type: Literal["SEARCH"] = "SEARCH"
    identifiers: List[str] = field(default_factory=list)

    def format(
        self,
        action_type_to_description: Dict[ActionType, str],
        title_start_delimiter: str = "<<",
        title_end_delimiter: str = ">>",
    ) -> str:
        sections: List[Tuple[str, str]] = [
            ("BEST OPTION", action_type_to_description[self.type]),
            ("IDENTIFIERS", ", ".join(self.identifiers)),
        ]
        return "\n".join(
            format_message_section(
                title, content, title_start_delimiter, title_end_delimiter
            )
            for title, content in sections
        )


Action = Union[EditAction, DefinitionsAction, SearchAction]
ConstrainedEditAction = Union[
    AppendAction, ReplaceAction, DefinitionsAction, SearchAction
]
CodeAction = Union[EditAction, AppendAction, ReplaceAction]
