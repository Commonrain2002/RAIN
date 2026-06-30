#!/usr/bin/env python3
from __future__ import annotations

import unittest

from BatchTest.proofagent_token_log import parse_token_usage_from_text


class ProofagentTokenLogParseTests(unittest.TestCase):
    def test_cumulative_with_cache(self) -> None:
        text = (
            "[12:00:00 INF] Cumulative tokens (loop ChatAsync sum): prompt=100 promptCacheHitTokens=40 "
            "promptCacheMissTokens=60 completion=10 total=110\n"
            "[12:00:00 ERR] Proof check did not pass\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "cumulative")
        self.assertEqual(p.prompt, 100)
        self.assertEqual(p.prompt_cache_hit, 40)
        self.assertEqual(p.prompt_cache_miss, 60)
        self.assertEqual(p.completion, 10)
        self.assertEqual(p.total, 110)

    def test_cumulative_legacy_without_cache(self) -> None:
        text = "Cumulative tokens: prompt=1 completion=2 total=3\n"
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "cumulative")
        self.assertEqual((p.prompt, p.completion, p.total), (1, 2, 3))
        self.assertIsNone(p.prompt_cache_hit)

    def test_session_cumulative_only_returns_none(self) -> None:
        text = (
            "[22:14:24 INF] LLM usage: reasoning=Deep round=9/5000\n"
            "promptTokens=1\n"
            "sessionCumulativePromptTokens=10\n"
            "sessionCumulativePromptCacheHitTokens=20\n"
            "sessionCumulativePromptCacheMissTokens=30\n"
            "sessionCumulativeCompletionTokens=40\n"
            "sessionCumulativeTotalTokens=50\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "none")
        self.assertIsNone(p.total)

    def test_session_cumulative_inline_legacy_returns_none(self) -> None:
        text = (
            "[INF] LLM usage: reasoning=Deep round=2/5000 promptTokens=3 completionTokens=4 "
            "totalTokens=7 sessionCumulativePromptTokens=4 sessionCumulativeCompletionTokens=5 "
            "sessionCumulativeTotalTokens=9\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "none")
        self.assertIsNone(p.total)

    def test_cumulative_wins_over_earlier_llm_usage(self) -> None:
        text = (
            "sessionCumulativePromptTokens=999 sessionCumulativeCompletionTokens=1 "
            "sessionCumulativeTotalTokens=1000\n"
            "Cumulative tokens (loop ChatAsync sum): prompt=10 promptCacheHitTokens=1 promptCacheMissTokens=9 "
            "completion=2 total=12\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "cumulative")
        self.assertEqual(p.total, 12)

    def test_run_cumulative_http_wins_over_loop_summary(self) -> None:
        text = (
            "[INF] Cumulative tokens (loop ChatAsync sum): prompt=10 completion=2 total=12\n"
            "[INF] Run cumulative tokens (all HTTP): prompt=20 promptCacheHitTokens=5 "
            "promptCacheMissTokens=15 completion=4 total=24\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "run_cumulative_http")
        self.assertEqual((p.prompt, p.completion, p.total), (20, 4, 24))

    def test_llm_usage_multiline_run_cumulative(self) -> None:
        text = (
            "[INF] LLM usage: reasoning=Deep round=2/5000\n"
            "promptTokens=1\n"
            "sessionCumulativeTotalTokens=50\n"
            "runCumulativePromptTokens=100\n"
            "runCumulativePromptCacheHitTokens=40\n"
            "runCumulativePromptCacheMissTokens=60\n"
            "runCumulativeCompletionTokens=10\n"
            "runCumulativeTotalTokens=110\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "llm_usage_run_cumulative")
        self.assertEqual(p.total, 110)
        self.assertEqual(p.prompt, 100)

    def test_timeout_uses_last_run_cumulative_not_session(self) -> None:
        # No Program.cs footer; last HTTP event includes process-wide runCumulative (plan + proof).
        text = (
            "runCumulativePromptTokens=1000000\n"
            "runCumulativePromptCacheHitTokens=900000\n"
            "runCumulativePromptCacheMissTokens=100000\n"
            "runCumulativeCompletionTokens=10000\n"
            "runCumulativeTotalTokens=1010000\n"
            "[INF] LLM usage: reasoning=Deep round=52/5000\n"
            "promptTokens=75289\n"
            "sessionCumulativePromptTokens=2289558\n"
            "sessionCumulativePromptCacheHitTokens=2262528\n"
            "sessionCumulativePromptCacheMissTokens=27030\n"
            "sessionCumulativeCompletionTokens=51289\n"
            "sessionCumulativeTotalTokens=2340847\n"
            "runCumulativePromptTokens=2953464\n"
            "runCumulativePromptCacheHitTokens=2890240\n"
            "runCumulativePromptCacheMissTokens=63224\n"
            "runCumulativeCompletionTokens=47224\n"
            "runCumulativeTotalTokens=3000688\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "llm_usage_run_cumulative")
        self.assertEqual(p.total, 3000688)
        self.assertEqual(p.prompt, 2953464)

    def test_timeout_truncated_before_run_cumulative_returns_none(self) -> None:
        text = (
            "[INF] LLM usage: reasoning=Deep round=113/5000\n"
            "sessionCumulativePromptTokens=8766233\n"
            "sessionCumulativePromptCacheHitTokens=8715776\n"
            "sessionCumulativePromptCacheMissTokens=50457\n"
            "sessionCumulativeCompletionTokens=110767\n"
            "sessionCumulativeTotalTokens=8877000\n"
        )
        p = parse_token_usage_from_text(text)
        self.assertEqual(p.source, "none")
        self.assertIsNone(p.total)


if __name__ == "__main__":
    unittest.main()
