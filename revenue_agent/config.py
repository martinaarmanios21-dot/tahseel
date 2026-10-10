"""Runtime configuration. Every knob is overridable via environment variables or `.env`."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if value[:1] in ('"', "'"):
            value = value[1:].split(value[0], 1)[0]
        else:
            value = value.split(" #", 1)[0].split("\t#", 1)[0].strip()  # inline comment
        os.environ.setdefault(key.strip(), value)


_load_dotenv(ROOT / ".env")

# All providers below have a free tier and speak the OpenAI-compatible chat API.
PROVIDERS: dict[str, dict] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "key_env": "GEMINI_API_KEY",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-3.5-flash,gemini-flash-latest",  # tried in order; the alias never disappears
        "rpm": 8,
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "model_env": "OPENROUTER_MODEL",
        "default_model": "meta-llama/llama-3.3-70b-instruct:free",
        "rpm": 15,
    },
    "nvidia": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "key_env": "NVIDIA_API_KEY",
        "model_env": "NVIDIA_MODEL",
        "default_model": "openai/gpt-oss-20b",
        "rpm": 30,
    },
}


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    value = _env(name)
    if not value:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    engine: str  # offline | api | hermes
    providers: tuple[str, ...]
    data_dir: Path
    db_path: Path
    # cost + rate limits
    run_llm_call_cap: int
    daily_llm_call_cap: int
    run_token_cap: int
    llm_timeout_s: float
    llm_max_retries: int
    # business policy
    approval_threshold_cents: int
    max_touches: int
    max_installments: int
    # learning
    explore_rate: float
    train_size: int
    eval_size: int
    eval_seeds: tuple[int, ...]
    promotion_margin: float
    # interactive agent (per user request / per chat session)
    max_model_calls_per_request: int
    max_agent_steps: int
    max_tool_calls_per_request: int
    max_input_tokens: int
    max_output_tokens: int
    max_request_seconds: float
    max_user_message_chars: int
    max_history_messages: int
    max_session_tokens: int
    llm_price_in_per_1k: float      # USD per 1k input tokens; 0 = unknown (cost is then not estimated)
    llm_price_out_per_1k: float
    max_cost_per_request_usd: float  # 0 = no cost ceiling (call/token ceilings still apply)
    max_cost_per_session_usd: float
    # hermes
    hermes_bin: str
    hermes_profile: str
    hermes_model: str
    hermes_provider: str
    hermes_timeout_s: int
    hermes_skill_sync: bool
    hermes_home: Path

    def provider_key(self, name: str) -> str:
        spec = PROVIDERS.get(name)
        return _env(spec["key_env"]) if spec else ""

    def provider_model(self, name: str) -> str:
        return self.provider_models(name)[0]

    def provider_models(self, name: str) -> list[str]:
        """One or more models per provider (comma-separated), tried in order before the next provider."""
        spec = PROVIDERS[name]
        raw = _env(spec["model_env"]) or spec["default_model"]
        return [m.strip() for m in raw.split(",") if m.strip()]

    @property
    def hermes_profile_home(self) -> Path:
        """Where the isolated Hermes profile keeps its config + skills."""
        return self.hermes_home / "profiles" / self.hermes_profile if self.hermes_profile else self.hermes_home

    def available_providers(self) -> list[str]:
        return [p for p in self.providers if p in PROVIDERS and self.provider_key(p)]


def get_settings() -> Settings:
    providers = tuple(
        p.strip().lower() for p in _env("LLM_PROVIDERS", "gemini,openrouter,nvidia").split(",") if p.strip()
    )
    engine = _env("ENGINE", "auto").lower()
    if engine == "auto":
        has_key = any(_env(PROVIDERS[p]["key_env"]) for p in providers if p in PROVIDERS)
        engine = "api" if has_key else "offline"
    data_dir = Path(_env("DATA_DIR", str(ROOT / "data")))
    seeds = tuple(int(s) for s in _env("EVAL_SEEDS", "101").split(",") if s.strip().isdigit()) or (101,)
    return Settings(
        engine=engine,
        providers=providers,
        data_dir=data_dir,
        db_path=Path(_env("DB_PATH", str(data_dir / "revenue_agent.db"))),
        run_llm_call_cap=_int("RUN_LLM_CALL_CAP", 40),
        daily_llm_call_cap=_int("DAILY_LLM_CALL_CAP", 300),
        run_token_cap=_int("RUN_TOKEN_CAP", 600_000),
        llm_timeout_s=_float("LLM_TIMEOUT_S", 90.0),
        llm_max_retries=_int("LLM_MAX_RETRIES", 3),
        approval_threshold_cents=_int("APPROVAL_THRESHOLD_CENTS", 10_000_000),  # 100,000 EGP
        max_touches=_int("MAX_TOUCHES", 3),
        max_installments=_int("MAX_INSTALLMENTS", 3),
        explore_rate=_float("EXPLORE_RATE", 0.35),
        train_size=_int("TRAIN_SIZE", 60),
        eval_size=_int("EVAL_SIZE", 40),
        eval_seeds=seeds,
        promotion_margin=_float("PROMOTION_MARGIN", 0.05),
        max_model_calls_per_request=_int("MAX_MODEL_CALLS_PER_REQUEST", 6),
        max_agent_steps=_int("MAX_AGENT_STEPS", 5),
        max_tool_calls_per_request=_int("MAX_TOOL_CALLS_PER_REQUEST", 10),
        max_input_tokens=_int("MAX_INPUT_TOKENS", 24_000),
        max_output_tokens=_int("MAX_OUTPUT_TOKENS", 2_000),
        max_request_seconds=_float("MAX_REQUEST_SECONDS", 75.0),
        max_user_message_chars=_int("MAX_USER_MESSAGE_CHARS", 2_000),
        max_history_messages=_int("MAX_HISTORY_MESSAGES", 6),
        max_session_tokens=_int("MAX_SESSION_TOKENS", 200_000),
        llm_price_in_per_1k=_float("LLM_PRICE_IN_PER_1K", 0.0),
        llm_price_out_per_1k=_float("LLM_PRICE_OUT_PER_1K", 0.0),
        max_cost_per_request_usd=_float("MAX_COST_PER_REQUEST_USD", 0.0),
        max_cost_per_session_usd=_float("MAX_COST_PER_SESSION_USD", 0.0),
        hermes_bin=_env("HERMES_BIN", "hermes"),
        hermes_profile=_env("HERMES_PROFILE", "tahseel"),
        hermes_model=_env("HERMES_MODEL"),
        hermes_provider=_env("HERMES_PROVIDER"),
        hermes_timeout_s=_int("HERMES_TIMEOUT_S", 300),
        hermes_skill_sync=_bool("HERMES_SKILL_SYNC", True),
        hermes_home=Path(_env("HERMES_HOME", str(Path.home() / ".hermes"))),
    )
