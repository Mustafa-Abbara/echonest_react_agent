"""Provider-neutral LLM calls. With config.py, the only module that knows LLM providers exist.

Everything else calls
    llm = get_llm()                                   # the model chosen in .env
    result = llm.complete(messages, LLMSettings(temperature=0.2, max_tokens=300))
with the same setting names for every provider. For each setting, the model's capability file (measured by
scripts/probe_settings.py, see docs/stage0_findings.md) decides whether it is sent:
    honoured                                → sent
    untested / inconclusive / not probed    → sent if this backend can express it, listed in `unverified`
    ignored                                 → not sent (measured: no effect on this model)
    rejected                                → not sent (the model answers HTTP 400)
Every LLMResult records what was requested, sent and dropped (with the reason), so the experiments in the
assignment (PDF 2.3: vary temperature, top-p, top-k, penalties, max tokens, model) report what really happened.
"""
import re
import threading
import time
from dataclasses import asdict, dataclass, field, fields, replace

from .config import ConfigError, ModelProfile, load_profile

REASONING_LEVELS = ("minimal", "low", "medium", "high")
RANGES = {"temperature": (0.0, 2.0), "top_p": (0.0, 1.0), "top_k": (1, 1000),
          "frequency_penalty": (-2.0, 2.0), "presence_penalty": (-2.0, 2.0), "max_tokens": (1, 200_000)}


class LLMError(RuntimeError):
    """A readable failure from the model provider (bad key, unknown model, server down...)."""


class QuotaExhausted(LLMError):
    """The daily quota is used up: retrying today cannot help."""


# ----------------------------------------------------------------------------------------------------
# Settings and results
# ----------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMSettings:
    """Generation settings, named the same for every provider. None = not set (the model's default)."""
    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    frequency_penalty: float | None = None
    presence_penalty: float | None = None
    max_tokens: int | None = None
    stop: tuple[str, ...] | None = None
    seed: int | None = None
    reasoning_effort: str | None = None     # minimal | low | medium | high (hidden "thinking")

    def __post_init__(self):
        for name, (low, high) in RANGES.items():
            value = getattr(self, name)
            if value is not None and not low <= value <= high:
                raise ValueError(f"{name}={value} is outside [{low}, {high}]")
        if self.reasoning_effort is not None and self.reasoning_effort not in REASONING_LEVELS:
            raise ValueError(f"reasoning_effort must be one of {REASONING_LEVELS}, not {self.reasoning_effort!r}")
        if isinstance(self.stop, (list, str)):
            object.__setattr__(self, "stop", (self.stop,) if isinstance(self.stop, str) else tuple(self.stop))

    def as_dict(self):
        """Only the settings that are set, with stop as a list (what APIs expect)."""
        out = {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}
        if "stop" in out:
            out["stop"] = list(out["stop"])
        return out

    def merged(self, **overrides):
        """A copy with some settings changed, e.g. persona settings + the ReAct stop sequence."""
        return replace(self, **overrides)


@dataclass
class LLMResult:
    text: str                       # the answer, with any inline thinking removed
    thinking: str | None            # inline or returned thinking text, if the model exposed it
    finish_reason: str | None       # "stop", "length", ...
    usage: dict
    latency_s: float
    provider: str
    model: str
    settings_requested: dict
    settings_sent: dict
    settings_dropped: dict          # setting -> why it was not sent
    unverified: list                # sent, but this model's support was never measured
    settings_adjusted: dict = field(default_factory=dict)   # sent with a different value, and why
    warnings: list = field(default_factory=list)

    def as_record(self):
        """JSON-serialisable form for experiment logs."""
        return asdict(self)


THOUGHT_RE = re.compile(r"^\s*<(thought|think)>(.*?)(?:</\1>|$)", re.S)


def split_thinking(text):
    """Gemma 4 ('<thought>...</thought>') and Qwen 3 ('<think>...</think>') may write their thinking before the
    answer. Returns (thinking or None, answer); an unclosed tag (cut by max_tokens/stop) is all thinking."""
    m = THOUGHT_RE.match(text or "")
    if not m:
        return None, text or ""
    return m.group(2).strip(), (text or "")[m.end():].lstrip()


def _api_message(error):
    """'Error code: 400 - [{'error': {'message': 'Penalty is not enabled...', ...' → 'Penalty is not enabled...'."""
    m = re.search(r"""['"]message['"]:\s*['"](.+?)['"],\s*['"]status""", error or "")
    return m.group(1) if m else (error or "HTTP 400")


def nearest_level(level, accepted):
    """The accepted reasoning level closest to the requested one (ties go to the deeper level)."""
    i = REASONING_LEVELS.index(level)
    return min(accepted, key=lambda a: (abs(REASONING_LEVELS.index(a) - i), -REASONING_LEVELS.index(a)))


