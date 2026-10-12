"""One live request to the model chosen in .env (or on the command line), to check a model switch works.

Run from the repo root:
  python scripts/smoke_llm.py                                    # the model in .env (LLM_PROVIDER / LLM_MODEL)
  python scripts/smoke_llm.py --provider <provider> --model <model id>    # any pair from config/models.json
Costs one request. Prints the answer and which settings were sent or dropped for this model.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from echonest_agent.llm import LLMError, LLMSettings, get_llm  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider")
    ap.add_argument("--model")
    args = ap.parse_args()

    llm = get_llm(args.provider, args.model)
    print(llm)
    settings = LLMSettings(temperature=0.3, top_k=20, presence_penalty=0.3, max_tokens=400,
                           stop=["Observation:"], seed=11, reasoning_effort="low")
    try:
        r = llm.complete([{"role": "system", "content": "You are Milo, EchoNest's memory concierge. One sentence."},
                          {"role": "user", "content": "Hi! Who are you?"}], settings)
    except LLMError as e:
        raise SystemExit(f"❌ {e}")
    print("answer   :", r.text.strip())
    print("sent     :", r.settings_sent)
    print("dropped  :", r.settings_dropped)
    if r.settings_adjusted:
        print("adjusted :", r.settings_adjusted)
    print("unverified:", r.unverified, "| finish:", r.finish_reason, "| latency:", r.latency_s, "s",
          "| thinking returned:", bool(r.thinking))
    for w in r.warnings:
        print("⚠️ ", w)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
