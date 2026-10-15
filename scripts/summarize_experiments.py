"""Summarize an experiment's results: one row per configuration, plus per-category and per-case tables (Stage 7).

Reads experiments/results/<plan>.jsonl (the latest row of each run counts) and writes
  experiments/summary/<plan>.csv   one row per configuration
  experiments/summary/<plan>.md    the same as tables, plus success by category, a case × config grid and the most
                                   common failure reasons
With --ratings-sheet it also writes experiments/ratings/<plan>.csv: every answer with empty 1-5 columns for a human
rating of helpfulness and persona fit (PDF 2.5: "which persona gave the most helpful or natural results").

Run from the repo root:  python scripts/summarize_experiments.py --plan experiments/plans/tiny.json
"""
import argparse
import csv
import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent.evaluation import distinct_n  # noqa: E402

RESULTS_DIR = ROOT / "experiments" / "results"
SUMMARY_DIR = ROOT / "experiments" / "summary"
RATINGS_DIR = ROOT / "experiments" / "ratings"
COLUMNS = ["config_id", "model", "persona", "variant", "cot", "settings", "runs", "errors", "success", "success_sd",
           "tool_precision", "format_errors", "steps", "requests", "tokens", "latency_s", "words", "words_sd",
           "distinct_2"]


def latest_rows(path):
    rows = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        rows[row["run_id"]] = row                 # a later row (a resumed or repeated run) replaces an earlier one
    return list(rows.values())


def _mean(values, digits=3):
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), digits) if values else None


def _sd(values, digits=3):
    values = [v for v in values if v is not None]
    return round(statistics.stdev(values), digits) if len(values) > 1 else None


def summarize(rows):
    """[{column: value}] per config, in first-appearance order."""
    by_config = defaultdict(list)
    for row in rows:
        by_config[row["config_id"]].append(row)
    table = []
    for config_id, group in by_config.items():
        ok = [r for r in group if not r.get("error")]
        m = [r["metrics"] for r in ok]
        per_repeat = defaultdict(list)
        for r in ok:
            per_repeat[r["repeat"]].append(r["metrics"]["task_success"])
        first = group[0]
        table.append({
            "config_id": config_id, "model": first["model"], "persona": first["persona"],
            "variant": first["variant"], "cot": first["cot"],
            "settings": json.dumps(first["settings_requested"], sort_keys=True),
            "runs": len(group), "errors": len(group) - len(ok),
            "success": _mean([x["task_success"] for x in m]),
            "success_sd": _sd([statistics.mean(v) for v in per_repeat.values()]),
            "tool_precision": _mean([x["tool_precision"] for x in m]),
            "format_errors": _mean([x["format_errors"] for x in m], 2),
            "steps": _mean([x["steps"] for x in m], 2),
            "requests": sum(x["requests"] for x in m),
            "tokens": _mean([x["tokens"] for x in m], 0),
            "latency_s": _mean([x["latency_s"] for x in m], 2),
            "words": _mean([x["words"] for x in m], 1),
            "words_sd": _sd([x["words"] for x in m], 1),
            "distinct_2": distinct_n([r["answer"] for r in ok]),
        })
    return table


def markdown(plan_name, rows, table):
    shown = ["config_id", "model", "persona", "runs", "errors", "success", "success_sd", "tool_precision",
             "format_errors", "steps", "requests", "latency_s", "words", "distinct_2"]
    out = [f"# Results: {plan_name}", "",
           f"{len(rows)} runs; cases file {sorted({r['cases_hash'] for r in rows})}. success = share of runs where "
           "every check passed (± spread across repeats).", "",
           "| " + " | ".join(shown) + " |", "|" + "---|" * len(shown)]
    out += ["| " + " | ".join("" if t[c] is None else str(t[c]) for c in shown) + " |" for t in table]

    configs = [t["config_id"] for t in table]
    ok_rows = [r for r in rows if not r.get("error")]
    categories = sorted({r["category"] for r in ok_rows})
    out += ["", "## Success by category", "", "| category | " + " | ".join(configs) + " |",
            "|" + "---|" * (len(configs) + 1)]
    for cat in categories:
        cells = []
        for c in configs:
            hits = [r["metrics"]["task_success"] for r in ok_rows if r["config_id"] == c and r["category"] == cat]
            cells.append(f"{sum(hits)}/{len(hits)}" if hits else "")
        out.append(f"| {cat} | " + " | ".join(cells) + " |")

    out += ["", "## Cases × configurations (passed / runs)", "", "| case | " + " | ".join(configs) + " |",
            "|" + "---|" * (len(configs) + 1)]
    for case in dict.fromkeys(r["case_id"] for r in rows):
        cells = []
        for c in configs:
            group = [r for r in rows if r["config_id"] == c and r["case_id"] == case]
            hits = [r["metrics"]["task_success"] for r in group if not r.get("error")]
            errors = len(group) - len(hits)
            cells.append(f"{sum(hits)}/{len(group)}" + (f" ({errors} error)" if errors else "") if group else "")
        out.append(f"| {case} | " + " | ".join(cells) + " |")

    reasons = Counter((r["config_id"], f) for r in ok_rows for f in r["metrics"]["failures"])
    if reasons:
        out += ["", "## Most common failure reasons", ""]
        out += [f"- {c}: {reason} ×{n}" for (c, reason), n in reasons.most_common(15)]
    return "\n".join(out) + "\n"


def ratings_sheet(rows, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["run_id", "config_id", "persona", "case_id", "message", "answer", "helpfulness_1to5",
                    "persona_fit_1to5", "notes"])
        for r in rows:
            if not r.get("error"):
                w.writerow([r["run_id"], r["config_id"], r["persona"], r["case_id"], r["message"], r["answer"],
                            "", "", ""])


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True, help="the plan file (its name selects the results file)")
    ap.add_argument("--ratings-sheet", action="store_true", help="also write a blank human-rating sheet")
    args = ap.parse_args(argv)
    name = json.loads(Path(args.plan).read_text(encoding="utf-8"))["name"]
    rows = latest_rows(RESULTS_DIR / f"{name}.jsonl")
    table = summarize(rows)
    SUMMARY_DIR.mkdir(parents=True, exist_ok=True)
    with (SUMMARY_DIR / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(table)
    md = markdown(name, rows, table)
    (SUMMARY_DIR / f"{name}.md").write_text(md, encoding="utf-8")
    print(md)
    if args.ratings_sheet:
        ratings_sheet(rows, RATINGS_DIR / f"{name}.csv")
        print(f"Rating sheet → {(RATINGS_DIR / f'{name}.csv').relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