def plan_settings(requested, capabilities, can_express):
    """Decide which requested settings to send. Returns (send, dropped, unverified, adjusted)."""
    measured = (capabilities or {}).get("settings", {})
    send, dropped, unverified, adjusted = {}, {}, [], {}
    for name, value in requested.items():
        entry = measured.get(name, {})
        status = entry.get("status", "untested")
        if name == "max_tokens" and status == "rejected" and entry.get("alias_max_completion_tokens") == "accepted":
            status = "honoured"                     # sent as max_completion_tokens (newer OpenAI models)
        if status == "rejected":
            dropped[name] = f"rejected by this model: {_api_message(entry.get('error'))}"[:200]
        elif status == "ignored":
            dropped[name] = "ignored by this model (measured: no effect)"
        elif not can_express(name, entry):
            dropped[name] = "this provider has no way to send it"
        else:
            levels = entry.get("levels_accepted") if name == "reasoning_effort" else None
            if levels and value not in levels:      # e.g. Gemma 4 natively takes only minimal and high
                send[name] = nearest_level(value, levels)
                adjusted[name] = f"{value} → {send[name]} (this model accepts {', '.join(levels)})"
            else:
                send[name] = value
            if status != "honoured":
                unverified.append(name)
    return send, dropped, unverified, adjusted


def fold_system(messages):
    """For models without a system role: put the system text in front of the first user message."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    rest = [dict(m) for m in messages if m["role"] != "system"]
    if system and rest and rest[0]["role"] == "user":
        rest[0]["content"] = f"{system}\n\n{rest[0]['content']}"
    elif system:
        rest.insert(0, {"role": "user", "content": system})
    return rest


# ----------------------------------------------------------------------------------------------------
# Backends: how one provider receives a request. Each returns (raw_text, thinking, finish_reason, usage).
# ----------------------------------------------------------------------------------------------------
class OpenAICompatBackend:
    """Chat Completions: OpenAI, Gemini's OpenAI-compatible endpoint, Ollama's /v1, and similar servers."""
    TOP_K_SHAPES = {   # Chat Completions has no top_k; these are the shapes the probe can measure
        "top_level": lambda v: {"top_k": v},
        "extra_body.google": lambda v: {"extra_body": {"google": {"top_k": v}}},
    }

    def __init__(self, profile):
        import openai
        self.openai = openai
        self.client = openai.OpenAI(api_key=profile.api_key() or "not-needed", base_url=profile.base_url,
                                    max_retries=0)

    def can_express(self, name, entry):
        if name == "top_k":                         # only through a shape the probe found
            return entry.get("send_as") in self.TOP_K_SHAPES
        return True

    def build_kwargs(self, send, capabilities):
        measured = (capabilities or {}).get("settings", {})
        kwargs, extra = {}, {}
        for name, value in send.items():
            if name == "top_k":
                extra.update(self.TOP_K_SHAPES[measured["top_k"]["send_as"]](value))
            elif name == "max_tokens" and measured.get("max_tokens", {}).get("status") == "rejected":
                kwargs["max_completion_tokens"] = value
            else:
                kwargs[name] = value
        if extra:
            kwargs["extra_body"] = extra
        return kwargs

    def request(self, model, messages, send, capabilities):
        resp = self.client.chat.completions.create(model=model, messages=messages,
                                                   **self.build_kwargs(send, capabilities))
        choice = resp.choices[0] if resp.choices else None
        text = (choice.message.content or "") if choice else ""
        thinking = getattr(choice.message, "reasoning_content", None) if choice else None   # some servers
        return text, thinking, choice.finish_reason if choice else None, (resp.usage.model_dump() if resp.usage else {})

    def error_kind(self, e):
        o = self.openai
        for kinds, kind in (((o.BadRequestError, o.UnprocessableEntityError), "bad_request"),
                            ((o.RateLimitError,), "rate"), ((o.InternalServerError,), "busy"),
                            ((o.NotFoundError,), "not_found"),
                            ((o.AuthenticationError, o.PermissionDeniedError), "auth"),
                            ((o.APIConnectionError,), "network")):
            if isinstance(e, kinds):
                return kind
        return "other"


class GoogleGenAIBackend:
    """Gemini API through Google's google-genai SDK (Gemini and Gemma). Stage 0: the only Gemini path that
    honours seed, and it returns Gemma's thinking separately instead of inline."""
    FIELD = {"temperature": "temperature", "top_p": "top_p", "top_k": "top_k", "seed": "seed",
             "frequency_penalty": "frequency_penalty", "presence_penalty": "presence_penalty",
             "max_tokens": "max_output_tokens", "stop": "stop_sequences"}
    FINISH = {"STOP": "stop", "MAX_TOKENS": "length"}

    def __init__(self, profile):
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError:
            raise ConfigError("LLM_PROVIDER uses google-genai: pip install -r requirements.txt") from None
        self.types, self.errors = types, errors
        # a timeout, or one stalled request hangs the agent (seen in the Stage 4 live run); it counts as a network
        # error, so complete() retries it
        self.client = genai.Client(api_key=profile.api_key(), http_options=types.HttpOptions(timeout=120_000))

    def can_express(self, name, entry):
        return name in self.FIELD or name == "reasoning_effort"

    def build_config(self, messages, send):
        t = self.types
        config = {self.FIELD[k]: v for k, v in send.items() if k in self.FIELD}
        if "reasoning_effort" in send:
            config["thinking_config"] = t.ThinkingConfig(thinking_level=send["reasoning_effort"].upper())
        system = [m["content"] for m in messages if m["role"] == "system"]
        if system:
            config["system_instruction"] = "\n\n".join(system)
        contents = [t.Content(role="model" if m["role"] == "assistant" else "user", parts=[t.Part(text=m["content"])])
                    for m in messages if m["role"] != "system"]
        return contents, t.GenerateContentConfig(**config)

    def request(self, model, messages, send, capabilities):
        contents, config = self.build_config(messages, send)
        resp = self.client.models.generate_content(model=model, contents=contents, config=config)
        cand = (resp.candidates or [None])[0]
        parts = cand.content.parts if cand and cand.content and cand.content.parts else []
        text = "".join(p.text or "" for p in parts if not getattr(p, "thought", False))
        thinking = "".join(p.text or "" for p in parts if getattr(p, "thought", False)) or None
        finish = getattr(getattr(cand, "finish_reason", None), "name", None)
        u = resp.usage_metadata
        usage = {"prompt_tokens": u.prompt_token_count, "completion_tokens": u.candidates_token_count,
                 "reasoning_tokens": u.thoughts_token_count or 0, "total_tokens": u.total_token_count} if u else {}
        return text, thinking, self.FINISH.get(finish, (finish or "").lower() or None), usage

    def error_kind(self, e):
        import httpx
        if isinstance(e, httpx.TransportError):     # dropped connection, timeout, DNS failure
            return "network"
        if not isinstance(e, self.errors.APIError):
            return "other"
        code = e.code
        if code == 429:
            return "rate"
        if code >= 500:
            return "busy"
        return {404: "not_found", 401: "auth", 403: "auth"}.get(code, "bad_request")


