"""Stage 0: measure which LLM settings a provider/model really honours.

A setting the API *accepts* (HTTP 200) is not necessarily a setting the model *honours*. For each setting this
script sends a valid value (acceptance) and, where possible, runs an effect test whose result can be counted.
Each setting is then classified as one of:
  honoured      accepted, and the expected effect shows up
  ignored       accepted, but no measurable effect
  rejected      the API returns HTTP 400 for a valid value
  inconclusive  the control run did not vary enough to tell (rerun with more --repeats)
  untested      skipped (--quick mode, or the daily quota ran out)

Writes (never the API key):
  config/capabilities/<provider>__<model>.json   read later by the agent's LLM layer
  docs/probe/<provider>__<model>__<date>.jsonl    every request and reply
  docs/available_models.txt                       model IDs the key can see (--list-models)

Run from the repo root:
  python scripts/probe_settings.py --provider gemini --model gemini-3.5-flash-lite --dry-run
  python scripts/probe_settings.py --provider gemini --model gemini-3.5-flash-lite
  python scripts/probe_settings.py --provider gemini --model gemma-4-26b-a4b-it --quick
  python scripts/probe_settings.py --provider gemini --list-models
"""
import argparse
import json
import os
import re
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODELS_FILE = ROOT / "config" / "models.json"
CAPABILITIES_DIR = ROOT / "config" / "capabilities"
PROBE_LOG_DIR = ROOT / "docs" / "probe"
PROBE_VERSION = 1
DEFAULT_RPM = 10          # pacing when models.json has no rpm for the model

STATUSES = ("honoured", "ignored", "rejected", "inconclusive", "untested")
SETTINGS = ("temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty",
            "max_tokens", "stop", "seed", "reasoning_effort")

# ----------------------------------------------------------------------------------------------------
# Prompts. Each one makes a setting's effect countable.
# ----------------------------------------------------------------------------------------------------
OK_PROMPT = "Reply with the single word OK."
ENTROPY_PROMPT = ("Write a random sequence of 8 unrelated lowercase English words, separated by spaces. "
                  "Reply with the words only.")
ECHO_PROMPT = "Write the word echo exactly 50 times, separated by single spaces. Output nothing else."
COUNT200_PROMPT = "Count from 1 to 200, separated by spaces. Output only the numbers."
COUNT10_PROMPT = "Count from 1 to 10, separated by commas. Output only the numbers."
REACT_COPY_PROMPT = ("Copy the following four lines exactly, with nothing before or after them:\n"
                     "Thought: I should look it up.\nAction: search_business_docs\n"
                     "Observation: The Legacy Edition takes 3 to 4 weeks.\nFinal Answer: It takes 3 to 4 weeks.")
PUZZLE_PROMPT = ("A box holds 3 red, 5 blue and 2 green marbles. I remove every blue marble, then add twice as many "
                 "green marbles as there are red ones. How many marbles are in the box? Reply with the number only.")
PENALTY_VALUE = 1.9   # strong but valid everywhere: OpenAI allows [-2, 2], Gemini [-2, 2) (2.0 itself is a 400)
FRENCH_SYSTEM ="You always reply only in French, whatever language the user writes in."
FRENCH_USER = "Hello! Who are you, in one sentence?"

# ----------------------------------------------------------------------------------------------------
# Metrics (pure functions, unit-tested offline in tests/test_probe.py)
# ----------------------------------------------------------------------------------------------------
def normalize(text):
    """Lowercase, punctuation and spacing removed, so trivial differences don't count as distinct."""
    return re.sub(r"[^\w]+", " ", (text or "").lower()).strip()


def distinct(texts):
    """Number of different answers among the non-empty texts."""
    return len({normalize(t) for t in texts if normalize(t)})


def count_word(text, word):
    return len(re.findall(rf"\b{re.escape(word)}\b", (text or "").lower()))


def numbers_in(text):
    return [int(n) for n in re.findall(r"\d+", text or "")]


THOUGHT_RE = re.compile(r"^\s*<thought>(.*?)(?:</thought>|$)", re.S)


def split_thought(text):
    """Some models (Gemma 4) write their thinking inline: '<thought>...</thought>answer'.
    Returns (thought or None, answer). An unclosed <thought> (cut by max_tokens/stop) is all thought."""
    m = THOUGHT_RE.match(text or "")
    if not m:
        return None, text or ""
    return m.group(1), (text or "")[m.end():]


FRENCH_MARKERS =("je", "suis", "bonjour", "vous", "un", "une", "le", "la", "les", "et", "est", "votre", "assistant")


