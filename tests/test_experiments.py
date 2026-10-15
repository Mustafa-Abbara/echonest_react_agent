"""Offline tests for the evaluation set, the metrics, the experiment runner and the summarizer (Stage 7).
A fake LLM that follows each case's required tools replaces the model: no API key, no quota.
Run from the repo root: python tests/test_experiments.py
"""
import json
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from echonest_agent import evaluation, graph, prompts, tools  # noqa: E402
from echonest_agent.llm import LLMResult, QuotaExhausted  # noqa: E402
import run_experiments as runner  # noqa: E402
import summarize_experiments as summary  # noqa: E402

TMP = Path(tempfile.mkdtemp(prefix="echonest_exp_"))
tools.LOGS_DIR = TMP
graph.TRACES_LOG = TMP / "traces.jsonl"

ARGS = {"search_business_docs": {"query": "photos"}, "get_package": {"name": "Memory Capsule"},
        "record_feedback": {"question": "Do you sell gift cards?"},
        "record_customer_interest": {"email": "sara@example.com", "name": "Sara"}}
CASES = [
    {"id": "T1", "category": "fact", "message": "How many photos?", "required": [["get_package", "search_business_docs"]],
     "must_include": ["\\b60\\b"], "final": "Up to 60 photos."},
    {"id": "T2", "category": "no_answer", "message": "Gift cards?", "required": [["search_business_docs"],
                                                                                ["record_feedback"]],
     "final": "The team will follow up."},
    {"id": "T3", "category": "greeting", "message": "Hi!", "no_tools": True, "final": "Hello!"},
]


class FollowerLLM:
    """Calls the first tool of each required group in order, then answers with the case's 'final' text."""

    def __init__(self, cases, fail_after=None):
        self.by_message = {c["message"]: c for c in cases}
        self.requests, self.fail_after = 0, fail_after
        self.profile = SimpleNamespace(provider="fake", model="follower")

    def complete(self, messages, settings=None):
        self.requests += 1
        if self.fail_after is not None and self.requests > self.fail_after:
            raise QuotaExhausted("daily quota used up")
        user = next(m["content"] for m in reversed(messages)
                    if m["role"] == "user" and m["content"] != prompts.CONTINUE_MESSAGE)
        case = self.by_message[user]
        done = messages[-2]["content"].count("Observation:") if messages[-1]["content"] == prompts.CONTINUE_MESSAGE else 0
        required = case.get("required", [])
        if done < len(required):
            tool = required[done][0]
            text = f"Thought: I need {tool}.\nAction: {tool}\nAction Input: {json.dumps(ARGS[tool])}"
        else:
            text = f"Thought: I can answer.\nFinal Answer: {case['final']}"
        return LLMResult(text=text, thinking=None, finish_reason="stop", usage={"total_tokens": 10}, latency_s=0.1,
                         provider="fake", model="follower", settings_requested={}, settings_sent={"max_tokens": 1},
                         settings_dropped={"temperature": "ignored"}, unverified=[])


PLAN = {"name": "unit", "configs": [{"id": "milo", "persona": "milo"},
                                    {"id": "nora-cold", "persona": "nora", "settings": {"temperature": 0.0}}]}


def turn(answer, calls=(), outcome="final", trace=None):
    trace = trace or [{"node": "act", "tool": t, "args": a, "observation": "OK"} for t, a in calls]
    return graph.TurnResult(answer=answer, outcome=outcome, steps=len(calls) + 1, format_errors=0, trace=trace)


# ---------- the frozen case file -----------------------------------------------------------------------------
def test_eval_cases_are_valid():
    cases = evaluation.load_cases("full")
    assert len(cases) >= 30 and len({c["id"] for c in cases}) == len(cases)
    assert len(evaluation.load_cases("core")) == 12
    known = set(tools.TOOLS)
    for c in cases:
        for group in c.get("required", []):
            assert group and set(group) <= known, (c["id"], group)
        assert set(c.get("allowed", [])) | set(c.get("forbidden", [])) <= known, c["id"]
        assert set(c.get("tool_args", {})) <= known, c["id"]
        for pattern in c.get("must_include", []) + c.get("must_not", []):
            re.compile(pattern)
        assert not (c.get("no_tools") and c.get("required")), c["id"]
    assert [c["id"] for c in evaluation.load_cases(["P3", "F1"])] == ["P3", "F1"]
    assert re.fullmatch(r"[0-9a-f]{12}", evaluation.cases_hash())


