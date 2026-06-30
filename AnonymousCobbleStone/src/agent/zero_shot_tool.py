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
from src.proof_script import ProofScript

LOGGER = get_logger("agent.zero_shot_tool")

SYSTEM_PROMPT = """You are an expert at proving theorems in Coq.
You will be given a proposition, definitions, and some potentially useful lemmas in a user message.
Integrating what you learn from the user message, write a proof of the proposition using no more than 10 tactics.
You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.'"""

SYSTEM_PROMPT_REASONING = """You are an expert at proving theorems in Coq.
You will be given a proposition, definitions, and some potentially useful lemmas in a user message.
Integrating what you learn from the user message, write your reasoning in a section called [REASONING], then write a proof of the proposition using no more than 10 tactics.
You may only use the Coq tactic language. Do not write any vernacular commands like 'Proof.' or 'Qed.'"""

TOOL = OpenaiTool(
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
)


@dataclass
class ZeroShotToolAgentConfig:
    include_reasoning: bool = False
    chat_config: OpenaiChatPromptConfig = OpenaiChatPromptConfig(model="gpt-4", n=1)
    max_reasoning_tokens: int = 500


class ZeroShotToolAgent(Agent[Action, Observation]):
    config: ZeroShotToolAgentConfig
    lemma: str

    def __init__(
        self,
        lemma: str,
        config: ZeroShotToolAgentConfig = ZeroShotToolAgentConfig(),
    ):
        super().__init__()
        self.lemma = lemma
        self.config = config

    def act(self, observation: Observation, n=1) -> t.Tuple[t.List[Action], Usage]:
        usage = Usage(name="zero_shot_tool")

        def run_action(reasoning: t.Optional[str]):
            action, a_usage = self.__get_action(observation, reasoning)
            usage.add_child(a_usage)
            LOGGER.debug("usage", extra={"usage": a_usage, "action": action})
            return action

        try:
            if not self.config.include_reasoning:
                action = run_action(None)
                self.usage.add_child(usage)
                return [action], usage
            else:
                reasonings, r_usage = self.__get_reasoning(observation, n)
                usage.add_child(r_usage)
                actions = [run_action(reasoning) for reasoning in reasonings]
                self.usage.add_child(usage)
                return actions, usage
        except UsageError as e:
            usage.add_child(e.usage)
            self.usage.add_child(usage)
            raise UsageError(str(e), usage) from e

    def __get_reasoning(self, observation: str, n=1) -> t.Tuple[t.List[str], Usage]:
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
            max_tokens=self.config.chat_config.max_tokens,
            n=n,
        )

        response, usage = rate_limited_chat(messages, config)
        messages = [message.content for message in response]

        LOGGER.debug(
            "got reasoning",
            extra={
                "reasoning": messages,
                "observation": observation,
                "usage": usage,
            },
        )

        return messages, usage

    def __get_action(
        self, observation: str, reasoning: t.Optional[str]
    ) -> t.Tuple[Action, Usage]:
        if reasoning:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT_REASONING),
                UserMessage(
                    content=f"""{observation}

[REASONING]
{reasoning}"""
                ),
            ]
        else:
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                UserMessage(content=observation),
            ]

#         if reasoning:
#             messages.append(
#                 AssistantMessage(
#                     content=f"""[REASONING]
# {reasoning}"""
#                 )
#             )

        response, usage = chat_with_tools(
            messages,
            self.config.chat_config,
            OpenaiToolConfig(tools=[TOOL], tool_choice=TOOL),
        )

        result = response[0]

        if isinstance(result, AssistantMessage):
            action = self.__parse_action_from_message(result.content)
            LOGGER.warning(
                "model returned a message instead of a tool call; parsed it as an edit",
                extra={
                    "content": result.content,
                    "action": action,
                },
            )
            return action, usage

        try:
            return self.__parse_action(result), usage
        except Exception as e:
            raise UsageError(str(e), usage) from e

    def __parse_action_from_message(self, content: str) -> Action:
        for code in self.__candidate_code_blocks(content):
            new_code = remove_extra_curly_brace(code)
            if self.__is_valid_proof_script(new_code):
                return EditAction(new_code=new_code)

        LOGGER.error(
            "expected GPT to use tools, and could not parse message as a proof script",
            extra={"content": content},
        )
        return EditAction(new_code="")

    def __candidate_code_blocks(self, content: str) -> t.List[str]:
        candidates: t.List[str] = []
        for match in re.finditer(r"```(?:coq)?\s*(.*?)```", content, re.DOTALL):
            candidates.append(match.group(1).strip())
        if "[PROOF]" in content:
            candidates.append(content.split("[PROOF]", 1)[1].strip())
        candidates.append(content.strip())
        return candidates

    def __parse_action(self, result: t.List[OpenaiToolCall]) -> Action:
        call = result[0]

        if call.name == "edit":
            new_code = remove_extra_curly_brace(t.cast(str, call.arguments["new_code"]))
            return EditAction(
                new_code=new_code if self.__is_valid_proof_script(new_code) else "",
            )
        else:
            LOGGER.error(
                "unknown tool",
                extra={
                    "tool": call.name,
                },
            )
            raise Exception(f"unknown tool {call.name}")

    def __is_valid_proof_script(self, code: str) -> bool:
        try:
            proof_script = ProofScript.parse(code)
            if proof_script.has_admit:
                LOGGER.warning(
                    "invalid LLM completion. script contains an admit. Ignoring it.",
                    extra={
                        "proof_script": proof_script,
                    },
                )
                return False
            else:
                return True
        except Exception as e:
            LOGGER.warning(
                "invalid LLM completion. failed to parse LLM completion",
                extra={
                    "code": code,
                    "error": str(e),
                },
            )
            return False
