"""LIVE multi-turn tests through the orchestrator (Stage 6 gate): real LLM calls, about 25 requests.
For each persona: M1 (memory: the name is remembered on a later turn) and M2 (a lead over 3 turns: asks for the
details first, records nothing until it has the email, then calls record_customer_interest with the right
arguments). The history is passed the way Gradio does, trace messages included, so the test also proves that
only final answers reach the model. Leads/feedback go to a temporary folder; every turn is saved to
docs/evidence/stage6_live_chat.jsonl.

Run from the repo root:
  python tests/live_chat_cases.py                 # the model in .env
  python tests/live_chat_cases.py --only nora --cases M2
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import agent, graph, personas, tools  # noqa: E402

EVIDENCE = ROOT / "docs" / "evidence" / "stage6_live_chat.jsonl"


def used(reply):
    return [name for name, _ in reply.result.tool_calls] if reply.result else []


def lead_args(reply):
    return [args for name, args in (reply.result.tool_calls if reply.result else []) if name == "record_customer_interest"]


CASES = [
    {"id": "M1", "turns": [
        ("Hi, I'm Karim.", lambda r: (bool(r.result), "replies")),
        ("Can you remind me what my name is?", lambda r: ("karim" in r.answer.lower(), "remembers the name Karim")),
    ]},
    {"id": "M2", "turns": [
        ("I'd like a Memory Capsule for my sister's graduation.",
         lambda r: ("record_customer_interest" not in used(r) and "email" in r.answer.lower(),
                    "asks for name and email, records nothing")),
        ("My name is Rania.",
         lambda r: ("record_customer_interest" not in used(r) and "email" in r.answer.lower(),
                    "still no email: asks for it, records nothing")),
        ("It's rania@example.com",
         lambda r: (any(a.get("email") == "rania@example.com" and "rania" in a.get("name", "").lower()
                        for a in lead_args(r)), "records the lead with Rania's name and email")),
    ]},
]


def as_gradio(history, message, reply):
    """What Gradio's history holds after a turn: the user message, the collapsed trace, then the answer."""
    trace = [{"role": "assistant", "content": f"{name} {args}", "metadata": {"title": f"🔧 {name}"}}
             for name, args in (reply.result.tool_calls if reply.result else [])]
    return history + [{"role": "user", "content": message}, *trace,
                      {"role": "assistant", "content": reply.answer, "metadata": {}}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="comma-separated persona ids")
    ap.add_argument("--cases", help="comma-separated case ids, e.g. M2")
    ap.add_argument("--evidence", help="file to append the rows to (default: the stage's evidence file)")
    args = ap.parse_args()
    evidence = ROOT / args.evidence if args.evidence else EVIDENCE
    tools.LOGS_DIR = Path(tempfile.mkdtemp(prefix="echonest_live_"))
    graph.TRACES_LOG = tools.LOGS_DIR / "traces.jsonl"
    print(f"Model: {agent.get_agent().llm}")
    evidence.parent.mkdir(parents=True, exist_ok=True)

    summary = []
    for p in personas.PERSONAS.values():
        if args.only and p.id not in args.only.split(","):
            continue
        for case in CASES:
            if args.cases and case["id"] not in args.cases.split(","):
                continue
            print(f"\n================ {p.name} · {case['id']} ================")
            history, ok_all, failed_at = [], True, None
            for i, (message, check) in enumerate(case["turns"], 1):
                reply = agent.respond(message, history, persona_id=p.id)
                ok, what = check(reply)
                ok = bool(ok) and reply.error is None
                print(f"👤 {message}\n🔧 {used(reply)}\n🤖 {reply.answer}\n{'✅' if ok else '❌'} turn {i}: {what}")
                with evidence.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                        "model": agent.get_agent().llm.profile.model, "persona": p.id,
                                        "case": case["id"], "turn": i, "message": message,
                                        "history_sent": agent.gradio_to_api(history), "pass": ok, "expected": what,
                                        "tools": used(reply), "answer": reply.answer, "error": reply.error,
                                        "trace": reply.result.trace if reply.result else None},
                                       ensure_ascii=False, default=str) + "\n")
                if not ok and failed_at is None:
                    ok_all, failed_at = False, f"turn {i}: {what}"
                history = as_gradio(history, message, reply)
            summary.append((p.name, case["id"], ok_all, failed_at))

    print("\n================ SUMMARY ================")
    for name, cid, ok, failed_at in summary:
        print(f"{'✅' if ok else '❌'} {name} · {cid}" + (f" (failed at {failed_at})" if failed_at else ""))
    passed = sum(1 for _, _, ok, _ in summary if ok)
    print(f"\n{passed}/{len(summary)} passed; {agent.get_agent().llm.requests} requests used. "
          f"Turns → {evidence.relative_to(ROOT)}")
    return 0 if passed == len(summary) else 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