# ---------- metrics -----------------------------------------------------------------------------------------
def test_score_success_and_every_failure_reason():
    fact = {"required": [["get_package", "search_business_docs"]], "must_include": ["\\b60\\b"],
            "must_not": ["\\$\\d"]}
    good = evaluation.score(fact, turn("Up to 60 photos.", [("get_package", {"name": "Memory Capsule"})]))
    assert good["task_success"] and good["tool_precision"] == 1.0 and good["failures"] == []
    bad = evaluation.score(fact, turn("It costs $79.", [("record_feedback", {"question": "x"})], outcome="gave_up"))
    assert not bad["task_success"] and bad["tool_precision"] == 0.0
    assert {f.split(":")[0] for f in bad["failures"]} == {"missing tool", "answer lacks /\\b60\\b/",
                                                           "answer contains /\\$\\d/", "outcome"}, bad["failures"]
    greet = evaluation.score({"no_tools": True}, turn("Hi", [("search_business_docs", {"query": "hi"})]))
    assert greet["failures"] == ["used a tool where none was needed: search_business_docs"]
    lead = {"required": [["record_customer_interest"]],
            "tool_args": {"record_customer_interest": {"email": "^sara@example\\.com$"}}}
    assert not evaluation.score(lead, turn("Saved.", [("record_customer_interest", {"email": "s@x.com"})]))["task_success"]
    assert evaluation.score(lead, turn("Saved.", [("record_customer_interest", {"email": "Sara@example.com"})]))["task_success"]
    saved = turn("ok", trace=[{"node": "act", "tool": "record_customer_interest", "args": {},
                               "observation": "OK: lead lead_1 saved"}])
    assert evaluation.score({"forbid_saved_lead": True}, saved)["failures"] == ["saved a lead it should not have"]
    assert evaluation.score({"forbidden": ["record_feedback"]},
                            turn("x", [("record_feedback", {"question": "q"})]))["failures"] == ["forbidden tool: record_feedback"]


def test_requests_count_the_empty_reply_retries():
    trace = [{"node": "reason", "llm": {"warnings": ["the first reply was empty, so the request was sent once more"]}},
             {"node": "act"}, {"node": "reason", "llm": {"warnings": []}}]
    assert evaluation.requests_used(trace) == 3


def test_distinct_n():
    assert evaluation.distinct_n(["a b c", "a b c"]) == 0.5 and evaluation.distinct_n(["a b c d"]) == 1.0
    assert evaluation.distinct_n([""]) == 0.0


# ---------- the runner --------------------------------------------------------------------------------------
def run(out, fail_after=None, cases=CASES):
    llm = FollowerLLM(cases, fail_after)
    written = runner.run_plan(PLAN, cases, 1, out, llm_factory=lambda provider, model: llm, verbose=False)
    return written, llm


def test_runner_writes_rows_and_the_estimate_equals_the_calls():
    out = TMP / "unit_rows.jsonl"
    written, llm = run(out)
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert written == len(rows) == 6
    assert llm.requests == sum(evaluation.estimated_calls(c) for c in CASES) * len(PLAN["configs"])
    assert all(r["metrics"]["task_success"] for r in rows), [r["metrics"]["failures"] for r in rows]
    row = next(r for r in rows if r["config_id"] == "nora-cold" and r["case_id"] == "T2")
    assert row["run_id"] == "unit:nora-cold:T2:0" and row["persona"] == "nora" and row["error"] is None
    assert row["settings_requested"]["temperature"] == 0.0 and row["settings_requested"]["top_k"] == 5
    assert row["settings_dropped"] == {"temperature": "ignored"} and row["cases_hash"] == evaluation.cases_hash()
    assert [t[0] for t in row["tools"]] == ["search_business_docs", "record_feedback"]


