"""Offline tests for the provider-neutral LLM layer (Stage 1): no API key, no network.

Covers settings validation, which settings are sent/dropped per model (from the real Stage 0 capability files),
how each backend builds its request, retries and readable errors, switching model through the environment only,
and the rule that only config.py and llm.py know about providers.
Run from the repo root: python tests/test_llm.py
"""
import json
import os
import re
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import config, llm  # noqa: E402
from echonest_agent.llm import LLM, LLMError, LLMSettings, QuotaExhausted  # noqa: E402


def caps(provider, model):
    return json.loads(config.capability_path(provider, model).read_text(encoding="utf-8"))


@contextmanager
def env(**values):
    """Temporarily set (or with None, remove) environment variables."""
    old = {k: os.environ.get(k) for k in values}
    try:
        for k, v in values.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        yield
    finally:
        for k, v in old.items():
            os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def profile(provider="fake", model="fake-model", backend="openai_compat", capabilities=None, rpm=None,
            key_env=None, base_url=None):
    return config.ModelProfile(provider=provider, model=model, backend=backend, base_url=base_url,
                               key_env=key_env, rpm=rpm, capabilities=capabilities)


# ----------------------------------------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------------------------------------
def test_settings_validate_and_serialise():
    s = LLMSettings(temperature=0.2, stop="Observation:", reasoning_effort="high")
    assert s.as_dict() == {"temperature": 0.2, "stop": ["Observation:"], "reasoning_effort": "high"}
    assert s.merged(max_tokens=300).as_dict()["max_tokens"] == 300 and s.max_tokens is None
    for bad in ({"temperature": 2.5}, {"top_p": 1.5}, {"top_k": 0}, {"presence_penalty": 3},
                {"reasoning_effort": "extreme"}):
        try:
            LLMSettings(**bad)
            raise AssertionError(f"{bad} should be refused")
        except ValueError:
            pass


# ----------------------------------------------------------------------------------------------------
# Which settings are sent, per model (real capability files from Stage 0)
# ----------------------------------------------------------------------------------------------------
EVERYTHING = LLMSettings(temperature=0.1, top_p=0.5, top_k=5, frequency_penalty=0.5, presence_penalty=0.5,
                         max_tokens=300, stop=["Observation:"], seed=7, reasoning_effort="medium").as_dict()


def test_plan_for_flash_lite_native_matches_stage0():
    native = llm.GoogleGenAIBackend.__new__(llm.GoogleGenAIBackend)
    send, dropped, unverified, _ = llm.plan_settings(EVERYTHING, caps("gemini_native", "gemini-3.5-flash-lite"),
                                                  native.can_express)
    assert set(send) == {"max_tokens", "stop", "seed", "reasoning_effort"}, send
    assert set(dropped) == {"temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty"}, dropped
    assert dropped["temperature"].startswith("ignored") and dropped["presence_penalty"].startswith("rejected")
    assert unverified == []


def test_plan_for_gemma_native_keeps_sampling_settings():
    native = llm.GoogleGenAIBackend.__new__(llm.GoogleGenAIBackend)
    send, dropped, _, _ = llm.plan_settings(EVERYTHING, caps("gemini_native", "gemma-4-26b-a4b-it"), native.can_express)
    assert {"temperature", "top_p", "seed"} <= set(send), send
    assert set(dropped) == {"top_k", "frequency_penalty", "presence_penalty"}, dropped


def test_plan_for_gemini_compat_drops_seed_and_top_k():
    compat = llm.OpenAICompatBackend.__new__(llm.OpenAICompatBackend)
    send, dropped, _, _ = llm.plan_settings(EVERYTHING, caps("gemini", "gemini-3.5-flash-lite"), compat.can_express)
    assert "seed" in dropped and "top_k" in dropped and "seed" not in send
    assert dropped["seed"] == 'rejected by this model: Invalid JSON payload received. Unknown name "seed": ' \
                              'Cannot find field.', dropped["seed"]


