"""Offline tests for scripts/probe_settings.py (Stage 0): no API key, no LLM calls.

The metric functions are tested directly; the whole probe is run against two fake models, one that honours
every setting and one that behaves as Google documents for Gemini 3.x (sampling ignored, penalties rejected).
Run from the repo root: python tests/test_probe.py
"""
import itertools
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import probe_settings as ps  # noqa: E402

WORDS = "apple river candle orbit velvet lantern meadow pixel harbor quartz tundra ember".split()


# ----------------------------------------------------------------------------------------------------
# Metric functions
# ----------------------------------------------------------------------------------------------------
def test_distinct_ignores_case_punctuation_and_empty():
    assert ps.distinct(["Apple river.", "apple  river", "APPLE, RIVER!", "", None]) == 1
    assert ps.distinct(["a b", "b a"]) == 2


def test_count_word_counts_whole_words_only():
    assert ps.count_word("echo echo Echo echoes re-echo", "echo") == 4  # "re-echo" contains a whole-word echo
    assert ps.count_word("", "echo") == 0


def test_looks_french():
    assert ps.looks_french("Bonjour ! Je suis Milo, votre assistant.")
    assert not ps.looks_french("Hello! I am Milo, your assistant.")


def test_classify_collapse():
    assert ps.classify_collapse(5, 1, 5) == "honoured"
    assert ps.classify_collapse(5, 5, 5) == "ignored"
    assert ps.classify_collapse(5, 4, 5) == "ignored"
    assert ps.classify_collapse(2, 1, 5) == "inconclusive"   # control already repetitive
    assert ps.classify_collapse(5, 3, 5) == "inconclusive"


def test_classify_diversity():
    base = "the sea the sea is blue and the sea is deep"
    assert ps.classify_diversity(base, base, "the ocean glitters, vast and restless under a pale sky") == "honoured"
    assert ps.classify_diversity(base, base, base) == "ignored"
    assert ps.classify_diversity(base, base + " today", "a b c d") == "inconclusive"   # control not deterministic


def test_classify_penalty():
    assert ps.classify_penalty([50, 50], [12, 20]) == "honoured"
    assert ps.classify_penalty([50, 50], [49, 50]) == "ignored"
    assert ps.classify_penalty([10, 12], [3, 4]) == "inconclusive"
    assert ps.classify_penalty([], [3]) == "inconclusive"


def test_reasoning_tokens_from_details_or_derived():
    assert ps._reasoning_tokens({"completion_tokens_details": {"reasoning_tokens": 64}}) == 64          # OpenAI
    assert ps._reasoning_tokens({"total_tokens": 489, "prompt_tokens": 50, "completion_tokens": 2,
                                 "completion_tokens_details": None}) == 437                            # Gemini
    assert ps._reasoning_tokens({"completion_tokens": 2}) is None


def test_run_only_probes_the_named_settings():
    backend = FakeBackend(honours=True)
    probe = ps.Probe(backend, repeats=5, quick=False)
    probe.run(only=["presence_penalty", "system_role"])
    assert set(probe.settings) == {"presence_penalty"}, set(probe.settings)
    assert set(probe.extra) == {"echo_control", "system_role"}, set(probe.extra)
    assert backend.requests == 2 + 2 + 1 + 1   # samples, control, validation, system role


def test_split_thought():
    assert ps.split_thought("<thought>* Word 1: apple</thought>apple cloud") == ("* Word 1: apple", "apple cloud")
    assert ps.split_thought("  <thought>cut off by max_tokens") == ("cut off by max_tokens", "")
    assert ps.split_thought("plain answer") == (None, "plain answer")
    assert ps.split_thought("I had a <thought> mid-sentence") == (None, "I had a <thought> mid-sentence")
    assert ps.split_thought(None) == (None, "")
    assert ps.split_thought("<think>\nhmm\n</think>\n\nanswer") == ("\nhmm\n", "answer")   # Qwen 3 style
    assert ps.split_thought("<think>a</thought>b") == ("a</thought>b", "")                  # tags must match


