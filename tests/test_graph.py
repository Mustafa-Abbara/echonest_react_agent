"""Offline tests for the LangGraph ReAct loop (Stage 4): a scripted fake LLM replays model replies, so every path
through the graph is checked without an API key or quota. Logs go to a temporary folder.
Run from the repo root: python tests/test_graph.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import graph, tools  # noqa: E402
from echonest_agent.llm import LLMResult, LLMSettings  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="echonest_graph_"))
tools.LOGS_DIR = TMP
graph.TRACES_LOG = TMP / "traces.jsonl"


class ScriptedLLM:
    """Replays replies in order and records what the graph sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, settings=None):
        self.calls.append({"messages": [dict(m) for m in messages], "settings": settings})
        text = self.replies.pop(0)
        return LLMResult(text=text, thinking=None, finish_reason="stop", usage={}, latency_s=0.0, provider="fake",
                         model="scripted", settings_requested=(settings or LLMSettings()).as_dict(),
                         settings_sent={}, settings_dropped={}, unverified=[])


def run(*replies, **kwargs):
    llm = ScriptedLLM(*replies)
    result = graph.ReActAgent(llm=llm, verbose=False).run(kwargs.pop("message", "How long does the Legacy Edition "
                                                                                "take?"), **kwargs)
    return result, llm


def nodes(result):
    return [t["node"] for t in result.trace]


# ----------------------------------------------------------------------------------------------------
def test_action_then_final_answer():
    result, llm = run('Thought: I need the timeline.\nAction: get_package\nAction Input: {"name": "Legacy Edition"}',
                      "Thought: The observation says 3 to 4 weeks.\nFinal Answer: It takes 3 to 4 weeks.")
    assert nodes(result) == ["reason", "act", "reason", "finalize"], nodes(result)
    assert result.answer == "It takes 3 to 4 weeks." and result.outcome == "final" and result.steps == 2
    assert result.tool_calls == [("get_package", {"name": "Legacy Edition"})]
    second = llm.calls[1]["messages"]       # the step + its observation went back as one assistant turn
    assert second[-2]["role"] == "assistant" and second[-2]["content"].startswith("Thought: I need the timeline.")
    assert '{"name": "Legacy Edition"}\nObservation: Legacy Edition\nPrice: $499' in second[-2]["content"]
    assert second[-1] == {"role": "user", "content": graph.prompts.CONTINUE_MESSAGE}


def test_two_tools_share_one_scratchpad_turn():
    result, llm = run('Action: get_package\nAction Input: {"name": "Legacy Edition"}',
                      'Action: get_package\nAction Input: {"name": "Memory Capsule"}',
                      "Final Answer: $499 and $79.")
    third = llm.calls[2]["messages"]
    assert [m["role"] for m in third] == ["system", "user", "assistant", "user"]
    pad = third[-2]["content"]
    assert pad.count("Observation:") == 2 and pad.index("Legacy Edition") < pad.index("Memory Capsule")
    assert result.outcome == "final" and result.steps == 3


def test_direct_final_answer_uses_no_tool():
    result, _ = run("Thought: A greeting needs no tool.\nFinal Answer: Hi! I'm Milo from EchoNest.", message="Hi!")
    assert nodes(result) == ["reason", "finalize"] and result.tool_calls == []


def test_stop_sequence_and_persona_settings_reach_the_llm():
    _, llm = run("Final Answer: ok", settings=LLMSettings(temperature=0.2, max_tokens=300))
    s = llm.calls[0]["settings"]
    assert s.stop == ("Observation:",) and s.temperature == 0.2 and s.max_tokens == 300


def test_invented_observation_is_not_sent_back():
    result, llm = run('Action: search_business_docs\nAction Input: {"query": "gift cards"}\n'
                      "Observation: We sell gift cards for $50.\nFinal Answer: Yes, $50.",
                      "Final Answer: I couldn't find gift cards in our documents.")
    sent = "\n".join(m["content"] for m in llm.calls[1]["messages"])
    assert "$50" not in sent, "the invented observation reached the model"
    assert "Observation: NO_MATCH" in sent and nodes(result) == ["reason", "act", "reason", "finalize"]


def test_bad_format_is_corrected_once():
    result, llm = run("Let me check that for you.", "Final Answer: Typical projects take 5 to 10 business days.")
    assert nodes(result) == ["reason", "recover", "reason", "finalize"] and result.format_errors == 1
    pad = llm.calls[1]["messages"][-2]["content"]
    assert pad.startswith("Let me check that for you.\nObservation: FORMAT ERROR:") and "Final Answer:" in pad
    assert result.outcome == "final"


def test_two_empty_replies_get_two_corrections():
    result, llm = run("", "", "Final Answer: It takes 3 to 4 weeks.")
    assert nodes(result) == ["reason", "recover", "reason", "recover", "reason", "finalize"]
    pad = llm.calls[1]["messages"][-2]["content"]
    assert pad.startswith("Observation: FORMAT ERROR: your reply was empty.") and "(empty reply)" not in pad
    assert result.outcome == "final" and result.format_errors == 2


