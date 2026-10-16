# EchoNest ReAct agent with configurable personas

EECE 503P/798S (Agentic Systems), **Assignment C4**: a ReAct agent built by hand in **LangGraph**, with three
personas defined by prompt traits *and* LLM settings, a dedicated instructions block, and logged experiments that
compare personas, LLM settings, model types and prompt techniques.

The agent works for **EchoNest**, a fictional digital-memory studio (the scenario from Assignment C3). It has no
business facts in its prompt: it looks them up with tools, captures leads, and logs what the documents can't answer.

| | |
|---|---|
| 📓 Main notebook | [`react_agent.ipynb`](react_agent.ipynb): use case, ReAct loop, personas, instructions, results, **reflection** |
| 💬 Working assistant | `python app.py`: Gradio chat with a persona selector and the agent's steps shown ([screenshots 09–14](docs/screenshots)) |
| 🧪 Experiments | [`experiments/`](experiments): plans, one row per run, summaries, [notes](experiments/notes.md) |
| 🗺️ Plan | [`docs/planning/Roadmap.md`](docs/planning/Roadmap.md) (stages and the requirements table) |

## Assignment checklist

| PDF item (points) | Where | Evidence |
|---|---|---|
| Use-case summary and write-up (10) | [`docs/use_case.md`](docs/use_case.md); notebook §1 | goal, audience, tools, constraints |
| ReAct logic manually implemented (30) | [`echonest_agent/graph.py`](echonest_agent/graph.py), [`react_parser.py`](echonest_agent/react_parser.py); notebook §2 | [graph diagram](docs/react_graph.md); `tests/test_graph.py` (incl. *no prebuilt agent*); live traces in `docs/evidence/` |
| Persona design: prompt and configuration (20) | [`echonest_agent/personas.py`](echonest_agent/personas.py); notebook §4 | intended vs effective settings per model; `tests/test_personas.py` |
| Configuration experimentation and comparison (15) | [`experiments/`](experiments); notebook §7 | temperature, top-p, top-k, both penalties, max tokens, reasoning, model type; CoT, zero/few-shot, system vs in-message |
| Clear instructions design (10) | [`echonest_agent/prompts.py`](echonest_agent/prompts.py); notebook §5 | single-purpose rules, inputs/outputs, worked example, no persona conflict (tests) |
| Creativity, clarity, reflection (15) | notebook §8 | the five questions answered with plan and run ids |
| Working assistant (§1) | [`app.py`](app.py), [`echonest_agent/agent.py`](echonest_agent/agent.py) | final run on the submission code: G1–G6 12/12, memory and lead flow M1–M2 5/6 (`docs/evidence/stage12_final_*.jsonl`); UI screenshots 09–14 |

## Architecture

```
User ─▶ Gradio (app.py: persona dropdown, steps shown) ─▶ agent.respond(message, history, persona)
                                                              │ history = final answers only
                                                              ▼
            ┌──────────────────── LangGraph StateGraph (graph.py) ────────────────────┐
            │  reason ──route_after_reason──▶ act ──▶ reason          (tool, Observation)
            │     │                     ├──▶ recover ──▶ reason       (format correction)
            │     │                     ├──▶ finalize ──▶ END         (Final Answer)
            │     │                     └──▶ give_up ──▶ END          (too many steps)
            └─────┼───────────────────────────────────────────────────────────────────┘
                  ▼ every reason step
            llm.complete(messages, persona settings + stop=["Observation:"])
                  │ sends only the settings the model honours (measured), logs what it drops
                  ▼
            Gemini (google-genai or OpenAI-compatible) │ Ollama (local) │ OpenAI
```

- **ReAct protocol:** text (Thought / Action / Action Input / Final Answer), parsed by `parse_react()`, so it works
  with any chat model. The stop sequence stops invented Observations; `recover` corrects a broken format (twice at
  most), `give_up` apologises and logs the question.
- **Tools** ([`tools.py`](echonest_agent/tools.py)), described in the system prompt from the same registry:
  `search_business_docs(query)`, `get_package(name)`, `record_customer_interest(email, name, message)`,
  `record_feedback(question)`. Leads and feedback go to `logs/`.
- **No prebuilt agent:** no `create_react_agent`, `ToolNode`, `tools_condition`, `AgentExecutor` or `bind_tools`.

## Personas

| | Milo, Memory Concierge | Nora, Package Specialist | Sami, Story Planner |
|---|---|---|---|
| Task | first contact, general questions, leads | exact prices, comparisons, deposits | planning chapters, photos, interview questions |
| Voice | warm, 2–4 sentences | precise, number first, ≤ 70 words | enthusiastic, numbered plans, ≤ 250 words |
| temperature / top-p / top-k | 0.7 / 0.9 / 40 | 0.1 / 0.5 / 5 | 1.1 / 0.95 / 64 |
| frequency / presence penalty | 0.2 / 0.3 | 0 / 0 | 0.4 / 0.6 |
| max tokens / reasoning | 400 / low | 700 / medium | 800 / minimal |

