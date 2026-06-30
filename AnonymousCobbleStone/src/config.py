from dataclasses import dataclass
from typing import Optional
import openai
import os
import dotenv

dotenv.load_dotenv()


def optional_env(key: str) -> Optional[str]:
    return os.getenv(key)


def required_one_of_env(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and value.strip() != "":
            return value
    raise Exception(
        f"One of these environment variables must be set: {', '.join(keys)}"
    )


def deepseek_api_base() -> str:
    raw = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com").rstrip("/")
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def required_env(key: str) -> str:
    value = os.getenv(key)
    if value is None:
        raise Exception(f"Environment variable {key} is not set")
    return value


DIR_CONTAINING_FILE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@dataclass
class GlobalConfig:
    OPENAI_ORG: Optional[str] = optional_env("OPENAI_ORG")
    OPENAI_SECRET: Optional[str] = optional_env("OPENAI_SECRET")
    DEEPSEEK_API_KEY: Optional[str] = optional_env("DEEPSEEK_API_KEY")
    DEEPSEEK_API_BASE: str = deepseek_api_base()

    TOGETHER_API_KEY: Optional[str] = optional_env("TOGETHER_API_KEY")
    TOGETHER_BASE_URL: str = "https://api.together.xyz/v1"

    CLAUDE_API_KEY: Optional[str] = optional_env("CLAUDE_API_KEY")

    OCTO_API_KEY: Optional[str] = optional_env("OCTO_API_KEY")

    ROOT_DIR = DIR_CONTAINING_FILE

    PROJECTS_ROOT: str = required_env("PROJECTS_ROOT")

    LOG_DIR: str = os.getenv("LOG_DIR", DIR_CONTAINING_FILE + "/results_and_logs")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "WARNING")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs")
    LOG_LEVELS_FILE: str = os.getenv("LOG_LEVELS_FILE", "log_levels.yaml")

    MAX_OBSERVATION_TOKENS: int = int(os.getenv("MAX_OBSERVATION_TOKENS", "128000"))
    MAX_CHAT_COMPLETION_TOKENS: int = int(
        os.getenv("MAX_CHAT_COMPLETION_TOKENS", "300000")
    )
    LLM_REQUEST_TIMEOUT_SEC: int = int(os.getenv("LLM_REQUEST_TIMEOUT_SEC", "600"))
    LLM_MAX_RETRIES: int = int(os.getenv("LLM_MAX_RETRIES", "50"))
    DEEPSEEK_REASONING_EFFORT: str = os.getenv("DEEPSEEK_REASONING_EFFORT", "max")

    GOAL_DECOMPOSITION_EXAMPLE_WALL_TIMEOUT_SEC: Optional[float] = (
        float(v)
        if (v := os.getenv("GOAL_DECOMPOSITION_EXAMPLE_WALL_TIMEOUT_SEC", "5400"))
        not in (
            None,
            "",
        )
        and float(v) > 0
        else None
    )


CONFIG = GlobalConfig()

LLM_API_KEY = required_one_of_env("DEEPSEEK_API_KEY", "OPENAI_SECRET")
USE_DEEPSEEK = bool(CONFIG.DEEPSEEK_API_KEY)

DEFAULT_CHAT_MODEL = "deepseek-v4-flash" if USE_DEEPSEEK else "gpt-4"

if USE_DEEPSEEK:
    openai.api_base = CONFIG.DEEPSEEK_API_BASE
    openai.organization = ""
    openai.api_key = CONFIG.DEEPSEEK_API_KEY
elif CONFIG.OPENAI_ORG:
    openai.organization = CONFIG.OPENAI_ORG
    openai.api_key = LLM_API_KEY
else:
    openai.api_key = LLM_API_KEY

os.makedirs(CONFIG.LOG_DIR, exist_ok=True)
