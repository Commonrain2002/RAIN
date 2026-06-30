import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

OPENAI_API_KEY = os.environ.get(
    'OPENAI_API_KEY',
    os.environ.get('PALM_OPENAI_API_KEY', ''),
)
REPLICATE_API_TOKEN = os.environ.get('REPLICATE_API_TOKEN', '')

# Any OpenAI-compatible chat completion endpoint can be used.
MODEL = os.environ.get('PALM_MODEL', os.environ.get('OPENAI_MODEL', 'gpt-4o-mini'))
OPENAI_BASE_URL = os.environ.get(
    'OPENAI_BASE_URL',
    os.environ.get('PALM_OPENAI_BASE_URL', ''),
)

REASONING_EFFORT = os.environ.get('PALM_REASONING_EFFORT', 'max')

# SerAPI/coqc use the opam switch recorded in data/path.json.
opam_path = os.environ.get('OPAMROOT', str(Path.home() / '.opam'))

# PALM_PROJECTS_PATH should point to a directory containing <project>/ subdirectories.
projects_path = os.environ.get('PALM_PROJECTS_PATH', str(REPO_ROOT / 'coq_projects'))

# Eval batch runs override these per trial to avoid concurrent writes.
data_path = os.environ.get('PALM_DATA_PATH', str(REPO_ROOT / 'data'))
eval_path = os.environ.get('PALM_EVAL_PATH', str(REPO_ROOT / 'evaluation'))
proof_path = os.path.join(eval_path, 'proof')

_DEFAULT_LLM_MAX_TOKENS = 200_000


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, '').strip()
    if not raw:
        return default
    return int(raw)


llm_max_tokens = _int_env('PALM_MAX_TOKENS', _DEFAULT_LLM_MAX_TOKENS)