def test_runner_resumes_and_retries_errors():
    out = TMP / "unit_resume.jsonl"
    run(out)
    written, llm = run(out)
    assert written == 0 and llm.requests == 0                       # everything finished: nothing is sent
    lines = out.read_text(encoding="utf-8").splitlines()
    broken = json.loads(lines[0])
    broken.update(error="busy", metrics=None)
    out.write_text("\n".join([json.dumps(broken)] + lines[1:]) + "\n", encoding="utf-8")
    written, llm = run(out)
    assert written == 1 and llm.requests == evaluation.estimated_calls(CASES[0])


def test_runner_stops_cleanly_on_quota_and_resumes():
    out = TMP / "unit_quota.jsonl"
    try:
        run(out, fail_after=4)
        raise AssertionError("QuotaExhausted must stop the run")
    except QuotaExhausted:
        pass
    before = len(out.read_text(encoding="utf-8").splitlines())
    assert before == 1                                              # T1 took 2 calls; T2 needed 3 more (> 4)
    written, _ = run(out)
    assert written == 6 - before


def test_dry_run_estimate_skips_finished_runs():
    out = TMP / "unit_estimate.jsonl"
    original = runner.model_of
    runner.model_of = lambda config: ("fake", "follower")
    try:
        runs, calls = runner.estimate(PLAN, CASES, 2, out)
        assert runs[("fake", "follower")] == 12 and calls[("fake", "follower")] == 2 * 2 * 6
        run(out)
        runs, calls = runner.estimate(PLAN, CASES, 1, out)
        assert not runs
    finally:
        runner.model_of = original


def test_plan_validation():
    path = TMP / "bad_plan.json"
    for bad, phrase in [({"name": "x", "configs": [{"id": "a", "persona": "zed"}]}, "unknown persona"),
                        ({"name": "x", "configs": [{"id": "a"}, {"id": "a"}]}, "duplicate"),
                        ({"name": "x", "configs": [{"id": "a", "variant": "odd"}]}, "unknown variant"),
                        ({"name": "x", "configs": [{"id": "a", "settings": {"temperature": 9}}]}, "outside")]:
        path.write_text(json.dumps(bad), encoding="utf-8")
        try:
            runner.load_plan(path)
            raise AssertionError(f"accepted: {bad}")
        except ValueError as e:
            assert phrase in str(e), (phrase, str(e))
    assert runner.config_settings({"persona": "nora", "settings": {"top_k": None}}).top_k is None


# ---------- the summarizer ----------------------------------------------------------------------------------
def test_repeat_variety():
    rows = [{"case_id": "C1", "answer": "a b c"}, {"case_id": "C1", "answer": "a b c"}, {"case_id": "C2", "answer": "x y"}]
    assert summary._repeat_variety(rows) == 0.5 and summary._repeat_variety(rows[2:]) is None


def test_summary_tables_and_rating_sheet():
    out = TMP / "unit_summary.jsonl"
    run(out)
    rows = summary.latest_rows(out)
    table = summary.summarize(rows)
    assert [t["config_id"] for t in table] == ["milo", "nora-cold"]
    milo = table[0]
    assert milo["runs"] == 3 and milo["errors"] == 0 and milo["success"] == 1.0 and milo["requests"] == 6
    assert milo["tokens"] == round((20 + 30 + 10) / 3) and 0 < milo["distinct_2"] <= 1
    md = summary.markdown("unit", rows, table)
    for heading in ("# Results: unit", "## Success by category", "## Cases × configurations"):
        assert heading in md
    assert "| T2 | 1/1 | 1/1 |" in md
    sheet = TMP / "ratings.csv"
    summary.ratings_sheet(rows, sheet)
    assert len(sheet.read_text(encoding="utf-8").splitlines()) == 1 + 6


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