def looks_french(text):
    words = set(normalize(text).split())
    return len(words & set(FRENCH_MARKERS)) >= 3


def classify_collapse(control_distinct, test_distinct, n):
    """A restrictive setting (temperature 0, top_p 0.01, top_k 1) should collapse varied answers to ~1."""
    if control_distinct < n - 1:          # the unrestricted control was already repetitive: can't tell
        return "inconclusive"
    if test_distinct <= 2:
        return "honoured"
    if test_distinct >= control_distinct - 1:
        return "ignored"
    return "inconclusive"


def classify_penalty(control_counts, test_counts):
    """A strong penalty should break 'write echo 50 times' well below the control's count."""
    if not control_counts or not test_counts:
        return "inconclusive"
    control, test = statistics.mean(control_counts), statistics.mean(test_counts)
    if control < 30:
        return "inconclusive"
    return "honoured" if test < 0.6 * control else "ignored"


# ----------------------------------------------------------------------------------------------------
# Config and backend
# ----------------------------------------------------------------------------------------------------
class QuotaExhausted(Exception):
    pass


def load_config(provider, model):
    cfg = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
    if provider not in cfg["providers"]:
        raise SystemExit(f"Provider {provider!r} is not in {MODELS_FILE}. Known: {sorted(cfg['providers'])}")
    provider_cfg = cfg["providers"][provider]
    model_cfg = cfg["models"].get(model, {}) if model else {}
    if model and not model_cfg:
        print(f"⚠️  {model!r} is not in config/models.json; pacing at {DEFAULT_RPM} requests/minute.")
    return provider_cfg, model_cfg


def load_key(key_env):
    try:
        from dotenv import find_dotenv, load_dotenv
        load_dotenv(find_dotenv(usecwd=True))
    except ImportError:
        pass
    key = os.getenv(key_env)
    if not key:
        raise SystemExit(f"{key_env} is missing: add it to .env (see .env.example).")
    return key


def _retry_seconds(error):
    """Seconds until the API says to retry ('Please retry in 18h38m37s'), or 0."""
    m = re.search(r"retry in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", str(error))
    if not m or not any(m.groups()):
        return 0
    h, mins, secs = m.groups()
    return int(h or 0) * 3600 + int(mins or 0) * 60 + int(float(secs or 0))


class ProbeBackend:
    """Shared pacing, retries and logging. Subclasses implement _request() and _error_kind()."""

    # How top_k can be sent, and a matching unknown-field canary (None = this backend can't send unknown fields).
    top_k_shapes = {}
    default_send_as = "top_level"   # how settings travel unless a test says otherwise
    canary_shapes = {}

    def __init__(self, provider_cfg, model, rpm, log_path):
        self.model = model
        self.interval = 60 / (rpm or DEFAULT_RPM)
        self.log_path = log_path
        self.requests = 0
        self.saw_inline_thought = False
        self._last = 0.0

    def send(self, test, messages, **params):
        """One request. Returns a dict; a 4xx answer is a result (ok=False), not an exception."""
        for attempt in (1, 2, 3):
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            self.requests += 1
            started = time.monotonic()
            try:
                raw, finish_reason, usage = self._request(messages, params)
                split = [split_thought(t) for t in raw]
                if any(thought is not None for thought, _ in split):
                    self.saw_inline_thought = True
                result = {"ok": True, "status": 200, "texts": [answer for _, answer in split], "raw_texts": raw,
                          "finish_reason": finish_reason, "usage": usage,
                          "reasoning_tokens": _reasoning_tokens(usage)}
            except Exception as e:
                kind, code = self._error_kind(e)
                if kind == "bad_request":
                    result = {"ok": False, "status": code, "error": _short(e)}
                elif kind in ("rate", "busy"):
                    retry = _retry_seconds(e)
                    if kind == "rate" and retry > 120:
                        raise QuotaExhausted(f"Daily quota for {self.model!r} is used up; resets in about "
                                             f"{retry // 3600}h {retry % 3600 // 60}m.") from None
                    if attempt == 3:
                        raise SystemExit(f"Giving up after repeated HTTP {code}: {_short(e)}")
                    delay = max(retry, 15 * attempt)
                    print(f"   ⏳ HTTP {code} ({'server busy' if kind == 'busy' else 'rate limit'}), "
                          f"retrying in {delay}s")
                    time.sleep(delay)
                    continue
                elif kind == "not_found":   # e.g. listed by --list-models but "no longer available to new users"
                    raise SystemExit(f"Model {self.model!r} not found (HTTP 404): {_short(e)}") from None
                elif kind == "auth":
                    raise SystemExit(f"Key rejected (HTTP {code}): {_short(e)}") from None
                else:
                    raise
            result["latency_s"] = round(time.monotonic() - started, 2)
            self._log(test, params, result)
            return result

    def _log(self, test, params, result):
        record = {"time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "model": self.model,
                  "test": test, "params": params, **result}
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


