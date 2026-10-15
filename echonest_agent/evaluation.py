"""Automatic metrics for the experiments (Stage 7; PDF 2.3: "log your experiments and compare performance across
setups"; PDF 1 and 2.5: which agent and configuration worked best).

score() rates one agent turn against one case from tests/eval_cases.json. It judges what the agent DID (tools,
arguments, outcome) and a few phrases in its answer, never the exact wording, and lists every reason a case failed.
distinct_n() measures lexical variety across a set of answers (used per configuration in the summaries).
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES_FILE = ROOT / "tests" / "eval_cases.json"


def cases_hash(path=CASES_FILE):
    """Short SHA-256 of the case file: every result row records it, so a changed case set is visible."""
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]


def load_cases(subset="core", path=CASES_FILE):
    """subset: "core" (the 12 sweep cases), "full" (all), or a list of case ids (in that order)."""
    cases = json.loads(Path(path).read_text(encoding="utf-8"))["cases"]
    if subset == "full":
        return cases
    if subset == "core":
        return [c for c in cases if c.get("core")]
    by_id = {c["id"]: c for c in cases}
    missing = [i for i in subset if i not in by_id]
    if missing:
        raise ValueError(f"unknown case ids: {missing}")
    return [by_id[i] for i in subset]


def estimated_calls(case):
    """LLM calls for a turn that goes straight to the goal: one per required tool group, plus the final answer."""
    return 1 + len(case.get("required", []))


def requests_used(trace):
    """Requests actually sent: one per reason step, plus one when an empty reply was sent again."""
    reasons = [t for t in trace if t.get("node") == "reason"]
    retries = sum(1 for t in reasons for w in (t.get("llm") or {}).get("warnings", []) if "empty" in w)
    return len(reasons) + retries


def _sum(trace, key):
    values = [(t.get("llm") or {}).get(key) for t in trace if t.get("node") == "reason"]
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values), 2) if values else None


def _tokens(trace):
    values = [((t.get("llm") or {}).get("usage") or {}).get("total_tokens") for t in trace if t.get("node") == "reason"]
    values = [v for v in values if isinstance(v, int)]
    return sum(values) if values else None


def score(case, result):
    """Metrics for one turn (`result` is a graph.TurnResult). task_success needs every check to pass."""
    answer = result.answer or ""
    calls = result.tool_calls
    tools = [name for name, _ in calls]
    required = case.get("required", [])
    allowed = set() if case.get("no_tools") else {t for group in required for t in group} | set(case.get("allowed", []))
    failures = []

    for group in required:
        if not any(t in tools for t in group):
            failures.append(f"missing tool: {' or '.join(group)}")
    for t in sorted(set(tools) & set(case.get("forbidden", []))):
        failures.append(f"forbidden tool: {t}")
    if case.get("no_tools") and tools:
        failures.append(f"used a tool where none was needed: {', '.join(tools)}")
    for pattern in case.get("must_include", []):
        if not re.search(pattern, answer, re.I):
            failures.append(f"answer lacks /{pattern}/")
    for pattern in case.get("must_not", []):
        if re.search(pattern, answer, re.I):
            failures.append(f"answer contains /{pattern}/")
    for tool, checks in case.get("tool_args", {}).items():
        made = [args for name, args in calls if name == tool]
        if made and not any(all(re.search(p, str(args.get(arg, "")), re.I) for arg, p in checks.items())
                            for args in made):
            failures.append(f"wrong arguments for {tool}: {made}")
    lead_saved = any(t.get("node") == "act" and t.get("tool") == "record_customer_interest"
                     and str(t.get("observation", "")).startswith("OK") for t in result.trace)
    if case.get("forbid_saved_lead") and lead_saved:
        failures.append("saved a lead it should not have")
    if result.outcome != "final":
        failures.append(f"outcome: {result.outcome}")

    wrong = [t for t in tools if t not in allowed]
    return {
        "task_success": not failures,
        "failures": failures,
        "tool_precision": round(1 - len(wrong) / len(tools), 3) if tools else 1.0,
        "tools_used": len(tools),
        "outcome": result.outcome,
        "steps": result.steps,
        "format_errors": result.format_errors,
        "requests": requests_used(result.trace),
        "tokens": _tokens(result.trace),
        "latency_s": _sum(result.trace, "latency_s"),
        "words": len(answer.split()),
    }


def distinct_n(texts, n=2):
    """Unique word n-grams / all word n-grams over a set of answers (0 to 1; higher = more varied wording)."""
    grams = []
    for text in texts:
        words = re.findall(r"\w+", text.lower())
        grams += [tuple(words[i:i + n]) for i in range(len(words) - n + 1)]
    return round(len(set(grams)) / len(grams), 3) if grams else 0.0
