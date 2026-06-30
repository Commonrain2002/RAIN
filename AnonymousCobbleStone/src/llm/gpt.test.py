import datetime
from typing import List
import logging


from src.llm import (
    AssistantMessage,
    ChatMessage,
    SystemMessage,
    UserMessage,
)

from src.llm.gpt import (
    chat,
    rate_limited_chat,
    OpenaiChatPromptConfig,
)

"""
informal (non-unit) tests of prompt.py
"""

# confirmed to have 1000 tokens using https://platform.openai.com/tokenizer
STRING_WITH_1000_TOKENS = """the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog
the quick brown fox jumped over the lazy red dog

the"""


def test_gpt4_rate_limiting():
    """
    test that gpt4 rate limiting works
    """
    messages: List[ChatMessage] = [
        SystemMessage(content=STRING_WITH_1000_TOKENS),
        UserMessage(
            content="\n".join(
                [
                    STRING_WITH_1000_TOKENS,
                    STRING_WITH_1000_TOKENS,
                    STRING_WITH_1000_TOKENS,
                ]
            )
        ),
    ]
    config = OpenaiChatPromptConfig("gpt-4", 100)

    for _ in range(50):
        logging.info(f"running rate_limited_chat at {datetime.datetime.now()}")
        rate_limited_chat(messages, config)


if __name__ == "__main__":
    test_gpt4_rate_limiting()