def test_safe_name_and_keyless_providers():
    assert ps.safe_name("qwen3:8b") == "qwen3_8b"
    assert ps.safe_name("gemini-3.5-flash-lite") == "gemini-3.5-flash-lite"
    assert ps.load_key(None) == "not-needed"


def test_ollama_native_request_and_reply_mapping():
    backend = ps.OllamaNativeProbe.__new__(ps.OllamaNativeProbe)
    backend.model = "qwen3:8b"
    body = backend.build_body([{"role": "user", "content": "hi"}],
                              {"temperature": 0.0, "top_k": 1, "max_tokens": 16, "stop": ["7"], "seed": 42,
                               "presence_penalty": 1.9, "reasoning_effort": "minimal"})
    assert body["options"] == {"temperature": 0.0, "top_k": 1, "num_predict": 16, "stop": ["7"], "seed": 42,
                               "presence_penalty": 1.9}, body["options"]
    assert body["think"] is False and body["stream"] is False
    assert backend.build_body([], {"reasoning_effort": "high"})["think"] is True
    for bad in ({"extra_body": {"top_k": 1}}, {"n": 2}):
        try:
            backend.build_body([], bad)
            raise AssertionError(f"{bad} should be refused")
        except ValueError:
            pass
    texts, finish, usage = ps.OllamaNativeProbe.parse_reply(
        {"message": {"content": "1, 2", "thinking": "x" * 400}, "done_reason": "length",
         "prompt_eval_count": 10, "eval_count": 120})
    assert texts == ["1, 2"] and finish == "length"
    assert usage["total_tokens"] == 130 and ps._reasoning_tokens(usage) == 100


def test_retry_seconds():
    assert ps._retry_seconds("Please retry in 18h38m37s") == 18 * 3600 + 38 * 60 + 37
    assert ps._retry_seconds("Please retry in 12.5s") == 12
    assert ps._retry_seconds("no hint") == 0


# ----------------------------------------------------------------------------------------------------
# Whole probe against fake models
# ----------------------------------------------------------------------------------------------------
class FakeBackend:
    """Imitates OpenAICompatProbe.send(). honours=True: a model that obeys every setting.
    honours=False: Gemini-3.x-like (sampling ignored, penalties and top-level top_k rejected, no seed)."""
    top_k_shapes = ps.OpenAICompatProbe.top_k_shapes
    canary_shapes = ps.OpenAICompatProbe.canary_shapes

    def __init__(self, honours):
        self.honours = honours
        self.requests = 0
        self.counter = itertools.count()

    def send(self, test, messages, **params):
        self.requests += 1
        prompt = messages[-1]["content"]
        body = params.get("extra_body", {})               # top-level JSON fields the SDK doesn't know
        google = body.get("extra_body", {}).get("google", {})
        top_k = body.get("top_k", google.get("top_k"))

        if "zz_probe_canary" in body or "zz_probe_canary" in google:
            return self._error("Unknown name zz_probe_canary")
        if not self.honours and ("frequency_penalty" in params or "presence_penalty" in params):
            return self._error("Penalty is not enabled for this model")
        if not self.honours and "top_k" in body:
            return self._error("Unknown name top_k")
        if params.get("temperature", 1) > 2 or params.get("top_p", 1) > 1 or (top_k is not None and top_k < 1):
            return self._error("value out of range")
        if any(params.get(p, 0) > 2 for p in ("frequency_penalty", "presence_penalty")):
            return self._error("value out of range")

        greedy = self.honours and (params.get("temperature") == 0 or params.get("top_p", 1) < 0.1 or top_k == 1)
        if prompt == ps.ENTROPY_PROMPT:
            seed = params.get("seed") if self.honours else None
            i = 0 if greedy else (seed if seed is not None else next(self.counter))
            text = " ".join(WORDS[(i + j) % len(WORDS)] for j in range(8))
        elif prompt == ps.ECHO_PROMPT:
            text = " ".join(["echo"] * (10 if self.honours and params.get("frequency_penalty", params.get(
                "presence_penalty")) else 50))
        elif prompt == ps.COUNT200_PROMPT:
            limit = params.get("max_tokens") or params.get("max_completion_tokens")
            return self._ok(" ".join(map(str, range(1, 8 if limit else 201))), "length" if limit else "stop")
        elif prompt == ps.COUNT10_PROMPT:
            text = "1,2,3,4,5,6," if params.get("stop") == ["7"] else "1,2,3,4,5,6,7,8,9,10"
        elif prompt == ps.REACT_COPY_PROMPT:
            text = ps.REACT_COPY_PROMPT.split("\n", 1)[1]
            if params.get("stop") == ["Observation:"]:
                text = text.split("Observation:")[0]
        elif prompt == ps.PUZZLE_PROMPT:
            reasoning = {"minimal": 0, "high": 400}[params["reasoning_effort"]] if self.honours else 30
            return self._ok("7", "stop", reasoning)
        elif prompt == ps.FRENCH_USER:
            text = "Bonjour ! Je suis un assistant et je suis là pour vous aider."
        else:
            text = "OK"
        n = params.get("n", 1)
        if n > 1 and not self.honours:
            return self._error("n > 1 is not supported")
        return self._ok(text, "stop", n=n)

    def _ok(self, text, finish, reasoning=None, n=1):
        return {"ok": True, "status": 200, "texts": [text] * n, "finish_reason": finish,
                "usage": {"completion_tokens": 20}, "reasoning_tokens": reasoning, "latency_s": 0.1}

    @staticmethod
    def _error(message):
        return {"ok": False, "status": 400, "error": message}


