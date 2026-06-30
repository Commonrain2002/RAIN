"""Named OpenCode model presets (provider/model + default variant)."""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_DEEPSEEK_MODEL = "deepseek/deepseek-v4-flash"
_DEFAULT_VARIANT = "max"


@dataclass(frozen=True)
class OpenCodeModelPreset:
    model: str
    variant: str


_PRESETS: dict[str, OpenCodeModelPreset] = {
    "deepseek-v4-flash": OpenCodeModelPreset(
        model=_DEFAULT_DEEPSEEK_MODEL,
        variant=_DEFAULT_VARIANT,
    ),
    "openai-gpt-5.4": OpenCodeModelPreset(
        model="openai/gpt-5.4",
        variant="xhigh",
    ),
    "codex-gpt-5.4": OpenCodeModelPreset(
        model="openai/gpt-5.4",
        variant="xhigh",
    ),
    "gpt-5.4": OpenCodeModelPreset(
        model="openai/gpt-5.4",
        variant="xhigh",
    ),
    "openrouter-gpt-5.4": OpenCodeModelPreset(
        model="openrouter/openai/gpt-5.4",
        variant="xhigh",
    ),
    "qwen3.5-flash": OpenCodeModelPreset(
        model="alibaba-cn/qwen3.5-flash",
        variant="xhigh",
    ),
}


def list_opencode_preset_keys() -> list[str]:
    return sorted(_PRESETS.keys())


def resolve_opencode_model_settings(
    preset_key: str | None,
    model_arg: str,
    variant_arg: str,
) -> tuple[str, str, str | None]:
    """Apply preset, then explicit ``--opencode-model`` / ``--opencode-variant`` overrides."""
    if preset_key is None:
        return model_arg, variant_arg, None

    normalized = preset_key.strip()
    if normalized not in _PRESETS:
        known = ", ".join(list_opencode_preset_keys())
        raise ValueError(f"Unknown opencode preset {preset_key!r}; known: {known}")

    entry = _PRESETS[normalized]
    resolved_model = entry.model
    resolved_variant = entry.variant

    if model_arg != _DEFAULT_DEEPSEEK_MODEL:
        resolved_model = model_arg
    if variant_arg != _DEFAULT_VARIANT:
        resolved_variant = variant_arg

    return resolved_model, resolved_variant, normalized
