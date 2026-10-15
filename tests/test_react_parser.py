"""Offline tests for the ReAct text protocol (Stage 3): the parser that detects actions and final answers, and the
system prompt that tells the model the format and the tools. No API key, no LLM calls.
Run from the repo root: python tests/test_react_parser.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))
from echonest_agent import prompts, tools  # noqa: E402
from echonest_agent.react_parser import parse_react  # noqa: E402
from react_fixtures import FIXTURES  # noqa: E402

TOOL_ARGS = tools.tool_arguments()


def check_fixture(fx):
    step = parse_react(fx["raw"], tools=fx.get("tools", TOOL_ARGS))
    e = fx["expect"]
    problems = []
    for key in ("kind", "tool", "args", "answer"):
        if key in e and getattr(step, key) != e[key]:
            problems.append(f"{key}: expected {e[key]!r}, got {getattr(step, key)!r}")
    if "thought" in e and step.thought != e["thought"]:
        problems.append(f"thought: expected {e['thought']!r}, got {step.thought!r}")
    for key, attr in (("answer_contains", "answer"), ("thought_contains", "thought"), ("error_contains", "error")):
        if key in e and e[key] not in (getattr(step, attr) or ""):
            problems.append(f"{attr} should contain {e[key]!r}, got {getattr(step, attr)!r}")
    if "warning_contains" in e and not any(e["warning_contains"] in w for w in step.warnings):
        problems.append(f"warnings should mention {e['warning_contains']!r}, got {step.warnings}")
    if e.get("no_warnings") and step.warnings:
        problems.append(f"expected no warnings, got {step.warnings}")
    if step.kind == "invalid" and not step.error:
        problems.append("an invalid step must explain itself in .error")
    return problems


def test_fixtures():
    failures = {fx["id"]: p for fx in FIXTURES if (p := check_fixture(fx))}
    print(f"  {len(FIXTURES) - len(failures)}/{len(FIXTURES)} fixtures pass")
    assert len(FIXTURES) >= 25
    assert not failures, failures


def test_fixture_ids_are_unique():
    ids = [fx["id"] for fx in FIXTURES]
    assert len(ids) == len(set(ids)), [i for i in ids if ids.count(i) > 1]


def test_parser_never_raises():
    for raw in (None, "", "   ", "Action:", "Final Answer", "Thought:\n\n", "{}", "Action: x(", "Observation: hi",
                "Action Input: {{{", "\x00 weird ﻿", "Action: get_package\nAction Input: " + "{" * 500):
        step = parse_react(raw, tools=TOOL_ARGS)
        assert step.kind == "invalid", (raw, step)
        assert step.error


def test_plain_text_for_the_no_format_fallback():
    step = parse_react("Hello! I'm Milo.\nHow can I help?", tools=TOOL_ARGS)
    assert step.kind == "invalid" and step.plain_text == "Hello! I'm Milo.\nHow can I help?"


def test_without_a_tool_list_any_tool_name_is_accepted():
    step = parse_react('Action: anything_at_all\nAction Input: {"x": 1}')
    assert step.kind == "action" and step.tool == "anything_at_all" and step.args == {"x": 1}


# ----------------------------------------------------------------------------------------------------
# The system prompt (PDF 2.2: behaviour and tools in the system prompt)
# ----------------------------------------------------------------------------------------------------
def test_format_spec_variants():
    with_cot, without_cot = prompts.format_spec(True), prompts.format_spec(False)
    assert "Thought:" in with_cot and "Final Answer:" in with_cot and "Action Input:" in with_cot
    assert 'Do not write any "Thought:"' in without_cot and "\nThought: <" not in without_cot
    for spec in (with_cot, without_cot):
        assert "Never write an Observation yourself." in spec


def test_system_prompt_contains_persona_tools_and_instructions():
    prompt = prompts.build_system_prompt("You are Milo.", cot=True)
    order = [prompt.index(s) for s in ("# Persona", "You are Milo.", "# Tools", "# Instructions",
                                       "## Inputs you receive", "## Rules", "## Worked example", "## Output format")]
    assert order == sorted(order), order
    custom = prompts.build_system_prompt("You are Milo.", "1. Use tools for facts.")
    assert "1. Use tools for facts." in custom and "## Rules" not in custom   # a string replaces the block
    for name in tools.TOOLS:
        assert f"### {name}" in prompt, name
    only = prompts.build_system_prompt("P", "I", tool_names=["search_business_docs"])
    assert "### search_business_docs" in only and "### get_package" not in only


def test_observation_message():
    assert prompts.observation_message("NO_MATCH: x") == "Observation: NO_MATCH: x"


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
