"""Tests for Codex token parsing (session authoritative, exec stdout fallback)."""

from __future__ import annotations

from codex_token_log import (
    parse_agent_run_seconds_from_session_json_text,
    parse_token_usage_from_codex_exec_json_text,
    parse_token_usage_from_session_json_text,
)


def test_parse_session_token_count_final_total() -> None:
    text = "\n".join(
        [
            '{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{'
            '"input_tokens":10000,"cached_input_tokens":8000,"output_tokens":100,'
            '"reasoning_output_tokens":20,"total_tokens":10100}}}}',
            '{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{'
            '"input_tokens":248161,"cached_input_tokens":207232,"output_tokens":3834,'
            '"reasoning_output_tokens":2138,"total_tokens":251995}}}}',
        ]
    )
    parsed = parse_token_usage_from_session_json_text(text, session_rollout_path="/tmp/t.jsonl")
    assert parsed.source == "codex_session_jsonl"
    assert parsed.prompt == 248161
    assert parsed.prompt_cache_hit == 207232
    assert parsed.prompt_cache_miss == 40929
    assert parsed.completion == 3834 + 2138
    assert parsed.reasoning == 2138
    assert parsed.total == 254133
    assert parsed.prompt_cache_hit + parsed.prompt_cache_miss + parsed.completion == parsed.total
    assert parsed.session_rollout_path == "/tmp/t.jsonl"


def test_parse_session_agent_run_seconds_from_timestamps() -> None:
    text = "\n".join(
        [
            '{"type":"session_meta","timestamp":"2026-06-14T14:20:22.843Z"}',
            '{"type":"event_msg","timestamp":"2026-06-14T14:20:30.000Z"}',
            '{"type":"response_item","timestamp":"2026-06-14T14:46:20.626Z"}',
        ]
    )
    seconds = parse_agent_run_seconds_from_session_json_text(text)
    assert seconds == 1558


def test_parse_exec_stdout_turn_completed_fallback() -> None:
    text = (
        '{"type":"turn.completed","usage":{'
        '"input_tokens":248161,"cached_input_tokens":207232,'
        '"output_tokens":3834,"reasoning_output_tokens":2138}}'
    )
    parsed = parse_token_usage_from_codex_exec_json_text(text)
    assert parsed.source == "codex_exec_jsonl"
    assert parsed.prompt == 248161
    assert parsed.prompt_cache_hit == 207232
    assert parsed.prompt_cache_miss == 40929
    assert parsed.completion == 3834 + 2138
    assert parsed.total == 254133
    assert parsed.prompt_cache_hit + parsed.prompt_cache_miss + parsed.completion == parsed.total


def test_parse_session_uncached_input_rollup() -> None:
    text = (
        '{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{'
        '"input_tokens":83276,"cached_input_tokens":74496,"output_tokens":1288,'
        '"reasoning_output_tokens":370,"total_tokens":84564}}}}'
    )
    parsed = parse_token_usage_from_session_json_text(text)
    assert parsed.prompt == 157772
    assert parsed.prompt_cache_hit == 74496
    assert parsed.prompt_cache_miss == 83276
    assert parsed.completion == 1288 + 370
    assert parsed.total == 159430
    assert parsed.prompt + parsed.completion == parsed.total


def test_parse_session_id65_style_completion_includes_reasoning() -> None:
    text = (
        '{"type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{'
        '"input_tokens":481675,"cached_input_tokens":429312,"output_tokens":6121,'
        '"reasoning_output_tokens":3438,"total_tokens":487796}}}}'
    )
    parsed = parse_token_usage_from_session_json_text(text)
    assert parsed.prompt == 481675
    assert parsed.completion == 6121 + 3438
    assert parsed.total == 491234
    assert parsed.prompt + parsed.completion == parsed.total
