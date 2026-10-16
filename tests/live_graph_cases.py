"""LIVE tests of the ReAct graph (Stage 4 gate): real LLM calls, about 30-40 requests with the default repeats.
Checks which tools the agent used and key facts in its answer (not the exact wording).
Leads/feedback go to a temporary folder; every trace is saved to docs/evidence/stage4_live_traces.jsonl.

Run from the repo root:
  python tests/live_graph_cases.py                 # the model in .env
  python tests/live_graph_cases.py --only G1,G2 --repeats 1
"""
import argparse
import json
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import graph, tools  # noqa: E402
from echonest_agent.llm import LLMError, LLMSettings  # noqa: E402

EVIDENCE = ROOT / "docs" / "evidence" / "stage4_live_traces.jsonl"
LOOKUP = {"search_business_docs", "get_package"}


def used(result):
    return [name for name, _ in result.tool_calls]


def args_of(result, tool):
    return [a for name, a in result.tool_calls if name == tool]


CASES = [
    {"id": "G1", "message": "How long does a Legacy Edition take?", "repeats": 3,
     "check": lambda r: (set(used(r)) & LOOKUP and re.search(r"3\s*(to|-|–)\s*4 weeks", r.answer),
                         "looks it up; answers 3 to 4 weeks")},
    {"id": "G2", "message": "Do you sell gift cards?", "repeats": 3,
     "check": lambda r: ("search_business_docs" in used(r) and "record_feedback" in used(r),
                         "searches, finds nothing, then logs it with record_feedback")},
    {"id": "G3", "message": "Hi!", "repeats": 1,
     "check": lambda r: (not used(r) and r.outcome == "final", "greeting: no tool")},
    {"id": "G4", "message": "I'm Sara, sara@example.com, I'd like a Life Timeline for my parents.", "repeats": 1,
     "check": lambda r: (any(a.get("email") == "sara@example.com" and "sara" in a.get("name", "").lower()
                             for a in args_of(r, "record_customer_interest")),
                         "records the lead with the right email and name")},
    {"id": "G5", "message": "How much is a Corporate Story?", "repeats": 3,
     "check": lambda r: (set(used(r)) & LOOKUP and not re.search(r"\$\s?\d", r.answer)
                         and re.search(r"no fixed price|quote|consultation", r.answer, re.I),
                         "looks it up; no invented price; mentions the quote/consultation")},
    {"id": "G6", "message": "Do you restore old film reels?", "repeats": 1,
     "check": lambda r: (set(used(r)) & LOOKUP and "record_feedback" in used(r)
                         and re.search(r"not|don't|do not", r.answer, re.I),
                         "looks it up, says it isn't offered, logs the demand")},
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated case ids, e.g. G1,G5")
    ap.add_argument("--repeats", type=int, help="override every case's repeat count")
    ap.add_argument("--evidence", help="file to append the rows to (default: the stage's evidence file)")
    args = ap.parse_args()
    evidence = ROOT / args.evidence if args.evidence else EVIDENCE
    cases = [c for c in CASES if not args.only or c["id"] in args.only.split(",")]

    tools.LOGS_DIR = Path(tempfile.mkdtemp(prefix="echonest_live_"))
    graph.TRACES_LOG = tools.LOGS_DIR / "traces.jsonl"
    agent = graph.ReActAgent(verbose=True)
    settings = LLMSettings(max_tokens=600, reasoning_effort="low")
    print(f"Model: {agent.llm}\n")
    evidence.parent.mkdir(parents=True, exist_ok=True)

    summary = []
    for case in cases:
        for i in range(args.repeats or case["repeats"]):
            print(f"\n================ {case['id']} run {i + 1} ================")
            try:
                result = agent.run(case["message"], settings=settings)
            except LLMError as e:
                print(f"❌ LLM error: {e}")
                summary.append((case["id"], i + 1, False, f"LLM error: {e}", 0))
                break
            ok, what = case["check"](result)
            ok = bool(ok)
            summary.append((case["id"], i + 1, ok, what, result.steps))
            with evidence.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "model": agent.llm.profile.model, "provider": agent.llm.profile.provider,
                                    "case": case["id"], "run": i + 1, "message": case["message"], "pass": ok,
                                    "expected": what, "tools": used(result), "answer": result.answer,
                                    "outcome": result.outcome, "steps": result.steps,
                                    "format_errors": result.format_errors, "trace": result.trace},
                                   ensure_ascii=False, default=str) + "\n")

    print("\n================ SUMMARY ================")
    for cid, run, ok, what, steps in summary:
        print(f"{'✅' if ok else '❌'} {cid} run {run}: {what} ({steps} LLM calls)")
    passed = sum(1 for _, _, ok, _, _ in summary if ok)
    print(f"\n{passed}/{len(summary)} passed; {agent.llm.requests} requests used. Traces → {evidence.relative_to(ROOT)}")
    return 0 if passed == len(summary) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