Each setting has a one-line rationale in `personas.py`. **Which settings take effect depends on the model**, measured
by `scripts/probe_settings.py` ([`docs/settings_support.md`](docs/settings_support.md)): `gemini-3.5-flash-lite`
ignores temperature, top-p and top-k and rejects both penalties; `qwen3:4b-instruct` (Ollama, native API) honours
all of them. The persona card in the app and in the notebook shows intended vs effective settings.

## Instructions block

Shared by every persona ([`prompts.py`](echonest_agent/prompts.py)): **Inputs you receive**, 13 **Rules** (one
purpose, one sentence each), a **Worked example** built from the real tool output, and the **Output format** (last:
in the middle it made Flash-Lite return empty replies). Length and tone live only in the personas, rules only in the
instructions; tests check both directions.

## Results (details: notebook §7–8, [`experiments/notes.md`](experiments/notes.md))

| Finding | Evidence |
|---|---|
| **Model type matters most**: Flash-Lite 85–94% task success, qwen3:4b-instruct 59–62% (it skips lookups) | `personas_by_model`, `model_type_core` |
| **Best persona on the shipped model: Milo** (32/34); voices differ clearly (Sami's answers twice as long) | `p_flash` |
| Human ratings (30 answers): Milo most helpful (4.6), Nora most in character (4.9), Sami least consistent (3.9: strong on plans, flat on prices) | `experiments/ratings/` |
| **Prompt traits set the voice; live sampling settings add variety** (Sami vs Nora distinct-2: +0.02 on Flash-Lite, +0.09 on qwen) | `personas_by_model` |
| Temperature 0, top-p 0.3 and top-k 1 gave **identical** runs (greedy decoding); temperature 1.4 was the worst | `s_qwen` |
| High reasoning failed at max_tokens 400 (5/12: thinking used the budget) and passed at 1200 (12/12) | `s_flash` |
| Temperature 1.4 raised variety across repeats from 0.31 to 0.84, without fixing grounding | `v_qwen` |
| Without visible Thought lines the agent skipped lookups (10/12 vs 12/12); one worked example beat zero and three | `prompt_flash` |
| Instructions in the user message: same success, 1 format correction instead of 11, 23% fewer requests | `prompt_confirm` |

**Best combination:** Milo on Flash-Lite with the shipped prompt (Thought lines, one worked example, instructions in
the system prompt), low reasoning, max_tokens 400: 31–32 of 34 cases.

## Switching the model

Configuration only: set `LLM_PROVIDER` / `LLM_MODEL` in `.env` to an entry of
[`config/models.json`](config/models.json). For a new model, add it there and measure it once:
`python scripts/probe_settings.py --provider <p> --model <m>`, then check with `python scripts/smoke_llm.py`. Only
`echonest_agent/config.py` and `llm.py` contain provider code; `tests/test_llm.py` fails if it appears elsewhere.

**Drill (2026-10-16):** with only two lines added to `.env` (`LLM_PROVIDER=ollama_native`,
`LLM_MODEL=qwen3:4b-instruct`) and no code change, the smoke call, the 122 offline tests and the agent ran on the local
model (`experiments/plans/switch_drill.json`: 1 of 3 cases passed, qwen's known failures); with `.env` restored, the
default Flash-Lite passed 3 of 3 (`switch_drill_flash.json`). A fresh clone with a fresh venv and a new `.env` installed
in about a minute and passed the 122 tests, the smoke call and the notebook's Restart & Run All.

## How to run

```bash
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env                      # add GEMINI_API_KEY
python app.py                             # the assistant (http://localhost:7860)
for t in tests/test_*.py; do python "$t" > /dev/null || echo "FAILED: $t"; done
```
- Notebook: open `react_agent.ipynb` and run all; `RUN_LIVE = False` needs no key.
- Experiments: `python scripts/run_experiments.py --plan experiments/plans/<plan>.json --dry-run` (estimates the
  requests), then without `--dry-run` (resumes, stops cleanly on the daily quota); summarize with
  `python scripts/summarize_experiments.py --plan experiments/plans/<plan>.json`.
- Local model (optional): install Ollama, `ollama pull qwen3:4b-instruct`, `ollama serve`, then
  `LLM_PROVIDER=ollama_native`, `LLM_MODEL=qwen3:4b-instruct`.

## Limitations

- One repeat per case for most plans: on the 12-case core set one case is 8 points, and differences of one case are
  within the measured noise.
- Two models; the local one is slow (about 14 s per turn) and its results are committed as evidence.
- Automatic scoring uses fixed patterns and can miss a correct answer (one known false negative, documented in the
  notebook §9); human ratings cover 30 answers by one rater (the author).
- Milo's max_tokens 400 is tight: once his hidden reasoning used 309 tokens and cut a reply (about 800 would be safer).
- Persona vs rule tension varies from run to run: in the final run Sami answered a project request with a plan
  instead of asking for contact details first (he passed the same test in Stage 6).
- The free tier allows 500 Flash-Lite requests a day; the experiments took two quota days.

## Key safety

The key is read only from `.env` through the LLM layer and never printed. `.env` is git-ignored; `.env.example` holds
a placeholder. Before every push the history is scanned (`git log --all -p | grep -E "AIza|sk-|AQ\."`).

The Assignment C3 version of this repo (notebook `business_agent.ipynb`, router, reflection, Hugging Face Space) is
at tag `a4-start`.