def test_unprobed_model_sends_what_it_can_and_flags_it():
    compat = llm.OpenAICompatBackend.__new__(llm.OpenAICompatBackend)
    send, dropped, unverified, _ = llm.plan_settings(EVERYTHING, None, compat.can_express)
    assert dropped == {"top_k": "this provider has no way to send it"}, dropped   # e.g. OpenAI: no top_k field
    assert set(unverified) == set(send) == set(EVERYTHING) - {"top_k"}


def test_unsupported_reasoning_level_maps_to_nearest_accepted():
    assert llm.nearest_level("low", ["minimal", "high"]) == "minimal"
    assert llm.nearest_level("medium", ["minimal", "high"]) == "high"
    assert llm.nearest_level("low", ["minimal", "medium"]) == "medium"        # tie → the deeper level
    gemma = {"settings": {"reasoning_effort": {"status": "honoured", "levels_accepted": ["minimal", "high"]}}}
    send, dropped, _, adjusted = llm.plan_settings({"reasoning_effort": "low"}, gemma, lambda n, e: True)
    assert send == {"reasoning_effort": "minimal"} and not dropped
    assert adjusted == {"reasoning_effort": "low → minimal (this model accepts minimal, high)"}, adjusted


# ----------------------------------------------------------------------------------------------------
# How each backend builds its request
# ----------------------------------------------------------------------------------------------------
def test_openai_compat_kwargs():
    compat = llm.OpenAICompatBackend.__new__(llm.OpenAICompatBackend)
    measured = {"settings": {"top_k": {"status": "untested", "send_as": "top_level"},
                             "max_tokens": {"status": "rejected", "alias_max_completion_tokens": "accepted"}}}
    kwargs = compat.build_kwargs({"temperature": 0.3, "top_k": 5, "max_tokens": 100}, measured)
    assert kwargs == {"temperature": 0.3, "extra_body": {"top_k": 5}, "max_completion_tokens": 100}, kwargs
    kwargs = compat.build_kwargs({"max_tokens": 100}, {"settings": {"max_tokens": {"status": "honoured"}}})
    assert kwargs == {"max_tokens": 100}


def test_google_genai_config():
    from google.genai import types
    native = llm.GoogleGenAIBackend.__new__(llm.GoogleGenAIBackend)
    native.types = types
    contents, cfg = native.build_config(
        [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Hi"},
         {"role": "assistant", "content": "Hello"}, {"role": "user", "content": "Price?"}],
        {"temperature": 0.0, "max_tokens": 50, "stop": ["Observation:"], "seed": 3, "reasoning_effort": "low"})
    assert cfg.system_instruction == "Be brief." and cfg.max_output_tokens == 50 and cfg.seed == 3
    assert cfg.stop_sequences == ["Observation:"] and cfg.thinking_config.thinking_level == types.ThinkingLevel.LOW
    assert [c.role for c in contents] == ["user", "model", "user"]


def test_ollama_native_body():
    backend = llm.OllamaNativeBackend.__new__(llm.OllamaNativeBackend)
    body = backend.build_body("qwen3:8b", [{"role": "user", "content": "hi"}],
                              {"top_k": 1, "max_tokens": 64, "presence_penalty": 1.0, "reasoning_effort": "minimal"})
    assert body["options"] == {"top_k": 1, "num_predict": 64, "presence_penalty": 1.0} and body["think"] is False


def test_fold_system_and_split_thinking():
    folded = llm.fold_system([{"role": "system", "content": "S"}, {"role": "user", "content": "U"}])
    assert folded == [{"role": "user", "content": "S\n\nU"}]
    assert llm.split_thinking("<thought>plan</thought>Answer") == ("plan", "Answer")
    assert llm.split_thinking("<think>\nhmm\n</think>\n\nThought: x") == ("hmm", "Thought: x")
    assert llm.split_thinking("Thought: no tags") == (None, "Thought: no tags")