class OpenAICompatProbe(ProbeBackend):
    """Chat Completions on OpenAI or any OpenAI-compatible endpoint (e.g. Gemini's /v1beta/openai/).

    Chat Completions has no top_k field and the openai SDK refuses unknown keyword arguments, so both top_k shapes
    go through the SDK's extra_body (merged into the JSON body):
      top_level          → {"top_k": 1} at the top of the request body (what vLLM/Ollama-style servers accept)
      extra_body.google  → {"extra_body": {"google": {"top_k": 1}}}, the nesting Google's Python examples use
    """
    top_k_shapes = {
        "top_level": lambda value: {"extra_body": {"top_k": value}},
        "extra_body.google": lambda value: {"extra_body": {"extra_body": {"google": {"top_k": value}}}},
    }
    canary_shapes = {   # a field no API knows: tells whether unknown fields are rejected or silently dropped
        "top_level": {"extra_body": {"zz_probe_canary": 1}},
        "extra_body.google": {"extra_body": {"extra_body": {"google": {"zz_probe_canary": 1}}}},
    }

    def __init__(self, provider_cfg, model, rpm, log_path):
        super().__init__(provider_cfg, model, rpm, log_path)
        import openai
        self.openai = openai
        self.client = openai.OpenAI(api_key=load_key(provider_cfg["key_env"]),
                                    base_url=provider_cfg.get("base_url"), max_retries=0)

    def list_models(self):
        return sorted(m.id for m in self.client.models.list())

    def _request(self, messages, params):
        resp = self.client.chat.completions.create(model=self.model, messages=messages, **params)
        usage = resp.usage.model_dump() if resp.usage else {}
        raw = [c.message.content or "" for c in resp.choices]
        return raw, (resp.choices[0].finish_reason if resp.choices else None), usage

    def _error_kind(self, e):
        o = self.openai
        code = getattr(e, "status_code", None)
        if isinstance(e, (o.BadRequestError, o.UnprocessableEntityError)):
            return "bad_request", code
        if isinstance(e, o.RateLimitError):
            return "rate", code
        if isinstance(e, o.InternalServerError):
            return "busy", code
        if isinstance(e, o.NotFoundError):
            return "not_found", code
        if isinstance(e, (o.AuthenticationError, o.PermissionDeniedError)):
            return "auth", code
        return "other", code


class GoogleGenAIProbe(ProbeBackend):
    """Gemini API through Google's native google-genai SDK (generate_content), which has fields that the
    OpenAI-compatible endpoint does not pass on: top_k, seed, frequency/presence penalty, candidate_count."""
    default_send_as = "native"      # fields of GenerateContentConfig
    top_k_shapes = {"native": lambda value: {"top_k": value}}
    canary_shapes = {"native": None}   # the SDK's typed config cannot carry unknown fields

    # Neutral setting name → GenerateContentConfig field
    FIELD = {"temperature": "temperature", "top_p": "top_p", "top_k": "top_k", "seed": "seed",
             "frequency_penalty": "frequency_penalty", "presence_penalty": "presence_penalty",
             "max_tokens": "max_output_tokens", "max_completion_tokens": "max_output_tokens",
             "stop": "stop_sequences", "n": "candidate_count"}
    FINISH = {"STOP": "stop", "MAX_TOKENS": "length"}

    def __init__(self, provider_cfg, model, rpm, log_path):
        super().__init__(provider_cfg, model, rpm, log_path)
        try:
            from google import genai
            from google.genai import errors, types
        except ImportError:
            raise SystemExit("The native backend needs google-genai: pip install google-genai") from None
        self.types, self.errors = types, errors
        self.client = genai.Client(api_key=load_key(provider_cfg["key_env"]))

    def list_models(self):
        return sorted(m.name for m in self.client.models.list())

    def _request(self, messages, params):
        t = self.types
        unknown = set(params) - set(self.FIELD) - {"reasoning_effort"}
        if unknown:
            raise ValueError(f"native backend cannot send {sorted(unknown)}")
        config = {self.FIELD[k]: v for k, v in params.items() if k in self.FIELD}
        if "reasoning_effort" in params:
            config["thinking_config"] = t.ThinkingConfig(thinking_level=params["reasoning_effort"].upper())
        system = [m["content"] for m in messages if m["role"] == "system"]
        if system:
            config["system_instruction"] = "\n\n".join(system)
        contents = [t.Content(role="model" if m["role"] == "assistant" else "user",
                              parts=[t.Part(text=m["content"])])
                    for m in messages if m["role"] != "system"]
        resp = self.client.models.generate_content(model=self.model, contents=contents,
                                                   config=t.GenerateContentConfig(**config))
        raw = ["".join(p.text or "" for p in (c.content.parts if c.content and c.content.parts else [])
                       if not getattr(p, "thought", False))
               for c in (resp.candidates or [])] or [""]
        first = (resp.candidates or [None])[0]
        finish = getattr(getattr(first, "finish_reason", None), "name", None)
        u = resp.usage_metadata
        usage = {"prompt_tokens": u.prompt_token_count, "completion_tokens": u.candidates_token_count,
                 "total_tokens": u.total_token_count,
                 "completion_tokens_details": {"reasoning_tokens": u.thoughts_token_count or 0}} if u else {}
        return raw, self.FINISH.get(finish, (finish or "").lower() or None), usage

    def _error_kind(self, e):
        if isinstance(e, ValueError):        # a setting this backend cannot express: treat as rejected
            return "bad_request", None
        if not isinstance(e, self.errors.APIError):
            return "other", None
        code = e.code
        if code == 429:
            return "rate", code
        if code >= 500:
            return "busy", code
        if code == 404:
            return "not_found", code
        if code in (401, 403):
            return "auth", code
        return "bad_request", code


