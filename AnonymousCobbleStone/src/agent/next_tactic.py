from dataclasses import dataclass
import re
import typing as t

from src.environment.actions import EditAction
from src.utils import get_logger, remove_extra_curly_brace
from src.llm import (
    rate_limited_chat,
    OpenaiChatPromptConfig,
    OpenaiTool,
    OpenaiToolCall,
    OpenaiToolConfig,
    chat_with_tools,
    Usage,
    UsageError,
    AssistantMessage,
    SystemMessage,
    UserMessage,
)
from src.environment import Action, Observation
from src.agent.agent import Agent
from src.proof_script import Tactic, read_tactics

LOGGER = get_logger("agent.next_tactic")

SYSTEM_PROMPT = """You are an expert at proving theorems in Coq.
You will be given a proof context, definitions, and some potentially useful lemmas in a user message.
Your task is to write down the next tactic in a correct proof of the proposition.

Integrating what you learn from the user message, write down the next tactic.

You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.'
Write only one tactic."""

SYSTEM_PROMPT_REASONING = """You are an expert at proving theorems in Coq.
You will be given a proof context, definitions, and some potentially useful lemmas in a user message.
Your task is to write down the next tactic in a correct proof of the proposition.

Integrating what you learn from the user message, write your reasoning in a section called [REASONING], then write down the next tactic.

You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.'
Write only one tactic."""

TOOL = OpenaiTool(
    name="predict_next_tactic",
    description="Predict the next tactic in the proof",
    parameters={
        "type": "object",
        "properties": {
            "next_tactic": {
                "type": "string",
                "description": "the next tactic in the proof script, which should only use tactics from the Coq tactic language. This code should only mention identifiers from the user message or lemmas from the standard library.",
            }
        },
    },
)


@dataclass
class NextTacticAgentConfig:
    include_reasoning: bool = False
    chat_config: OpenaiChatPromptConfig = OpenaiChatPromptConfig(model="gpt-4", n=1)
    max_reasoning_tokens: int = 500