class OllamaNativeBackend:
    """A local model through Ollama's /api/chat. Stage 0b: the path that can carry top_k (in `options`)."""
    OPTION = {"temperature": "temperature", "top_p": "top_p", "top_k": "top_k", "seed": "seed",
              "frequency_penalty": "frequency_penalty", "presence_penalty": "presence_penalty",
              "max_tokens": "num_predict", "stop": "stop"}

    def __init__(self, profile):
        import httpx                                # installed with the openai SDK
        self.httpx = httpx
        self.base_url = (profile.base_url or "http://localhost:11434").rstrip("/")
        self.http = httpx.Client(timeout=300)

    def can_express(self, name, entry):
        return name in self.OPTION or name == "reasoning_effort"

    def build_body(self, model, messages, send):
        body = {"model": model, "messages": messages, "stream": False,
                "options": {self.OPTION[k]: v for k, v in send.items() if k in self.OPTION}}
        if "reasoning_effort" in send:              # Qwen 3 thinking is on/off: minimal = off
            body["think"] = send["reasoning_effort"] != "minimal"
        return body

    def request(self, model, messages, send, capabilities):
        r = self.http.post(f"{self.base_url}/api/chat", json=self.build_body(model, messages, send))
        if r.status_code >= 400:
            raise OllamaHTTPError(r.status_code, r.text)
        data = r.json()
        msg = data.get("message") or {}
        prompt, completion = data.get("prompt_eval_count"), data.get("eval_count")
        usage = {"prompt_tokens": prompt, "completion_tokens": completion,
                 "total_tokens": (prompt or 0) + (completion or 0)}
        return msg.get("content") or "", msg.get("thinking") or None, data.get("done_reason"), usage

    def error_kind(self, e):
        if isinstance(e, self.httpx.ConnectError):  # nothing listening: Ollama isn't running, retrying won't help
            return "unreachable"
        if isinstance(e, self.httpx.TransportError):
            return "network"
        if isinstance(e, OllamaHTTPError):
            return "not_found" if e.status_code == 404 else "busy" if e.status_code >= 500 else "bad_request"
        return "other"