def _reasoning_tokens(usage):
    """Hidden reasoning ("thinking") tokens. OpenAI reports them in completion_tokens_details; Gemini's endpoint
    leaves that empty but counts them in total_tokens, so derive them as total - prompt - completion."""
    usage = usage or {}
    details = usage.get("completion_tokens_details") or {}
    if details.get("reasoning_tokens") is not None:
        return details["reasoning_tokens"]
    total, prompt, completion = (usage.get(k) for k in ("total_tokens", "prompt_tokens", "completion_tokens"))
    if None in (total, prompt, completion):
        return None
    return max(total - prompt - completion, 0)


def _short(error, limit=300):
    text = getattr(error, "message", None) or str(error)
    return re.sub(r"\s+", " ", text)[:limit]


def make_backend(provider_cfg, model, rpm, log_path):
    backends = {"openai_compat": OpenAICompatProbe, "google_genai": GoogleGenAIProbe}
    if provider_cfg["backend"] not in backends:
        raise SystemExit(f"Unknown backend {provider_cfg['backend']!r}; known: {sorted(backends)}")
    return backends[provider_cfg["backend"]](provider_cfg, model, rpm, log_path)


# ----------------------------------------------------------------------------------------------------
# The probe
# ----------------------------------------------------------------------------------------------------
def user(text):
    return [{"role": "user", "content": text}]


def entry(status, send_as="top_level", **evidence):
    assert status in STATUSES, status
    return {"status": status, "send_as": send_as, **evidence}


