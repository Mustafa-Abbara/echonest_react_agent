"""Offline tests for the personas and the instructions block (Stage 5; PDF 2.3 and 2.4). No API key, no LLM calls.
Run from the repo root: python tests/test_personas.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from echonest_agent import graph, personas, prompts, tools  # noqa: E402
from echonest_agent.llm import LLMResult, LLMSettings  # noqa: E402
from echonest_agent.react_parser import parse_react  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="echonest_personas_"))
tools.LOGS_DIR = TMP
graph.TRACES_LOG = TMP / "traces.jsonl"
CAPABILITIES = ROOT / "config" / "capabilities"

# Words that belong to the instructions (tools, format, rules), never to a persona.
RULE_WORDS = ["tool", "action", "observation", "record_", "search_business_docs", "get_package", "final answer",
              "json", "always call", "never state", "look it up", "look up"]
# Words that belong to a persona (length, tone), never to the shared instructions.
STYLE_WORDS = ["concise", "brief", "short", "keep answers", "under about", "friendly", "warm", "enthusiastic",
               "tone", "emoji", "exclamation"]


# ---------- personas (PDF 2.3) -------------------------------------------------------------------------------
def test_three_personas_with_different_tasks():
    assert len(personas.PERSONAS) >= 2 and set(personas.PERSONAS) == {"milo", "nora", "sami"}
    assert len({p.task_focus for p in personas.PERSONAS.values()}) == len(personas.PERSONAS)
    assert len({p.name for p in personas.PERSONAS.values()}) == len(personas.PERSONAS)


def test_every_persona_has_all_traits_settings_and_rationales():
    for p in personas.PERSONAS.values():
        assert set(p.traits) == set(personas.TRAITS), (p.id, set(p.traits))
        assert all(len(v.split()) >= 5 for v in p.traits.values()), p.id
        settings = p.llm_settings()                       # raises on an out-of-range value
        assert settings.stop is None and settings.seed is None, p.id   # set by the graph / the experiments
        for name in ("temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "max_tokens",
                     "reasoning_effort"):
            assert name in p.settings, (p.id, name)
        assert set(p.rationale) == set(p.settings), (p.id, set(p.settings) ^ set(p.rationale))
        for name, line in p.rationale.items():
            assert "\n" not in line and line.startswith(f"{p.settings[name]}:"), (p.id, name, line)


def test_settings_match_the_personas():
    m, n, s = personas.MILO.settings, personas.NORA.settings, personas.SAMI.settings
    assert n["temperature"] < m["temperature"] < s["temperature"]          # precise < conversational < creative
    assert n["top_k"] < m["top_k"] < s["top_k"] and n["top_p"] < m["top_p"] < s["top_p"]
    assert n["presence_penalty"] <= m["presence_penalty"] < s["presence_penalty"]
    assert s["max_tokens"] > m["max_tokens"]                                 # the Story Planner writes long plans
    for p in personas.PERSONAS.values():
        assert p.settings["frequency_penalty"] < 2.0 and p.settings["presence_penalty"] < 2.0   # Gemini: 2.0 = 400


def test_prompt_block_shows_name_focus_and_traits():
    for p in personas.PERSONAS.values():
        block = p.prompt_block
        assert block.startswith(f"You are {p.name}, {p.role} at EchoNest"), block[:80]
        assert p.task_focus in block
        for key in personas.TRAITS:
            assert p.traits[key] in block and f"- {key.replace('_', ' ').capitalize()}:" in block


def test_persona_blocks_contain_no_rules():
    for p in personas.PERSONAS.values():
        lower = p.prompt_block.lower()
        found = [w for w in RULE_WORDS if w in lower]
        assert not found, (p.id, found)


def test_card_shows_intended_vs_effective_settings():
    def llm_for(capability_file, expressible=True):
        caps = json.loads((CAPABILITIES / capability_file).read_text(encoding="utf-8"))
        return SimpleNamespace(profile=SimpleNamespace(capabilities=caps),
                               backend=SimpleNamespace(can_express=lambda name, entry: expressible))
    flash = dict((r[0], r) for r in personas.NORA.card(llm_for("gemini_native__gemini-3.5-flash-lite.json")))
    assert flash["temperature"][2] == "—" and "ignored" in flash["temperature"][3]
    assert flash["frequency_penalty"][2] == "—" and "rejected" in flash["frequency_penalty"][3]
    assert flash["max_tokens"][2] == 700 and flash["reasoning_effort"][2] == "medium"
    qwen = dict((r[0], r) for r in personas.SAMI.card(llm_for("ollama_native__qwen3_4b-instruct.json")))
    for name in ("temperature", "top_p", "top_k", "frequency_penalty", "presence_penalty", "max_tokens"):
        assert qwen[name][2] == personas.SAMI.settings[name], (name, qwen[name])


# ---------- the instructions block (PDF 2.4) -----------------------------------------------------------------
def test_instructions_have_inputs_output_rules_and_example():
    for cot in (True, False):
        block = prompts.build_instructions(cot)
        headings = [block.index(h) for h in ("## Inputs you receive", "## Rules", "## Worked example",
                                             "## Output format")]
        assert headings == sorted(headings), headings
        assert "The Final Answer is the only text the customer sees." in block


def test_each_rule_has_one_purpose_and_one_sentence():
    block = prompts.build_instructions()
    numbered = re.findall(r"^(\d+)\. (.+)$", block.split("## Rules\n")[1].split("\n\n")[0], re.M)
    assert [int(n) for n, _ in numbered] == list(range(1, len(prompts.RULES) + 1))
    for rule in prompts.RULES:
        assert rule.endswith(".") and not re.search(r"[.!?] [A-Z]", rule), rule   # one sentence
        assert len(rule.split()) <= 40, rule


def test_instructions_contain_no_style_rules():
    lower = prompts.build_instructions().lower()
    found = [w for w in STYLE_WORDS if w in lower]
    assert not found, found


def test_worked_example_parses_and_uses_the_real_observation():
    for cot in (True, False):
        replies = prompts.example_replies(cot)
        block = prompts.worked_example(cot)
        for reply in replies:
            assert reply in block
        first, last = (parse_react(r, tools=tools.tool_arguments()) for r in (replies[0], replies[-1]))
        assert first.kind == "action" and first.tool == "get_package" and first.args == {"name": "Event Story"}
        assert last.kind == "final" and "150 photos" in last.answer
        assert (first.thought is not None) == cot and (last.thought is not None) == cot
        real = tools.safe_execute("get_package", {"name": "Event Story"})
        assert prompts.observation_message(real) in block and "up to 150 photos" in real


def test_shot_variants_for_the_experiment():
    zero, one, few = (prompts.build_instructions(examples=n) for n in (0, 1, 3))
    assert "## Worked example" not in zero and one == prompts.build_instructions()      # the shipped block = 1 shot
    assert "## Worked examples" in few and few.count("Customer: ") == 3
    for block in (zero, one, few):
        assert block.rstrip().endswith(prompts.format_spec().rstrip())                 # the format stays last
    for example in prompts.EXTRA_EXAMPLES:
        for cot in (True, False):
            for reply in prompts.example_replies(cot, example):
                assert reply in prompts.build_instructions(cot, examples=3)
                assert parse_react(reply, tools=tools.tool_arguments()).kind in ("action", "final"), reply
    assert not (TMP / "leads.jsonl").exists() and not (TMP / "feedback.jsonl").exists()   # building saved nothing


def test_in_message_placement():
    calls = []

    class FakeLLM:
        def complete(self, messages, settings=None):
            calls.append(messages)
            return LLMResult(text="Final Answer: Hi!", thinking=None, finish_reason="stop", usage={}, latency_s=0.0,
                             provider="fake", model="fake", settings_requested={}, settings_sent={},
                             settings_dropped={}, unverified=[])

    agent = graph.ReActAgent(llm=FakeLLM(), verbose=False)
    agent.run("Hi!", persona=personas.MILO, placement="in_message")
    system, user = calls[0][0]["content"], calls[0][-1]["content"]
    assert system.startswith("# Persona") and "# Instructions" not in system and "# Tools" not in system
    assert user.startswith("# Tools") and "## Rules" in user and user.endswith("# Customer message\n\nHi!")
    try:
        agent.run("Hi!", placement="sideways")
        raise AssertionError("an unknown placement must be refused")
    except ValueError:
        pass


def test_worked_example_is_not_a_live_test_case():
    import live_graph_cases
    assert prompts.WORKED_EXAMPLE["customer"] not in {c["message"] for c in live_graph_cases.CASES}


# ---------- the graph uses the persona ----------------------------------------------------------------------
def test_graph_uses_the_persona_prompt_and_settings():
    calls = []

    class FakeLLM:
        def complete(self, messages, settings=None):
            calls.append((messages, settings))
            return LLMResult(text="Final Answer: $149.", thinking=None, finish_reason="stop", usage={},
                             latency_s=0.0, provider="fake", model="fake", settings_requested={}, settings_sent={},
                             settings_dropped={}, unverified=[])

    agent = graph.ReActAgent(llm=FakeLLM(), verbose=False)
    result = agent.run("How much is an Event Story?", persona=personas.NORA)
    system, settings = calls[0][0][0]["content"], calls[0][1]
    assert "You are Nora, the Package Specialist" in system and "## Worked example" in system
    assert settings.temperature == 0.1 and settings.reasoning_effort == "medium" and settings.stop == ("Observation:",)
    agent.run("Hi", persona=personas.NORA, settings=LLMSettings(max_tokens=50))       # explicit settings win
    assert calls[1][1].max_tokens == 50 and calls[1][1].temperature is None
    assert result.persona == "nora"
    assert json.loads(graph.TRACES_LOG.read_text(encoding="utf-8").splitlines()[-1])["persona"] == "nora"


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
