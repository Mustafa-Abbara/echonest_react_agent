"""LIVE tests of the three personas (Stage 5 gate): real LLM calls, about 30 requests.
Each persona answers G1, G2 and one task from its own focus. Checks the tools used and key facts in the answer, then
compares answer lengths: the voices must differ (Nora short, Sami long). Leads/feedback go to a temporary folder;
every trace is saved to docs/evidence/stage5_live_traces.jsonl.

Run from the repo root:
  python tests/live_persona_cases.py                    # the model in .env
  python tests/live_persona_cases.py --only nora --cases G1
"""
import argparse
import json
import re
import statistics
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import graph, personas, tools  # noqa: E402
from echonest_agent.llm import LLMError  # noqa: E402

EVIDENCE = ROOT / "docs" / "evidence" / "stage5_live_traces.jsonl"
LOOKUP = {"search_business_docs", "get_package"}


def used(result):
    return [name for name, _ in result.tool_calls]


def numbers(text):
    return text.replace(",", "").replace("$", "")


SHARED = [
    {"id": "G1", "message": "How long does a Legacy Edition take?",
     "check": lambda r: (set(used(r)) & LOOKUP and re.search(r"3\s*(to|-|–)\s*4 weeks", r.answer),
                         "looks it up; answers 3 to 4 weeks")},
    {"id": "G2", "message": "Do you sell gift cards?",
     "check": lambda r: ("search_business_docs" in used(r) and "record_feedback" in used(r),
                         "searches, finds nothing, then logs it with record_feedback")},
]
FOCUS = {
    "milo": {"id": "F-milo", "message": "I'd love to turn my grandmother's letters and photos into something "
                                        "special for her 80th birthday.",
             "check": lambda r: ("record_customer_interest" not in used(r) and "email" in r.answer.lower(),
                                 "lead capture: asks for the email, records nothing yet")},
    "nora": {"id": "F-nora", "message": "What's the price difference between the Event Story and the Life Timeline, "
                                        "and how much is the deposit on each?",
             "check": lambda r: ("get_package" in used(r) and all(n in numbers(r.answer)
                                                                  for n in ("150", "74.5", "149.5")),
                                 "looks up both; difference $150, deposits $74.50 and $149.50")},
    "sami": {"id": "F-sami", "message": "Can you help me plan a Memory Capsule for my daughter's graduation?",
             "check": lambda r: (set(used(r)) & LOOKUP and "60" in r.answer
                                 and re.search(r"^\s*(\*\*)?1[.)]", r.answer, re.M),
                                 "looks it up; a numbered plan within the 60-photo limit")},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated persona ids, e.g. nora,sami")
    ap.add_argument("--cases", help="comma-separated case ids, e.g. G1,F")
    args = ap.parse_args()
    chosen = [p for p in personas.PERSONAS.values() if not args.only or p.id in args.only.split(",")]

    tools.LOGS_DIR = Path(tempfile.mkdtemp(prefix="echonest_live_"))
    graph.TRACES_LOG = tools.LOGS_DIR / "traces.jsonl"
    agent = graph.ReActAgent(verbose=True)
    print(f"Model: {agent.llm}\n")
    for p in chosen:
        print(f"{p.name}: intended → effective on this model")
        for name, intended, effective, note in p.card(agent.llm):
            print(f"  {name:<18} {intended!s:<8} → {effective!s:<8} {note}")
    EVIDENCE.parent.mkdir(parents=True, exist_ok=True)

    summary, words = [], {}
    for p in chosen:
        for case in SHARED + [FOCUS[p.id]]:
            if args.cases and not any(case["id"].startswith(c) for c in args.cases.split(",")):
                continue
            print(f"\n================ {p.name} · {case['id']} ================")
            try:
                result = agent.run(case["message"], persona=p)
            except LLMError as e:
                print(f"❌ LLM error: {e}")
                summary.append((p.name, case["id"], False, f"LLM error: {e}", 0))
                break
            ok, what = case["check"](result)
            ok = bool(ok) and result.outcome == "final"
            summary.append((p.name, case["id"], ok, what, result.steps))
            words.setdefault(p.name, []).append(len(result.answer.split()))
            with EVIDENCE.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                    "model": agent.llm.profile.model, "provider": agent.llm.profile.provider,
                                    "persona": p.id, "case": case["id"], "message": case["message"], "pass": ok,
                                    "expected": what, "tools": used(result), "answer": result.answer,
                                    "words": len(result.answer.split()), "outcome": result.outcome,
                                    "steps": result.steps, "format_errors": result.format_errors,
                                    "trace": result.trace}, ensure_ascii=False, default=str) + "\n")

    print("\n================ SUMMARY ================")
    for name, cid, ok, what, steps in summary:
        print(f"{'✅' if ok else '❌'} {name} · {cid}: {what} ({steps} LLM calls)")
    print("\nAnswer length (words): " + ", ".join(f"{n} mean {statistics.mean(w):.0f} {w}" for n, w in words.items()))
    voices_ok = True
    if {"Nora", "Sami"} <= set(words):
        voices_ok = statistics.mean(words["Nora"]) < statistics.mean(words["Sami"])
        print(f"{'✅' if voices_ok else '❌'} voices differ: Nora's answers are shorter than Sami's")
    passed = sum(1 for _, _, ok, _, _ in summary if ok)
    print(f"\n{passed}/{len(summary)} passed; {agent.llm.requests} requests used. Traces → {EVIDENCE.relative_to(ROOT)}")
    return 0 if passed == len(summary) and voices_ok else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