class Probe:
    def __init__(self, backend, repeats, quick):
        self.b = backend
        self.n = repeats
        self.quick = quick
        self.settings = {}
        self.extra = {}
        self.control = None

    # -- helpers ----------------------------------------------------------------------------------
    def sample(self, test, prompt, n, **params):
        """n calls; stops early if the first one is rejected. Returns (texts, first_result)."""
        texts, first = [], None
        for i in range(n):
            r = self.b.send(test, user(prompt), **params)
            first = first or r
            if not r["ok"]:
                return None, r
            texts.append(r["texts"][0])
        return texts, first

    def validated(self, test, **params):
        """Send an out-of-range value: HTTP 400 means the server reads and checks this field."""
        r = self.b.send(test, user(OK_PROMPT), **params)
        return (not r["ok"]), (r.get("error") if not r["ok"] else None)

    def control_texts(self):
        if self.control is None:
            self.control, _ = self.sample("control_entropy", ENTROPY_PROMPT, self.n)
            self.control = self.control or []
            print(f"   control: {distinct(self.control)}/{len(self.control)} distinct answers without settings")
        return self.control

    # -- sampling settings ------------------------------------------------------------------------
    def collapse_setting(self, name, value, invalid, send_as="top_level", build=None):
        build = build or (lambda v: {name: v})
        if self.quick:
            r = self.b.send(f"{name}_accept", user(OK_PROMPT), **build(value))
            return entry("untested" if r["ok"] else "rejected", send_as, accepted=r["ok"], error=r.get("error"))
        texts, first = self.sample(f"{name}={value}", ENTROPY_PROMPT, self.n, **build(value))
        if texts is None:
            return entry("rejected", send_as, accepted=False, error=first.get("error"))
        control = self.control_texts()
        is_validated, validation_error = self.validated(f"{name}_invalid={invalid}", **build(invalid))
        status = classify_collapse(distinct(control), distinct(texts), self.n)
        return entry(status, send_as, accepted=True, validated=is_validated, validation_error=validation_error,
                     evidence=f"{name}={value}: {distinct(texts)}/{len(texts)} distinct vs control "
                              f"{distinct(control)}/{len(control)}",
                     samples=texts)

    def probe_top_k(self):
        shapes = {}
        for shape, build in self.b.top_k_shapes.items():
            canary_params = self.b.canary_shapes.get(shape)
            canary = self.b.send(f"canary[{shape}]", user(OK_PROMPT), **canary_params) if canary_params else None
            result = self.collapse_setting("top_k", 1, -3, send_as=shape, build=build)
            result["unknown_fields_rejected"] = None if canary is None else not canary["ok"]
            shapes[shape] = result
        order = ["honoured", "inconclusive", "ignored", "untested", "rejected"]
        best_shape = min(shapes, key=lambda s: order.index(shapes[s]["status"]))
        best = dict(shapes[best_shape])
        best["shapes"] = {s: {k: v for k, v in r.items() if k != "samples"} for s, r in shapes.items()}
        return best

    def penalty(self, name):
        if self.quick:
            r = self.b.send(f"{name}_accept", user(OK_PROMPT), **{name: 1.0})
            return entry("untested" if r["ok"] else "rejected", accepted=r["ok"], error=r.get("error"))
        texts, first = self.sample(f"{name}={PENALTY_VALUE}", ECHO_PROMPT, 2, **{name: PENALTY_VALUE})
        if texts is None:
            return entry("rejected", accepted=False, error=first.get("error"))
        if "echo_control" not in self.extra:
            control, _ = self.sample("echo_control", ECHO_PROMPT, 2)
            self.extra["echo_control"] = [count_word(t, "echo") for t in control or []]
        is_validated, validation_error = self.validated(f"{name}_invalid=5.0", **{name: 5.0})
        counts = [count_word(t, "echo") for t in texts]
        return entry(classify_penalty(self.extra["echo_control"], counts), accepted=True, validated=is_validated,
                     validation_error=validation_error,
                     evidence=f"'echo' count with {name}={PENALTY_VALUE}: {counts} vs control {self.extra['echo_control']}")

    # -- other settings ---------------------------------------------------------------------------
    def max_tokens(self):
        r = self.b.send("max_tokens=16", user(COUNT200_PROMPT), max_tokens=16)
        if not r["ok"]:
            return entry("rejected", accepted=False, error=r.get("error"))
        text = r["texts"][0]
        cut = r["finish_reason"] == "length" or len(numbers_in(text)) < 40
        alias = self.b.send("max_completion_tokens=16", user(COUNT200_PROMPT), max_completion_tokens=16)
        return entry("honoured" if cut else "ignored", accepted=True,
                     evidence=f"finish_reason={r['finish_reason']}, {len(numbers_in(text))} numbers written, "
                              f"completion_tokens={r['usage'].get('completion_tokens')}, "
                              f"reasoning_tokens={r['reasoning_tokens']}, empty_text={not text.strip()}",
                     alias_max_completion_tokens="accepted" if alias["ok"] else f"rejected: {alias.get('error')}")

    def stop(self):
        # Judged on the answer. Gemma 4's inline thought may mention the stop string without being cut (measured:
        # the stop applies to the answer only); fall back to the raw text only when the answer is empty.
        def judged(result):
            answer = result["texts"][0]
            return answer if answer.strip() else result.get("raw_texts", result["texts"])[0]

        r = self.b.send("stop=['7']", user(COUNT10_PROMPT), stop=["7"])
        if not r["ok"]:
            return entry("rejected", accepted=False, error=r.get("error"))
        text = judged(r)
        digit_ok = 7 not in numbers_in(text) and 6 in numbers_in(text)
        react = self.b.send("stop=['Observation:']", user(REACT_COPY_PROMPT), stop=["Observation:"])
        react_text = judged(react) if react["ok"] else ""
        react_ok = react["ok"] and "Observation:" not in react_text and "Action:" in react_text
        cut_in_thought = any(x.get("raw_texts") and split_thought(x["raw_texts"][0])[0] is not None
                             and not x["texts"][0].strip() for x in (r, react) if x["ok"])
        return entry("honoured" if digit_ok and react_ok else "ignored", accepted=True,
                     evidence=f"stop=['7'] → {text.strip()[-120:]!r}; "
                              f"stop=['Observation:'] → {react_text.strip()[-160:]!r}",
                     react_stop_works=react_ok, cut_inside_thought=cut_in_thought)

    def seed(self):
        if self.quick:
            r = self.b.send("seed_accept", user(OK_PROMPT), seed=42)
            return entry("untested" if r["ok"] else "rejected", accepted=r["ok"], error=r.get("error"))
        pairs = {}
        for value in (42, 7):
            texts, first = self.sample(f"seed={value}", ENTROPY_PROMPT, 2, seed=value)
            if texts is None:
                return entry("rejected", accepted=False, error=first.get("error"))
            pairs[value] = texts
        same = all(normalize(t[0]) == normalize(t[1]) for t in pairs.values())
        return entry("honoured" if same else "ignored", accepted=True,
                     evidence="pairs " + "; ".join(f"seed {k}: {v}" for k, v in pairs.items()))

    def reasoning_effort(self):
        results = {}
        for level in (("high",) if self.quick else ("minimal", "high")):
            r = self.b.send(f"reasoning_effort={level}", user(PUZZLE_PROMPT), reasoning_effort=level)
            if not r["ok"]:
                return entry("rejected", accepted=False, error=r.get("error"))
            results[level] = r
        none = self.b.send("reasoning_effort=none", user(OK_PROMPT), reasoning_effort="none")
        none_note = "accepted" if none["ok"] else f"rejected: {none.get('error')}"
        if self.quick:
            return entry("untested", accepted=True, value_none=none_note)
        low, high = results["minimal"], results["high"]
        lt, ht = low["reasoning_tokens"], high["reasoning_tokens"]
        if lt is None and ht is None:
            lt, ht = low["usage"].get("completion_tokens"), high["usage"].get("completion_tokens")
        status = "honoured" if (ht or 0) > (lt or 0) + 50 else "ignored"
        if (ht or 0) == 0 and (lt or 0) == 0:
            status = "inconclusive"
        return entry(status, accepted=True, value_none=none_note,
                     evidence=f"reasoning tokens minimal={low['reasoning_tokens']} high={high['reasoning_tokens']}; "
                              f"latency minimal={low['latency_s']}s high={high['latency_s']}s; "
                              f"answers {low['texts'][0].strip()!r} / {high['texts'][0].strip()!r}")

    def system_role(self):
        r = self.b.send("system_role", [{"role": "system", "content": FRENCH_SYSTEM},
                                        {"role": "user", "content": FRENCH_USER}])
        if not r["ok"]:
            return {"supported": False, "error": r.get("error")}
        return {"supported": looks_french(r["texts"][0]), "evidence": r["texts"][0].strip()[:200]}

    def n_choices(self):
        r = self.b.send("n=2", user(OK_PROMPT), n=2)
        return {"supported": r["ok"] and len(r["texts"]) == 2, "error": r.get("error")}

    # -- run --------------------------------------------------------------------------------------
    def run(self, only=None):
        """Probe every setting, or only the names in `only` (settings and/or system_role, n_greater_than_1)."""
        steps = [
            ("temperature", lambda: self.collapse_setting("temperature", 0.0, 5.0)),
            ("top_p", lambda: self.collapse_setting("top_p", 0.01, 1.5)),
            ("top_k", self.probe_top_k),
            ("frequency_penalty", lambda: self.penalty("frequency_penalty")),
            ("presence_penalty", lambda: self.penalty("presence_penalty")),
            ("max_tokens", self.max_tokens),
            ("stop", self.stop),
            ("seed", self.seed),
            ("reasoning_effort", self.reasoning_effort),
        ]
        for name, step in steps:
            if only and name not in only:
                continue
            print(f"▶ {name}")
            try:
                self.settings[name] = step()
            except QuotaExhausted as e:
                print(f"🛑 {e}")
                break
            s = self.settings[name]
            if s["send_as"] == "top_level":
                s["send_as"] = getattr(self.b, "default_send_as", "top_level")
            print(f"   {s['status'].upper()}  {s.get('evidence') or s.get('error') or ''}")
        for name in (only or SETTINGS):
            if name in SETTINGS:
                self.settings.setdefault(name, entry("untested", note="not reached (quota)"))
        for key, step in (("system_role", self.system_role), ("n_greater_than_1", self.n_choices)):
            if only and key not in only:
                continue
            if all(s.get("note") != "not reached (quota)" for s in self.settings.values()):
                try:
                    self.extra[key] = step()
                    print(f"▶ {key}: {self.extra[key]}")
                except QuotaExhausted as e:
                    print(f"🛑 {e}")