def run_fake(honours, quick=False):
    backend = FakeBackend(honours)
    probe = ps.Probe(backend, repeats=5, quick=quick)
    probe.run()
    doc = ps.capability_document("fake", {"backend": "openai_compat"}, "fake-model", probe,
                                 "quick" if quick else "full", 5, backend.requests)
    return doc, backend.requests


def check_schema(doc):
    for key in ("provider", "backend", "model", "probed_at", "probe_version", "mode", "settings", "system_role"):
        assert key in doc, f"missing {key}"
    assert set(doc["settings"]) == set(ps.SETTINGS), sorted(doc["settings"])
    for name, s in doc["settings"].items():
        assert s["status"] in ps.STATUSES, (name, s["status"])
        assert s.get("send_as"), name
        if s["status"] == "rejected":
            assert s.get("error"), f"{name} is rejected but has no error message"
    json.dumps(doc)  # must be serialisable


def test_probe_classifies_a_model_that_honours_everything():
    doc, requests = run_fake(honours=True)
    check_schema(doc)
    statuses = {k: v["status"] for k, v in doc["settings"].items()}
    assert set(statuses.values()) == {"honoured"}, statuses
    assert doc["settings"]["temperature"]["validated"] is True
    assert doc["system_role"]["supported"] is True
    assert doc["n_greater_than_1"]["supported"] is True
    assert requests <= ps.estimate_requests(5, False), (requests, ps.estimate_requests(5, False))


def test_probe_classifies_a_gemini3_like_model():
    doc, requests = run_fake(honours=False)
    check_schema(doc)
    s = doc["settings"]
    assert s["temperature"]["status"] == "ignored"
    assert s["top_p"]["status"] == "ignored"
    assert s["top_k"]["status"] == "ignored" and s["top_k"]["send_as"] == "extra_body.google"
    assert s["top_k"]["shapes"]["top_level"]["status"] == "rejected"
    assert s["frequency_penalty"]["status"] == "rejected" and "Penalty" in s["frequency_penalty"]["error"]
    assert s["presence_penalty"]["status"] == "rejected"
    assert s["seed"]["status"] == "ignored"
    assert s["reasoning_effort"]["status"] == "ignored"
    assert s["max_tokens"]["status"] == "honoured" and s["stop"]["status"] == "honoured"
    assert doc["n_greater_than_1"]["supported"] is False
    assert requests <= ps.estimate_requests(5, False)


