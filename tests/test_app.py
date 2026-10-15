"""Offline tests for the orchestrator (echonest_agent/agent.py) and the Gradio app (app.py), Stage 6.
A scripted fake LLM replaces the model: no API key, no quota. Logs go to a temporary folder.
Run from the repo root: python tests/test_app.py
"""
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import agent, graph, personas, tools  # noqa: E402
from echonest_agent.llm import LLMError, LLMResult, QuotaExhausted  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="echonest_app_"))
tools.LOGS_DIR = TMP
graph.TRACES_LOG = TMP / "traces.jsonl"


class ScriptedLLM:
    def __init__(self, *replies):
        self.replies, self.calls = list(replies), []

    def complete(self, messages, settings=None):
        self.calls.append({"messages": messages, "settings": settings})
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return LLMResult(text=reply, thinking=None, finish_reason="stop", usage={}, latency_s=0.0, provider="fake",
                         model="fake", settings_requested={}, settings_sent={}, settings_dropped={}, unverified=[])


def fake_agent(*replies):
    llm = ScriptedLLM(*replies)
    return graph.ReActAgent(llm=llm, verbose=False), llm


# ---------- history conversion (A3's tests, plus trace messages) --------------------------------------------
def test_gradio_to_api_handles_every_shape():
    history = [{"role": "user", "content": "Hi"},
               {"role": "assistant", "content": [{"type": "text", "text": "Hello!"}]},
               ["pair question", "pair answer"],
               {"role": "user", "content": {"path": "photo.jpg"}},          # a file: no text
               {"role": "system", "content": "ignored"}]
    assert agent.gradio_to_api(history) == [
        {"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "pair question"}, {"role": "assistant", "content": "pair answer"}]
    assert agent.gradio_to_api(None) == []


def test_trace_messages_are_not_sent_back_to_the_model():
    history = [{"role": "user", "content": "How long does a Legacy Edition take?"},
               {"role": "assistant", "content": "Observation: ...", "metadata": {"title": "🔧 get_package"}},
               {"role": "assistant", "content": "3 to 4 weeks.", "metadata": {}}]
    assert agent.gradio_to_api(history) == [{"role": "user", "content": "How long does a Legacy Edition take?"},
                                            {"role": "assistant", "content": "3 to 4 weeks."}]


# ---------- respond() --------------------------------------------------------------------------------------
def test_respond_runs_the_persona_with_the_history():
    a, llm = fake_agent('Action: get_package\nAction Input: {"name": "Legacy Edition"}',
                        "Final Answer: It takes 3 to 4 weeks, Karim.")
    history = [{"role": "user", "content": "Hi, I'm Karim."}, {"role": "assistant", "content": "Hi Karim!"}]
    reply = agent.respond("How long does a Legacy Edition take?", history, persona_id="nora", agent=a)
    assert reply.answer == "It takes 3 to 4 weeks, Karim." and reply.persona == "nora" and reply.error is None
    sent = llm.calls[0]["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"] and "You are Nora" in sent[0]["content"]
    assert llm.calls[0]["settings"].temperature == personas.NORA.settings["temperature"]
    assert reply.result.tool_calls == [("get_package", {"name": "Legacy Edition"})]


def test_respond_keeps_only_the_last_20_history_messages():
    a, llm = fake_agent("Final Answer: ok")
    history = [{"role": "user" if i % 2 == 0 else "assistant", "content": f"m{i}"} for i in range(30)]
    agent.respond("latest", history, agent=a)
    sent = llm.calls[0]["messages"]
    assert len(sent) == 1 + agent.MAX_HISTORY_MESSAGES + 1 and sent[1]["content"] == "m10"


def test_respond_handles_empty_messages_and_unknown_personas():
    a, llm = fake_agent("Final Answer: Hi!")
    assert agent.respond("   ", agent=a).answer == agent.EMPTY_MESSAGE_REPLY and llm.calls == []
    assert agent.respond({"text": "Hi", "files": []}, persona_id="nobody", agent=a).persona == "milo"


def test_llm_errors_become_friendly_replies():
    cases = [(QuotaExhausted("daily quota used up"), "quota"),
             (LLMError("gemini_native is temporarily unavailable for 'x'."), "busy"),
             (LLMError("The key in GEMINI_API_KEY was rejected"), "other"),
             (RuntimeError("boom"), "other")]
    for error, kind in cases:
        a, _ = fake_agent(error)
        reply = agent.respond("Hi", agent=a)
        assert reply.answer == agent.FRIENDLY_ERRORS[kind] and reply.error and reply.result is None, (kind, reply)


# ---------- app.py ----------------------------------------------------------------------------------------
def test_app_shows_the_trace_then_the_answer():
    import app
    a, _ = fake_agent("", 'Thought: I need the timeline.\nAction: get_package\nAction Input: {"name": "Legacy Edition"}',
                      "Thought: The Observation says 3 to 4 weeks.\nFinal Answer: It takes 3 to 4 weeks.")
    original, agent._agent = agent._agent, a
    try:
        out = app.chat("How long does a Legacy Edition take?", [], "milo")
    finally:
        agent._agent = original
    titles = [m.metadata.get("title") for m in out]
    assert titles == ["🛠 Format correction", "🔧 get_package", "🧠 Thought", None], titles
    assert out[-1].content == "It takes 3 to 4 weeks." and "Legacy Edition takes 3 to 4 weeks" in out[1].content
    as_history = [{"role": "user", "content": "How long does a Legacy Edition take?"}] + [asdict(m) for m in out]
    assert agent.gradio_to_api(as_history)[-1] == {"role": "assistant", "content": "It takes 3 to 4 weeks."}
    assert len(agent.gradio_to_api(as_history)) == 2                  # the trace never reaches the model


def test_app_offers_every_persona_and_has_no_key():
    import app
    assert [value for _, value in app.CHOICES] == list(personas.PERSONAS)
    source = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "demo.launch(" in source.split('if __name__ == "__main__":')[1]     # importing never launches
    for prefix in ["AIza", "sk-", "AQ."]:
        assert prefix not in source


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
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