# ----------------------------------------------------------------------------------------------------
# LLM.complete with a scripted backend: results, retries, readable errors
# ----------------------------------------------------------------------------------------------------
class Scripted:
    """A backend that replays a list of outcomes: a (text, thinking, finish, usage) tuple or an exception."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    def can_express(self, name, entry):
        return True

    def request(self, model, messages, send, capabilities):
        self.calls.append({"messages": messages, "send": send})
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def error_kind(self, e):
        return getattr(e, "kind", "other")


class Fail(Exception):
    def __init__(self, kind, text="boom"):
        super().__init__(text)
        self.kind = kind


def test_complete_records_settings_and_strips_inline_thinking():
    backend = Scripted(("<thought>check docs</thought>Final Answer: 3 to 4 weeks.", None, "stop", {"total_tokens": 9}))
    result = LLM(profile(capabilities=caps("gemini", "gemma-4-26b-a4b-it")), backend=backend).complete(
        [{"role": "user", "content": "How long?"}], LLMSettings(temperature=0.2, presence_penalty=0.5))
    assert result.text == "Final Answer: 3 to 4 weeks." and result.thinking == "check docs"
    assert result.settings_sent == {"temperature": 0.2} and "presence_penalty" in result.settings_dropped
    assert backend.calls[0]["send"] == {"temperature": 0.2}
    json.dumps(result.as_record())


def test_complete_folds_system_when_unsupported():
    backend = Scripted(("ok", None, "stop", {}))
    LLM(profile(capabilities={"settings": {}, "system_role": {"supported": False}}), backend=backend).complete(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}])
    assert backend.calls[0]["messages"] == [{"role": "user", "content": "S\n\nU"}]


def test_complete_retries_busy_then_succeeds():
    backend = Scripted(Fail("busy"), Fail("busy"), ("ok", None, "stop", {}))
    client = LLM(profile(), backend=backend, retry_wait=0)
    assert client.complete([{"role": "user", "content": "x"}]).text == "ok" and client.requests == 3


def test_empty_reply_is_sent_once_more():
    client = LLM(profile(), backend=Scripted(("", None, "stop", {}), ("ok", None, "stop", {})), retry_wait=0)
    result = client.complete([{"role": "user", "content": "x"}])
    assert result.text == "ok" and client.requests == 2 and "empty" in result.warnings[0]
    twice = LLM(profile(), backend=Scripted(("", None, "stop", {}), ("", None, "stop", {})), retry_wait=0)
    assert twice.complete([{"role": "user", "content": "x"}]).text == "" and twice.requests == 2
    cut = LLM(profile(), backend=Scripted(("", "thinking...", "length", {})), retry_wait=0)
    assert cut.complete([{"role": "user", "content": "x"}]).text == "" and cut.requests == 1   # length: no retry


def test_network_errors_are_retried_then_reported():
    ok = LLM(profile(), backend=Scripted(Fail("network"), ("ok", None, "stop", {})), retry_wait=0)
    assert ok.complete([{"role": "user", "content": "x"}]).text == "ok"
    try:
        LLM(profile(), backend=Scripted(*[Fail("network", "Server disconnected")] * 3), retry_wait=0).complete(
            [{"role": "user", "content": "x"}])
        raise AssertionError("persistent network errors must raise")
    except LLMError as e:
        assert "cannot reach" in str(e).lower() and "Server disconnected" in str(e), str(e)


def test_complete_errors_are_readable():
    cases = [(Fail("rate", "Please retry in 18h2m3s"), QuotaExhausted, "daily quota"),
             (Fail("auth", "API key not valid"), LLMError, "OPENAI_API_KEY"),
             (Fail("not_found", "no such model"), LLMError, "not found"),
             (Fail("unreachable", "connection refused"), LLMError, "Ollama")]
    for error, expected, phrase in cases:
        p = profile(key_env="OPENAI_API_KEY", backend="ollama_native" if phrase == "Ollama" else "openai_compat")
        try:
            LLM(p, backend=Scripted(error), retry_wait=0).complete([{"role": "user", "content": "x"}])
            raise AssertionError(f"{error.kind} should raise")
        except expected as e:
            assert phrase.lower() in str(e).lower(), str(e)


def test_empty_answer_at_length_warns():
    result = LLM(profile(), backend=Scripted(("<think>long thinking", None, "length", {}))).complete(
        [{"role": "user", "content": "x"}], LLMSettings(max_tokens=16))
    assert result.text == "" and result.warnings and "max_tokens" in result.warnings[0]


# ----------------------------------------------------------------------------------------------------
# Switching model through the environment only (the user's requirement)
# ----------------------------------------------------------------------------------------------------
def test_switching_model_needs_only_environment_changes():
    with env(LLM_PROVIDER="gemini_native", LLM_MODEL="gemma-4-26b-a4b-it"):
        p = config.load_profile()
        assert (p.provider, p.model, p.backend) == ("gemini_native", "gemma-4-26b-a4b-it", "google_genai")
        assert p.capabilities["settings"]["temperature"]["status"] == "honoured"
    with env(LLM_PROVIDER="ollama_native", LLM_MODEL="qwen3:8b"):
        p = config.load_profile()
        assert p.backend == "ollama_native" and p.api_key() is None and p.base_url == "http://localhost:11434"
    with env(LLM_PROVIDER="ollama", LLM_MODEL="qwen3:8b"):
        client = LLM(config.load_profile())        # builds the OpenAI SDK client; no request is sent
        assert str(client.backend.client.base_url).startswith("http://localhost:11434/v1")


def test_openai_profile_from_a_models_file_entry():
    models = json.loads(config.MODELS_FILE.read_text(encoding="utf-8"))
    models["models"]["gpt-test-mini"] = {"providers": ["openai"], "rpm": None}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "models.json"
        path.write_text(json.dumps(models), encoding="utf-8")
        with env(LLM_PROVIDER="openai", LLM_MODEL="gpt-test-mini", OPENAI_API_KEY=None):
            p = config.load_profile(models_file=path)
            assert p.base_url is None and p.key_env == "OPENAI_API_KEY" and p.capabilities is None
            try:
                p.api_key()
                raise AssertionError("a missing OpenAI key must be reported")
            except config.ConfigError as e:
                assert "OPENAI_API_KEY" in str(e)


def test_config_errors_are_readable():
    for kwargs, phrase in (({"provider": "nope"}, "Known providers"),
                           ({"provider": "gemini", "model": "no-such-model"}, "probe_settings.py"),
                           ({"provider": "ollama", "model": "gemini-3.5-flash-lite"}, "not served")):
        try:
            config.load_profile(**kwargs)
            raise AssertionError(kwargs)
        except config.ConfigError as e:
            assert phrase in str(e), str(e)


# ----------------------------------------------------------------------------------------------------
# Only config.py and llm.py may know about providers
# ----------------------------------------------------------------------------------------------------
PROVIDER_CODE = re.compile(r"^\s*(import|from)\s+(openai|google\.genai|google import genai|httpx)\b|"
                           r"\b(gemini-\d|gemma-\d|gpt-\d|qwen\d)", re.M)
ALLOWED = {"echonest_agent/config.py", "echonest_agent/llm.py",
           "scripts/probe_settings.py",                     # measures providers directly, by design
           # A3 code, replaced by the package in Stages 4-6 (Roadmap): remove from this list when it goes
           "app.py", "scripts/export_app.py", "scripts/prepare_space.py"}


def test_only_config_and_llm_know_providers():
    offenders = []
    for path in list(ROOT.glob("echonest_agent/**/*.py")) + list(ROOT.glob("scripts/*.py")) + [ROOT / "app.py"]:
        rel = path.relative_to(ROOT).as_posix()
        if rel not in ALLOWED and PROVIDER_CODE.search(path.read_text(encoding="utf-8")):
            offenders.append(rel)
    assert not offenders, f"provider-specific code outside config.py/llm.py: {offenders}"


if __name__ == "__main__":
    failed = 0
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print("PASS", name)
            except AssertionError as e:
                failed += 1
                print("FAIL", name, "-", e)
    raise SystemExit(failed)