def estimate_requests(repeats, quick):
    """Upper bound: a setting rejected on its first call skips the rest of its test."""
    if quick:
        # temperature 1, top_p 1, top_k 2 shapes × (canary + accept), 2 penalties, max_tokens + alias,
        # 2 stop tests, seed 1, reasoning high + none, system role, n=2
        return 1 + 1 + 4 + 2 + 2 + 2 + 1 + 2 + 2
    control = repeats
    temperature_top_p = 2 * (repeats + 1)          # samples + one out-of-range validation call each
    top_k = 2 * (1 + repeats + 1)                  # per shape: canary + samples + validation
    penalties = 2 * (2 + 1) + 2                    # per penalty: 2 samples + validation; shared control of 2
    rest = 2 + 2 + 4 + 3 + 2                       # max_tokens(+alias), stop×2, seed 2×2, reasoning×2+none, system+n
    return control + temperature_top_p + top_k + penalties + rest


def capability_document(provider, provider_cfg, model, probe, mode, repeats, requests):
    return {
        "_about": "Written by scripts/probe_settings.py. status: honoured | ignored | rejected | inconclusive | "
                  "untested. send_as: how the LLM layer must send the setting. Re-run the probe to refresh.",
        "provider": provider,
        "backend": provider_cfg["backend"],
        "model": model,
        "probed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "probe_version": PROBE_VERSION,
        "mode": mode,
        "repeats": repeats,
        "requests_used": requests,
        "settings": {k: {kk: vv for kk, vv in v.items() if kk != "samples"} for k, v in probe.settings.items()},
        "system_role": probe.extra.get("system_role", {"supported": None}),
        "n_greater_than_1": probe.extra.get("n_greater_than_1", {"supported": None}),
        "thought_inline": getattr(probe.b, "saw_inline_thought", False),
        "control_samples": probe.control,
    }


