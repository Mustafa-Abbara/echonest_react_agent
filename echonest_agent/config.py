"""Which model the agent uses. With llm.py, the only module that knows LLM providers exist.

Choose the model in .env (or the environment, e.g. a Hugging Face secret):
    LLM_PROVIDER=gemini_native      # a key of "providers" in config/models.json
    LLM_MODEL=gemini-3.5-flash-lite # a key of "models" in config/models.json
Switching to another model or provider (a paid Gemini key, OpenAI, a local Ollama model) means editing those two
lines, adding the provider's key, and running scripts/probe_settings.py once for a new model. No code changes.
"""
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_FILE = ROOT / "config" / "models.json"
CAPABILITIES_DIR = ROOT / "config" / "capabilities"
DEFAULT_PROVIDER = "gemini_native"   # Stage 0: the only Gemini path that honours seed
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class ConfigError(RuntimeError):
    """A readable configuration problem (unknown model, missing key...)."""


def safe_name(text):
    """Model IDs such as 'qwen3:8b' contain characters Windows forbids in file names."""
    return re.sub(r'[<>:"/\\|?*]', "_", text)


def capability_path(provider, model):
    return CAPABILITIES_DIR / f"{provider}__{safe_name(model)}.json"


@dataclass(frozen=True)
class ModelProfile:
    provider: str
    model: str
    backend: str                 # openai_compat | google_genai | ollama_native
    base_url: str | None
    key_env: str | None          # None: no key needed (local Ollama)
    rpm: int | None              # requests per minute to pace at (None: no known limit)
    capabilities: dict | None    # measured by scripts/probe_settings.py; None = not probed yet

    def api_key(self):
        if not self.key_env:
            return None
        key = os.getenv(self.key_env)
        if not key:
            raise ConfigError(f"{self.key_env} is missing: add it to .env (see .env.example), "
                              f"or choose another LLM_PROVIDER.")
        return key

    def describe(self):
        probed = "probed" if self.capabilities else "NOT probed: run scripts/probe_settings.py"
        return f"{self.model} via {self.provider} ({self.backend}, {probed})"


def load_env():
    """Read .env from the working directory upwards; real environment variables win (python-dotenv default)."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        return
    load_dotenv(find_dotenv(usecwd=True))


def load_profile(provider=None, model=None, models_file=MODELS_FILE):
    """The active model: explicit arguments, else LLM_PROVIDER / LLM_MODEL, else the defaults above."""
    load_env()
    provider = provider or os.getenv("LLM_PROVIDER") or DEFAULT_PROVIDER
    model = model or os.getenv("LLM_MODEL") or DEFAULT_MODEL
    cfg = json.loads(Path(models_file).read_text(encoding="utf-8"))

    if provider not in cfg["providers"]:
        raise ConfigError(f"LLM_PROVIDER {provider!r} is not in config/models.json. "
                          f"Known providers: {', '.join(sorted(cfg['providers']))}.")
    entry = cfg["models"].get(model)
    if entry is None:
        raise ConfigError(f"LLM_MODEL {model!r} is not in config/models.json. Add it under \"models\", "
                          f"then run: python scripts/probe_settings.py --provider {provider} --model {model}")
    if provider not in entry.get("providers", [provider]):
        raise ConfigError(f"{model!r} is not served by provider {provider!r} "
                          f"(config/models.json lists: {', '.join(entry['providers'])}).")

    p = cfg["providers"][provider]
    path = capability_path(provider, model)
    capabilities = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return ModelProfile(provider=provider, model=model, backend=p["backend"], base_url=p.get("base_url"),
                        key_env=p.get("key_env"), rpm=entry.get("rpm"), capabilities=capabilities)
