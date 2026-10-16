"""Run an experiment plan: every configuration × every case × every repeat, one result row per run (Stage 7).

A plan is a JSON file in experiments/plans/:
  {"name": "tiny", "description": "...", "cases": "core" | "full" | ["F1", ...], "repeats": 1,
   "configs": [{"id": "milo-flash", "persona": "milo", "provider": null, "model": null,
                "settings": {"temperature": 0.0}, "cot": true, "variant": "default"}]}
provider/model null = the ones in .env; "settings" overrides the persona's settings (null removes one).

Rows are appended to experiments/results/<plan>.jsonl as soon as each run finishes. Running the plan again
RESUMES: finished runs are skipped, runs that ended in an error are tried again. The run stops cleanly when a daily
quota is used up. Always start with --dry-run: it prints the runs and the estimated requests per model.

Run from the repo root:
  python scripts/run_experiments.py --plan experiments/plans/tiny.json --dry-run
  python scripts/run_experiments.py --plan experiments/plans/tiny.json
"""
import argparse
import json
import math
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from echonest_agent import evaluation, graph, personas, prompts  # noqa: E402
from echonest_agent.config import MODELS_FILE, load_profile  # noqa: E402
from echonest_agent.llm import LLMError, LLMSettings, QuotaExhausted, get_llm  # noqa: E402

RESULTS_DIR = ROOT / "experiments" / "results"
# prompt variants (Stage 9, PDF 2.3): worked examples in the instructions, and where the instructions go
VARIANTS = {"default": {}, "zero_shot": {"examples": 0}, "few_shot": {"examples": 3},
            "in_message": {"placement": "in_message"}}
OVERHEAD = 1.5   # live calls / clean-run estimate (format corrections, empty-reply retries): 9 / 6 in the Stage 7 tiny run


def load_plan(path):
    plan = json.loads(Path(path).read_text(encoding="utf-8"))
    for key in ("name", "configs"):
        if key not in plan:
            raise ValueError(f"plan {path} has no {key!r}")
    ids = [c["id"] for c in plan["configs"]]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate config ids in {path}")
    for c in plan["configs"]:
        if c.get("persona", personas.DEFAULT.id) not in personas.PERSONAS:
            raise ValueError(f"config {c['id']}: unknown persona {c.get('persona')!r}")
        if c.get("variant", "default") not in VARIANTS:
            raise ValueError(f"config {c['id']}: unknown variant {c.get('variant')!r}; known: {list(VARIANTS)}")
        config_settings(c)                                  # raises on an invalid setting
    return plan


def config_settings(config):
    """The persona's settings with the config's overrides applied (an override of None removes the setting)."""
    persona = personas.PERSONAS[config.get("persona", personas.DEFAULT.id)]
    merged = {**persona.settings, **config.get("settings", {})}
    return LLMSettings(**{k: v for k, v in merged.items() if v is not None})


def done_keys(path):
    """Run keys already finished without an error."""
    keys = set()
    if Path(path).exists():
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if not row.get("error"):
                keys.add(row["run_id"])
    return keys


def run_id(plan, config, case, repeat):
    return f"{plan['name']}:{config['id']}:{case['id']}:{repeat}"


def model_of(config):
    profile = load_profile(config.get("provider"), config.get("model"))
    return profile.provider, profile.model


def estimate(plan, cases, repeats, out_path):
    """Runs still to do and estimated requests per (provider, model), skipping finished runs."""
    done, runs, calls = done_keys(out_path), Counter(), Counter()
    for config in plan["configs"]:
        key = model_of(config)
        for case in cases:
            for r in range(repeats):
                if run_id(plan, config, case, r) not in done:
                    runs[key] += 1
                    calls[key] += evaluation.estimated_calls(case)
    return runs, calls