STATUS_ICON = {"honoured": "✅ honoured", "ignored": "⚪ ignored", "rejected": "❌ rejected",
               "inconclusive": "❓ inconclusive", "untested": "· untested"}


def support_table(docs):
    """Markdown table: one row per setting, one column per probed provider/model."""
    header = "| Setting | " + " | ".join(f"`{d['model']}` ({d['provider']})" for d in docs) + " |"
    lines = [header, "|---|" + "---|" * len(docs)]
    for name in SETTINGS:
        cells = [STATUS_ICON[d["settings"].get(name, {"status": "untested"})["status"]] for d in docs]
        lines.append(f"| `{name}` | " + " | ".join(cells) + " |")
    for key, label in (("system_role", "system role"), ("n_greater_than_1", "`n` > 1")):
        cells = []
        for d in docs:
            supported = d.get(key, {}).get("supported")
            cells.append({True: "✅ yes", False: "❌ no", None: "· untested"}[supported])
        lines.append(f"| {label} | " + " | ".join(cells) + " |")
    cells = [{True: "⚠️ yes (`<thought>…</thought>` in text)", False: "no"}.get(d.get("thought_inline"), "· untested")
             for d in docs]
    lines.append("| thinking written inline in the reply | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def write_report():
    docs = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(CAPABILITIES_DIR.glob("*.json"))]
    if not docs:
        raise SystemExit("No capability files yet: run the probe first.")
    parts = ["# Which LLM settings each model honours",
             "",
             "Generated by `python scripts/probe_settings.py --report` from `config/capabilities/*.json`. "
             "Do not edit by hand: re-probe a model, then regenerate.",
             "",
             "**honoured** = accepted and the effect was measured · **ignored** = accepted (HTTP 200) but no "
             "measurable effect · **rejected** = HTTP 400 for a valid value · raw requests and replies are in "
             "`docs/probe/`.",
             "",
             support_table(docs),
             "",
             "## Evidence per model"]
    for d in docs:
        parts += ["", f"### `{d['model']}` via `{d['provider']}` ({d['backend']}), probed {d['probed_at'][:10]}, "
                      f"{d['mode']} mode, {d.get('requests_used')} requests", ""]
        for name in SETTINGS:
            s = d["settings"].get(name, {})
            detail = s.get("evidence") or s.get("error") or s.get("note") or ""
            extras = [f"{k}: {s[k]}" for k in ("validated", "alias_max_completion_tokens", "value_none",
                                                 "react_stop_works") if k in s]
            if "shapes" in s:
                extras.append("shapes: " + ", ".join(f"{k}={v['status']}" for k, v in s["shapes"].items()))
            text = re.sub(r"\s+", " ", f"{detail} {'(' + '; '.join(map(str, extras)) + ')' if extras else ''}")
            parts.append(f"- **{name}**: {s.get('status', 'untested')}. {text.strip()[:400]}")
        parts.append(f"- **system role**: {d.get('system_role')}")
        parts.append(f"- **n > 1**: {d.get('n_greater_than_1')}")
    out = ROOT / "docs" / "settings_support.md"
    out.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Report for {len(docs)} model(s) → {out.relative_to(ROOT)}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true", help="regenerate docs/settings_support.md and stop")
    ap.add_argument("--provider")
    ap.add_argument("--model")
    ap.add_argument("--quick", action="store_true", help="acceptance only (~17 requests)")
    ap.add_argument("--repeats", type=int, default=5, help="samples per sampling test (default 5)")
    ap.add_argument("--dry-run", action="store_true", help="print the request estimate and stop")
    ap.add_argument("--list-models", action="store_true", help="save the model IDs this key can see")
    ap.add_argument("--only", help="comma-separated settings to re-probe; merged into the existing capability file")
    args = ap.parse_args(argv)
    if args.report:
        return write_report()
    if not args.provider:
        ap.error("--provider is required")
    only =[s.strip() for s in args.only.split(",")] if args.only else None
    unknown = set(only or []) - set(SETTINGS) - {"system_role", "n_greater_than_1"}
    if unknown:
        ap.error(f"unknown --only names: {sorted(unknown)}; choose from {list(SETTINGS)} + system_role, n_greater_than_1")

    provider_cfg, model_cfg = load_config(args.provider, args.model)
    if args.list_models:
        backend = make_backend(provider_cfg, None, None, Path(os.devnull))
        ids = backend.list_models()
        out = ROOT / "docs" / "available_models.txt"
        out.write_text(f"# {args.provider}, listed {datetime.now():%Y-%m-%d}\n" + "\n".join(ids) + "\n",
                       encoding="utf-8")
        print(f"{len(ids)} models → {out.relative_to(ROOT)}")
        return
    if not args.model:
        ap.error("--model is required unless --list-models is given")

    mode = "quick" if args.quick else "full"
    out = CAPABILITIES_DIR / f"{args.provider}__{args.model}.json"
    if only and not out.exists():
        ap.error(f"--only needs an existing {out.relative_to(ROOT)}: run the full probe first")
    estimate = f"at most {estimate_requests(args.repeats, args.quick)}" if not only else "a few"
    rpm = model_cfg.get("rpm")
    print(f"Probe {args.provider} / {args.model} ({mode}{', only ' + ','.join(only) if only else ''}): "
          f"{estimate} requests, paced at {rpm or DEFAULT_RPM}/min (daily limit: {model_cfg.get('rpd') or 'unknown'}).")
    if args.dry_run:
        return

    PROBE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    CAPABILITIES_DIR.mkdir(parents=True, exist_ok=True)
    log_path = PROBE_LOG_DIR / f"{args.provider}__{args.model}__{datetime.now():%Y-%m-%d}.jsonl"
    backend = make_backend(provider_cfg, args.model, rpm, log_path)
    probe = Probe(backend, args.repeats, args.quick)
    probe.run(only)

    doc = capability_document(args.provider, provider_cfg, args.model, probe, mode, args.repeats, backend.requests)
    if only:   # merge the re-probed entries into the existing file
        old = json.loads(out.read_text(encoding="utf-8"))
        old["settings"].update(doc["settings"])
        for key in ("system_role", "n_greater_than_1"):
            if key in only:
                old[key] = doc[key]
        old["thought_inline"] = bool(old.get("thought_inline")) or doc["thought_inline"]
        old["requests_used"] = old.get("requests_used", 0) + backend.requests
        old.setdefault("reprobed", []).append({"at": doc["probed_at"], "only": only})
        doc = old
    out.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"\n{backend.requests} requests used. Capabilities → {out.relative_to(ROOT)}; "
          f"raw log → {log_path.relative_to(ROOT)}")
    print("\nSummary:")
    for name, s in doc["settings"].items():
        print(f"  {name:<18} {s['status']:<13} via {s['send_as']}")
    print(f"  {'system_role':<18} {doc['system_role'].get('supported')}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