def test_plain_prose_twice_becomes_the_answer():
    result, _ = run("Hello there!", "Hello! I'm Milo. How can I help?")
    assert nodes(result) == ["reason", "recover", "reason", "finalize"]
    assert result.outcome == "format_fallback" and result.answer == "Hello! I'm Milo. How can I help?"


def test_repeated_invalid_actions_give_up_and_log_the_question():
    invalid = 'Action: lookup_prices\nAction Input: {"q": 1}'
    result, llm = run(*[invalid] * (graph.MAX_FORMAT_ERRORS + 1))
    assert nodes(result).count("recover") == graph.MAX_FORMAT_ERRORS and len(llm.calls) == graph.MAX_FORMAT_ERRORS + 1
    assert nodes(result)[-1] == "give_up" and result.outcome == "gave_up" and result.answer == graph.GIVE_UP_REPLY
    logged = json.loads((TMP / "feedback.jsonl").read_text(encoding="utf-8").splitlines()[-1])
    assert logged["question"].endswith("How long does the Legacy Edition take?")


def test_endless_actions_stop_at_max_steps():
    action = 'Action: search_business_docs\nAction Input: {"query": "hours"}'
    result, llm = run(*[action] * 10, max_steps=3)
    assert len(llm.calls) == 3 and result.steps == 3 and result.outcome == "gave_up"
    assert nodes(result).count("act") == 2              # the 3rd action would leave no step for an answer


def test_unknown_tool_error_reaches_the_model_and_the_loop_continues():
    result, llm = run('Action: lookup_prices\nAction Input: {"q": 1}', "Final Answer: Here is what I found.")
    assert "unknown tool 'lookup_prices'" in llm.calls[1]["messages"][-2]["content"]
    assert result.outcome == "final"


def test_tool_error_observation_lets_the_model_recover():
    result, llm = run('Action: record_customer_interest\nAction Input: {"email": "sara-at-example", "name": "Sara"}',
                      "Final Answer: Could you check your email address? It doesn't look valid.")
    assert "not a valid email" in llm.calls[1]["messages"][-2]["content"] and result.outcome == "final"
    assert not (TMP / "leads.jsonl").exists() or "sara-at-example" not in (TMP / "leads.jsonl").read_text("utf-8")


def test_history_and_cot_off():
    history = [{"role": "user", "content": "Hi, I'm Karim."}, {"role": "assistant", "content": "Hi Karim!"}]
    result, llm = run('Action: get_package\nAction Input: {"name": "capsule"}', "Final Answer: $79, Karim.",
                      message="How much is a Memory Capsule?", history=history, cot=False)
    first = llm.calls[0]["messages"]
    assert [m["role"] for m in first] == ["system", "user", "assistant", "user"]
    assert 'Do not write any "Thought:"' in first[0]["content"]
    assert llm.calls[1]["messages"][-2]["content"].startswith("Action: get_package")   # no Thought line
    assert result.answer == "$79, Karim."


def test_trace_is_logged_and_records_llm_settings():
    result, _ = run("Final Answer: ok", message="trace me", settings=LLMSettings(temperature=0.5))
    last = json.loads(graph.TRACES_LOG.read_text(encoding="utf-8").splitlines()[-1])
    assert last["user"] == "trace me" and last["outcome"] == "final"
    assert last["trace"][0]["llm"]["settings_requested"]["temperature"] == 0.5


def test_no_prebuilt_agent_is_used():
    """PDF 1: no prebuilt executors. The loop is our graph; nothing from langgraph.prebuilt or LangChain agents."""
    import ast
    banned_names = {"create_react_agent", "ToolNode", "tools_condition", "AgentExecutor", "bind_tools"}
    banned_modules = re.compile(r"^(langgraph\.prebuilt|langchain\.agents|langchain_core\.agents)")
    for path in (ROOT / "echonest_agent").glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))          # code only: docstrings may name them
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not banned_modules.match(node.module), f"{path.name} imports {node.module}"
                assert not {a.name for a in node.names} & banned_names, f"{path.name} imports a prebuilt agent"
            if isinstance(node, ast.Import):
                assert not any(banned_modules.match(a.name) for a in node.names), f"{path.name} imports a prebuilt"
            name = getattr(node, "id", None) or getattr(node, "attr", None)
            assert name not in banned_names, f"{path.name} uses {name}"


def test_graph_shape():
    g = graph.ReActAgent(llm=ScriptedLLM(), verbose=False).graph.get_graph()
    assert {"reason", "act", "recover", "finalize", "give_up"} <= set(g.nodes)
    edges = {(e.source, e.target) for e in g.edges}
    for edge in (("__start__", "reason"), ("reason", "act"), ("act", "reason"), ("reason", "recover"),
                 ("recover", "reason"), ("reason", "finalize"), ("reason", "give_up"), ("finalize", "__end__")):
        assert edge in edges, edge


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
    print(f"\n(logs written to {TMP}, not to logs/)")
    raise SystemExit(failed)