class NextTacticAgent(Agent[Action, Observation]):
    config: NextTacticAgentConfig
    lemma: str

    def __init__(
        self,
        lemma: str,
        config: NextTacticAgentConfig = NextTacticAgentConfig(),
    ):
        super().__init__()
        self.lemma = lemma
        self.config = config

    def act(self, observation: Observation, n=1) -> t.Tuple[t.List[Action], Usage]:
        usage = Usage(name="next_tactic")

        def run_action(reasoning: t.Optional[AssistantMessage], n: int):
            actions, a_usage = self.__get_action(observation, reasoning, n)
            usage.add_child(a_usage)
            return actions

        try:
            if not self.config.include_reasoning:
                actions = run_action(None, n)
                self.usage.add_child(usage)
                return actions, usage
            else:
                reasonings, r_usage = self.__get_reasoning(observation, n)
                usage.add_child(r_usage)
                actions = [run_action(reasoning, 1)[0] for reasoning in reasonings]
                self.usage.add_child(usage)
                return actions, usage
        except UsageError as e:
            usage.add_child(e.usage)
            self.usage.add_child(usage)
            raise UsageError(str(e), usage) from e

    def __get_reasoning(self, observation: str, n=1) -> t.Tuple[t.List[AssistantMessage], Usage]:
        messages = [
            SystemMessage(content=SYSTEM_PROMPT_REASONING),
            UserMessage(
                content=f"""{observation}

[REASONING]"""
            ),
        ]

        config = OpenaiChatPromptConfig(
            model=self.config.chat_config.model,
            temperature=self.config.chat_config.temperature,
            top_p=self.config.chat_config.top_p,
            max_tokens=self.config.max_reasoning_tokens,
            n=n,
        )

        response, usage = rate_limited_chat(messages, config)
        reasoning_messages = response

        LOGGER.debug(
            "got reasoning",
            extra={
                "reasoning": [m.content for m in reasoning_messages],
                "observation": observation,
                "usage": usage,
            },
        )

        return reasoning_messages, usage

    def __get_action(
        self, observation: str, reasoning: t.Optional[AssistantMessage], n: int
    ) -> t.Tuple[t.List[Action], Usage]:
        messages = [
            SystemMessage(
                content=SYSTEM_PROMPT if not reasoning else SYSTEM_PROMPT_REASONING
            ),
            UserMessage(content=observation),
        ]

        if reasoning:
            if reasoning.reasoning_content and not reasoning.content.strip().startswith(
                "[REASONING]"
            ):
                messages.append(
                    AssistantMessage(
                        content=reasoning.content or "",
                        reasoning_content=reasoning.reasoning_content,
                    )
                )
            else:
                messages.append(
                    AssistantMessage(
                        content=f"""[REASONING]
{reasoning.content}""",
                        reasoning_content=reasoning.reasoning_content,
                    )
                )

        config = OpenaiChatPromptConfig(
            model=self.config.chat_config.model,
            temperature=self.config.chat_config.temperature,
            top_p=self.config.chat_config.top_p,
            max_tokens=self.config.chat_config.max_tokens,
            n=n,
        )

        response, usage = chat_with_tools(
            messages,
            config,
            OpenaiToolConfig(tools=[TOOL], tool_choice=TOOL),
        )

        actions: t.List[Action] = []
        for result in response:
            if isinstance(result, AssistantMessage):
                action = self.__parse_action_from_message(result.content)
                LOGGER.error(
                    "model returned a message instead of a tool call; parsed it as a tactic",
                    extra={
                        "content": result.content,
                        "action": action,
                    },
                )
                actions.append(action)
            else:
                try:
                    actions.append(self.__parse_action(t.cast(t.List[OpenaiToolCall], result)))
                except Exception as e:
                    raise UsageError(str(e), usage) from e

        return actions, usage

    def __parse_action_from_message(self, content: str) -> Action:
        for code in _candidate_code_blocks(content):
            tactic = fixup_gpt_tactic(code)
            if tactic.strip():
                return EditAction(new_code=tactic)
        return EditAction(new_code="")

    def __parse_action(self, result: t.List[OpenaiToolCall]) -> Action:
        call = result[0]

        if call.name == "predict_next_tactic":
            new_code = fixup_gpt_tactic(t.cast(str, call.arguments["next_tactic"]))
            return EditAction(
                new_code=new_code,
            )
        else:
            LOGGER.error(
                "unknown tool",
                extra={
                    "tool": call.name,
                },
            )
            raise Exception(f"unknown tool {call.name}")


def fixup_gpt_tactic(code: str) -> str:
    code = remove_extra_curly_brace(code).strip()
    tactics = try_to_parse_tactics(code)
    if tactics is None:
        # give up and return code as is
        return code

    tactic = next(
        (
            tactic
            for tactic in tactics
            if not tactic.is_bullet
            and not tactic.is_open_brace
            and not tactic.is_close_brace
            and not tactic.text == "admit."
        ),
        None,
    )

    if tactic is None:
        return code

    return tactic.text


def _candidate_code_blocks(content: str) -> t.List[str]:
    candidates: t.List[str] = []
    for match in re.finditer(r"```(?:coq)?\s*(.*?)```", content, re.DOTALL):
        candidates.append(match.group(1).strip())
    if "[PROOF]" in content:
        candidates.append(content.split("[PROOF]", 1)[1].strip())
    candidates.append(content.strip())
    return candidates


def try_to_parse_tactics(code: str) -> t.Optional[t.List[Tactic]]:
    try:
        return read_tactics(code)
    except:
        pass

    if code.endswith(";"):
        code = code[:-1]

    if not code.endswith("."):
        code += "."
        try:
            return read_tactics(code)
        except:
            pass

    return None