def test_quick_mode_stays_within_estimate_and_marks_untested():
    doc, requests = run_fake(honours=False, quick=True)
    check_schema(doc)
    assert requests <= ps.estimate_requests(5, True), requests
    assert doc["settings"]["temperature"]["status"] == "untested"
    assert doc["settings"]["frequency_penalty"]["status"] == "rejected"


def test_quota_stop_marks_the_rest_untested():
    class QuotaAfter(FakeBackend):
        def send(self, test, messages, **params):
            if self.requests >= 12:
                raise ps.QuotaExhausted("daily quota used up")
            return super().send(test, messages, **params)

    probe = ps.Probe(QuotaAfter(honours=True), repeats=5, quick=False)
    probe.run()
    statuses = {k: v["status"] for k, v in probe.settings.items()}
    assert statuses["temperature"] == "honoured"
    assert statuses["reasoning_effort"] == "untested", statuses


def test_native_backend_maps_settings_to_generate_content_config():
    """GoogleGenAIProbe with a fake client: checks the field mapping without any network call."""
    try:
        from google.genai import errors, types
    except ImportError:
        print("  (skipped: google-genai not installed)")
        return
    seen = {}

    class FakeModels:
        def generate_content(self, model, contents, config):
            seen.update(model=model, contents=contents, config=config)
            part = types.Part(text="bonjour")
            thought = types.Part(text="hidden", thought=True)
            cand = types.Candidate(content=types.Content(role="model", parts=[thought, part]),
                                   finish_reason=types.FinishReason.MAX_TOKENS)
            usage = types.GenerateContentResponseUsageMetadata(prompt_token_count=5, candidates_token_count=1,
                                                               thoughts_token_count=40, total_token_count=46)
            return types.GenerateContentResponse(candidates=[cand], usage_metadata=usage)

    backend = ps.GoogleGenAIProbe.__new__(ps.GoogleGenAIProbe)
    ps.ProbeBackend.__init__(backend, {}, "gemma-test", 600, Path("nul"))
    backend.types, backend.errors = types, errors
    backend.client = type("C", (), {"models": FakeModels()})()

    raw, finish, usage = backend._request(
        [{"role": "system", "content": "Speak French."}, {"role": "user", "content": "Hi"}],
        {"temperature": 0.0, "top_k": 1, "max_tokens": 16, "stop": ["7"], "seed": 42,
         "frequency_penalty": 1.9, "reasoning_effort": "minimal"})
    cfg = seen["config"]
    assert (cfg.temperature, cfg.top_k, cfg.max_output_tokens, cfg.stop_sequences, cfg.seed) == (0.0, 1, 16, ["7"], 42)
    assert cfg.frequency_penalty == 1.9 and cfg.system_instruction == "Speak French."
    assert cfg.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert [c.role for c in seen["contents"]] == ["user"]
    assert raw == ["bonjour"] and finish == "length"          # thought parts are excluded from the answer
    assert ps._reasoning_tokens(usage) == 40
    kind, _ = backend._error_kind(ValueError("cannot send"))
    assert kind == "bad_request"
    try:
        backend._request([{"role": "user", "content": "x"}], {"extra_body": {"top_k": 1}})
        raise AssertionError("an OpenAI-style extra_body must not be silently accepted by the native backend")
    except ValueError:
        pass


def test_saved_capability_files_are_valid():
    files = sorted((ROOT / "config" / "capabilities").glob("*.json"))
    for path in files:
        check_schema(json.loads(path.read_text(encoding="utf-8")))
    print(f"  checked {len(files)} capability file(s)")


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