def run_plan(plan, cases, repeats, out_path, llm_factory=get_llm, verbose=True):
    """Run every unfinished (config, case, repeat). Returns the number of rows written. Raises QuotaExhausted."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    done, written, case_hash = done_keys(out_path), 0, evaluation.cases_hash()
    for config in plan["configs"]:
        todo = [(case, r) for case in cases for r in range(repeats) if run_id(plan, config, case, r) not in done]
        if not todo:
            continue
        persona = personas.PERSONAS[config.get("persona", personas.DEFAULT.id)]
        settings = config_settings(config)
        variant = config.get("variant", "default")
        llm = llm_factory(config.get("provider"), config.get("model"))
        agent = graph.ReActAgent(llm=llm, verbose=False)
        for case, r in todo:
            row = {"run_id": run_id(plan, config, case, r),
                   "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), "plan": plan["name"],
                   "cases_hash": case_hash, "config_id": config["id"], "provider": llm.profile.provider,
                   "model": llm.profile.model, "persona": persona.id, "variant": variant,
                   "cot": config.get("cot", True), "settings_requested": settings.as_dict(), "case_id": case["id"],
                   "category": case["category"], "repeat": r, "message": case["message"]}
            try:
                v = VARIANTS[variant]
                instructions = prompts.build_instructions(row["cot"], examples=v["examples"]) if "examples" in v else None
                result = agent.run(case["message"], history=case.get("history", []), persona=persona,
                                   settings=settings, cot=row["cot"], instructions=instructions,
                                   placement=v.get("placement", "system"), log=False)
            except QuotaExhausted:
                raise
            except LLMError as e:
                row.update(error=str(e))
            else:
                first = next((t["llm"] for t in result.trace if t.get("node") == "reason"), {})
                row.update(settings_sent=first.get("settings_sent"), settings_dropped=first.get("settings_dropped"),
                           answer=result.answer, tools=result.tool_calls, metrics=evaluation.score(case, result),
                           trace=result.trace, error=None)
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            written += 1
            if verbose:
                m = row.get("metrics") or {}
                status = "ERROR " + row["error"] if row.get("error") else ("✅" if m["task_success"] else "❌ " +
                                                                           "; ".join(m["failures"]))
                print(f"  {config['id']:<22} {case['id']:<4} r{r}  {status}")
    return written


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", required=True)
    ap.add_argument("--cases", help="override the plan: core, full, or comma-separated ids")
    ap.add_argument("--repeats", type=int, help="override the plan's repeats")
    ap.add_argument("--dry-run", action="store_true", help="print runs and estimated requests, send nothing")
    args = ap.parse_args(argv)

    plan = load_plan(args.plan)
    subset = args.cases or plan.get("cases", "core")
    if isinstance(subset, str) and subset not in ("core", "full"):
        subset = subset.split(",")
    cases = evaluation.load_cases(subset)
    repeats = args.repeats or plan.get("repeats", 1)
    out_path = RESULTS_DIR / f"{plan['name']}.jsonl"

    runs, calls = estimate(plan, cases, repeats, out_path)
    models = json.loads(Path(MODELS_FILE).read_text(encoding="utf-8"))["models"]
    print(f"Plan {plan['name']}: {len(plan['configs'])} config(s) × {len(cases)} case(s) × {repeats} repeat(s); "
          f"cases {evaluation.cases_hash()}; results → {out_path.relative_to(ROOT)}")
    for (provider, model), n in sorted(runs.items()):
        info = models.get(model, {})
        limit = "local, no quota" if info.get("local") else f"daily limit {info.get('rpd') or 'unknown'}"
        clean = calls[(provider, model)]
        print(f"  {model} via {provider}: {n} run(s) to do, {clean} requests if every step is clean, "
              f"up to about {math.ceil(clean * OVERHEAD)} with format corrections ({limit})")
    if not runs:
        print("  nothing to do: every run is finished")
    if args.dry_run or not runs:
        return 0
    try:
        written = run_plan(plan, cases, repeats, out_path)
    except QuotaExhausted as e:
        print(f"\n🛑 {e}\nStopped cleanly; run the same command after the reset to resume.")
        return 2
    print(f"\n{written} row(s) written to {out_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    raise SystemExit(main())
