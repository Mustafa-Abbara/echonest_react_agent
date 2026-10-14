# Handoff: moving to the Mac in the middle of Stage 4 (2026-10-12)

> **Update 2026-10-14:** Stage 4 is done on the Mac (see the roadmap's Stage 4 "Done" note). Next: Stage 5.
> Still open: Stage 0b (`ollama pull qwen3:8b`, then the probe) and the qwen3 leg of the switch drill.

Written at the end of the Windows session so a new session (on the Mac) can continue without that conversation.
**New session: read this file, [Roadmap.md](Roadmap.md) (the plan; its "Requirements Coverage" table is the
checklist) and the assignment PDF `C4 - Agent Personas  Thinking Mechanisms.pdf` (not in git: copy it over).**
The older [HANDOFF_FROM_A3.md](HANDOFF_FROM_A3.md) explains the A3 starting point.

## 1. Where things stand

| Stage | Status | Commit |
|---|---|---|
| 0 Settings probe (what each model honours) | ✅ pushed | `588730a` |
| 0b Local model probe (Ollama `qwen3:8b`) | ⏳ code ready (`3563e84`); **the model was never downloaded** (slow network) | – |
| 1 Provider-neutral LLM layer | ✅ pushed; the only open item is the qwen3 leg of the switch drill | `8d042ab` |
| 2 Use-case write-up + knowledge tools | ✅ pushed | `bf2d22c` |
| 3 ReAct format + parser (36/36 fixtures) | ✅ pushed | `6e3d276` |
| 4 LangGraph ReAct loop | ✅ done on the Mac 2026-10-14 (100 offline tests; live G1–G6 13/13) | "Stage 4: LangGraph ReAct loop" |
| 5–12 | not started | – |

85 offline tests pass (Stages 0–3). Stage 4's `tests/test_graph.py` (14 offline tests) and
`tests/live_graph_cases.py` (G1–G6, about 35 requests) have **never been run**. Expect small fixes.

## 2. Next steps, in order

1. Set up the Mac (section 3) and run all offline tests: everything except `test_graph.py` must pass as-is.
2. `pip install langgraph`, then pin the exact version in `requirements.txt` (the roadmap expected 1.2.x). Check
   what `graph.invoke()` returns in that version: `graph.py` already handles both a plain dict and an object with
   `.value`.
3. `python tests/test_graph.py` → fix until 14/14 pass.
4. `python tests/live_graph_cases.py` (about 35 Flash-Lite requests). Gate: G1–G6 pass (G1, G2 and G5 three times
   each). Traces go to `docs/evidence/stage4_live_traces.jsonl`.
5. Export the graph diagram (`graph.get_graph().draw_mermaid()` → `docs/react_graph.md`), update the roadmap's
   Stage 4 "Done" note and requirements rows, make the proper **"Stage 4: LangGraph ReAct loop"** commit.
6. Optional, whenever the network allows: `ollama pull qwen3:8b`, then Stage 0b (two probe runs plus `--report`).
   That turns the top-k / penalty rows of the requirements table green.

## 3. Mac setup

```bash
git clone https://github.com/Mustafa-Abbara/echonest_react_agent.git
cd echonest_react_agent
python3.12 -m venv .venv            # Python 3.12 (Windows used 3.12.6); e.g. brew install python@3.12
source .venv/bin/activate
pip install -r requirements-dev.txt # includes requirements.txt
pip install langgraph               # Stage 4; pin it afterwards
# .env is NOT in git: copy it from the Windows PC (AirDrop/USB), or create it from .env.example
for t in tests/test_*.py; do python "$t" > /dev/null || echo "FAILED: $t"; done
```
- `.env` needs `GEMINI_API_KEY=...`. `LLM_PROVIDER` / `LLM_MODEL` are optional (the defaults are
  `gemini_native` / `gemini-3.5-flash-lite`). Check it works with `python scripts/smoke_llm.py` (1 request).
- Local model (optional): install Ollama for macOS, then `ollama pull qwen3:8b` (about 5 GB; fine on Apple Silicon
  with 16 GB of RAM).
- The roadmap's commands are PowerShell (`.\.venv\Scripts\python.exe`): on the Mac use `python` inside the venv.

## 4. Decisions already made (don't relitigate)

- **The assignment PDF is the source of truth.** Build what its requirements need, plus the user's own requirement
  below; no extras. (A usage ledger and `estimate_quote` were dropped for this reason.)
- **Switching model or provider must be configuration only** (`.env` + `config/models.json`). Only
  `echonest_agent/config.py` and `llm.py` may contain provider code; `tests/test_llm.py` enforces it.
- **Framework: LangGraph**, with the ReAct loop written by hand: no `create_react_agent`, `ToolNode`,
  `tools_condition`, `AgentExecutor` or `bind_tools` (`tests/test_graph.py` checks the code). **Text ReAct**
  (Thought / Action / Action Input / Final Answer), parsed by `react_parser.py`, not native tool calling.
- **Package layout:** `echonest_agent/` is the source of truth; a notebook will import it later (Stage 10/11).
  The A3 notebook, `app.py` and the export scripts are legacy until Stages 6/11.
- **Default provider `gemini_native`** (Google's SDK: the only Gemini path that honours `seed`).
- **Three models, each with a job** (Roadmap, "Status After Stage 0"):
  - Flash-Lite: the agent and the demo;
  - Gemma 4: temperature/top_p sweeps;
  - local qwen3: top-k and penalties.

  **Personas must be compared on models that honour their settings**, with Flash-Lite as the contrast.

## 5. Stage 0 facts that shape everything (details: `docs/stage0_findings.md`)

- `gemini-3.5-flash-lite`:
  - ignores temperature and top_p;
  - rejects top_k, both penalties, and seed (compatible path); seed works natively;
  - honours max_tokens, stop and reasoning_effort (all 4 levels).
- `gemma-4-26b-a4b-it`:
  - honours temperature and top_p;
  - top_k and penalties: same as Flash-Lite;
  - accepts **only minimal/high reasoning** (the layer maps low→minimal, medium→high, and records it in
    `settings_adjusted`);
  - writes `<thought>…</thought>` inline on the compatible path;
  - slow, with frequent 500 errors.
- `stop=["Observation:"]` works on every model: the graph uses it so the model can't invent observations.
- `gemini-2.5-flash-lite` → 404 "no longer available to new users".

## 6. How the user likes to work

- Stage by stage: a test gate, a short summary, then the user says "push stage N and build stage N+1". Commit
  after each stage; **push only when asked**. Before pushing, scan the history:
  `git log --all -p | grep -E "AIza|sk-[A-Za-z0-9_-]{8}|AQ\.[A-Za-z0-9_-]{6}"` should only find test/README
  pattern lines.
- Explicit, concrete steps. Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Check the requirements (PDF → mechanism → evidence) **before** choosing models or planning; probe candidate
  models instead of trusting docs.
- Quota: Flash-Lite 500 requests/day, resetting around 10:00 Beirut. On 2026-10-12 about 120 were used. Estimate
  requests before live runs. `docs/rate_limits.md` still needs Gemma's real limits from AI Studio.
