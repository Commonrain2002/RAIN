#!/usr/bin/env python3
"""Summarize DeepSeek usage.json cache-token costs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEEPSEEK_V4_FLASH_PRICE_PER_1M = {
    "cache_hit_input": 0.0028,
    "cache_miss_input": 0.14,
    "output": 0.28,
}


def as_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key, 0)
    return int(value) if value is not None else 0


def cost(tokens: int, price_per_1m: float) -> float:
    return tokens / 1_000_000 * price_per_1m


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize DeepSeek v4-flash cache hit/miss/output usage."
    )
    parser.add_argument(
        "usage_json",
        type=Path,
        help="Path to usage.json, or a run directory containing usage.json.",
    )
    args = parser.parse_args()

    usage_path = args.usage_json
    if usage_path.is_dir():
        usage_path = usage_path / "usage.json"

    data = json.loads(usage_path.read_text())

    cache_hit = as_int(data, "num_cache_hit_read_tokens")
    cache_miss = as_int(data, "num_cache_miss_read_tokens")
    cache_write = as_int(data, "num_cache_write_tokens")
    input_tokens = as_int(data, "num_input_tokens")
    output = as_int(data, "num_output_tokens")
    reasoning = as_int(data, "num_reasoning_tokens")
    total = as_int(data, "num_tokens")
    requests = as_int(data, "num_requests")

    hit_cost = cost(cache_hit, DEEPSEEK_V4_FLASH_PRICE_PER_1M["cache_hit_input"])
    miss_cost = cost(cache_miss, DEEPSEEK_V4_FLASH_PRICE_PER_1M["cache_miss_input"])
    output_cost = cost(output, DEEPSEEK_V4_FLASH_PRICE_PER_1M["output"])
    total_cost = hit_cost + miss_cost + output_cost

    print(f"usage_json: {usage_path}")
    print(f"requests: {requests}")
    print(f"total_tokens: {total}")
    print(f"input_tokens: {input_tokens}")
    print(f"cache_hit_read_tokens: {cache_hit}")
    print(f"cache_miss_read_tokens: {cache_miss}")
    print(f"cache_write_tokens: {cache_write}")
    print(f"output_tokens: {output}")
    print(f"reasoning_tokens: {reasoning}")
    print()
    print("deepseek_v4_flash_cost_usd:")
    print(f"  cache_hit_input: ${hit_cost:.6f}")
    print(f"  cache_miss_input: ${miss_cost:.6f}")
    print(f"  output: ${output_cost:.6f}")
    print(f"  total: ${total_cost:.6f}")
    if cache_hit + cache_miss != input_tokens:
        print()
        print(
            "warning: cache_hit_read_tokens + cache_miss_read_tokens does not "
            "equal input_tokens; this usage.json is missing complete DeepSeek "
            "cache accounting for input cost."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