class OllamaHTTPError(Exception):
    def __init__(self, status_code, text):
        super().__init__(f"HTTP {status_code}: {text}")
        self.status_code = status_code


BACKENDS = {"openai_compat": OpenAICompatBackend, "google_genai": GoogleGenAIBackend,
            "ollama_native": OllamaNativeBackend}


# ----------------------------------------------------------------------------------------------------
# The client the agent uses
# ----------------------------------------------------------------------------------------------------
_last_call = {}                 # (provider, model) -> monotonic time of the last request, for RPM pacing
_pacing_lock = threading.Lock()


def _retry_seconds(error):
    """Seconds until the provider says to retry ('Please retry in 18h38m37s'), or 0."""
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", str(error))
    if not m or not any(m.groups()):
        return 0
    h, mins, secs = m.groups()
    return int(h or 0) * 3600 + int(mins or 0) * 60 + int(float(secs or 0))


def _short(error, limit=300):
    return re.sub(r"\s+", " ", getattr(error, "message", None) or str(error))[:limit]


class LLM:
    def __init__(self, profile: ModelProfile, backend=None, retry_wait=15):
        self.profile = profile
        self.backend = backend or BACKENDS[profile.backend](profile)
        self.retry_wait = retry_wait
        self.requests = 0                           # requests sent by this client (retries included)

    def __repr__(self):
        return f"LLM({self.profile.describe()})"

    def _pace(self):
        if not self.profile.rpm:
            return
        key = (self.profile.provider, self.profile.model)
        with _pacing_lock:
            wait = 60 / self.profile.rpm - (time.monotonic() - _last_call.get(key, 0.0))
            if wait > 0:
                time.sleep(wait)
            _last_call[key] = time.monotonic()

    def complete(self, messages, settings=None):
        """Send one chat request; returns an LLMResult. Raises LLMError (or QuotaExhausted) with a readable
        message when the provider fails in a way retrying can't fix."""
        p = self.profile
        if isinstance(settings, dict):
            settings = LLMSettings(**settings)
        requested = (settings or LLMSettings()).as_dict()
        send, dropped, unverified, adjusted = plan_settings(requested, p.capabilities, self.backend.can_express)
        if (p.capabilities or {}).get("system_role", {}).get("supported") is False:
            messages = fold_system(messages)

        for attempt in (1, 2, 3):
            self._pace()
            self.requests += 1
            started = time.monotonic()
            try:
                raw, thinking, finish, usage = self.backend.request(p.model, messages, send, p.capabilities)
                break
            except Exception as e:   # classified below; anything unknown is re-raised unchanged
                kind = self.backend.error_kind(e)
                retry = _retry_seconds(e)
                if kind == "rate" and retry > 120:
                    raise QuotaExhausted(f"The daily quota for {p.model!r} is used up (HTTP 429); it resets in "
                                         f"about {retry // 3600}h {retry % 3600 // 60}m.") from None
                if kind in ("rate", "busy", "network") and attempt < (2 if kind == "rate" else 3):
                    time.sleep(max(retry, self.retry_wait * attempt))
                    continue
                if kind == "network":                   # still failing after the retries
                    kind = "unreachable"
                messages_by_kind = {
                    "rate": f"Rate limit reached for {p.model!r} (HTTP 429). Wait a minute and try again.",
                    "busy": f"{p.provider} is temporarily unavailable for {p.model!r}. Try again in a minute.",
                    "not_found": f"Model {p.model!r} was not found by {p.provider}: {_short(e)}",
                    "auth": f"The key in {p.key_env} was rejected by {p.provider}: {_short(e)}",
                    "unreachable": f"Cannot reach {p.provider} for {p.model!r}"
                                   + (" (is Ollama running?)" if p.backend == "ollama_native" or
                                      "localhost" in (p.base_url or "") else "") + f": {_short(e)}",
                    "bad_request": f"{p.provider} rejected the request for {p.model!r}: {_short(e)}",
                }
                if kind in messages_by_kind:
                    raise LLMError(messages_by_kind[kind]) from None
                raise

        inline, text = split_thinking(raw)
        result = LLMResult(text=text, thinking=thinking or inline, finish_reason=finish, usage=usage,
                           latency_s=round(time.monotonic() - started, 2), provider=p.provider, model=p.model,
                           settings_requested=requested, settings_sent=send, settings_dropped=dropped,
                           unverified=unverified, settings_adjusted=adjusted)
        if not text.strip() and finish == "length":
            result.warnings.append("max_tokens ran out before any answer (thinking can use it up): "
                                   "raise max_tokens or lower reasoning_effort")
        return result


def get_llm(provider=None, model=None):
    """The LLM chosen in .env (LLM_PROVIDER / LLM_MODEL), or the one named here."""
    return LLM(load_profile(provider, model))
