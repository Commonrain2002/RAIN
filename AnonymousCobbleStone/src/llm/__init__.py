"""
This module hosts code to perform inference on different LLMs,
including:

- llemma-7B
- code-llama-instruct-7B
- gpt-3.5
- gpt-4
"""

from src.llm.types import (
    ChatMessage,
    AssistantMessage,
    UserMessage,
    SystemMessage,
    ChatTrace,
    OpenaiToolCall,
    OpenaiChatPromptConfig,
    OpenaiToolConfig,
    OpenaiTool,
)

from src.llm.usage import Usage, UsageError

from src.llm.gpt import chat, chat_with_tools, rate_limited_chat
