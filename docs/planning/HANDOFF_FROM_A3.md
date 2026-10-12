# Handoff: Assignment 3 → Assignment 4

Written at the end of the Assignment 3 session (2026-10-10) so a new session can continue without that conversation.
**New session: read this file and `C4 - Agent Personas  Thinking Mechanisms.pdf` first.**
(The PDF's text extracts with pypdf; the PDF image viewer isn't available on this machine.)

## 1. What already exists

| | |
|---|---|
| A4 repo (local) | `C:\Graduate Studies\Agentic Systems\Assignment 4\echonest_react_agent` |
| A4 repo (GitHub, private) | https://github.com/Mustafa-Abbara/echonest_react_agent (`main` + tag `a4-start`) |
| Starting point | A full copy of the A3 repo **with its history**. Tag `a4-start` = commit `d93c255`, the last A3 commit at branch time |
| Environment | `.venv` in the repo (Python 3.12.6, openai 3.26.1, gradio 6.29.1, pypdf 6.19.0, python-dotenv 1.2.4, plus ipykernel, fpdf2, nbclient, nbformat). Jupyter kernel **"Python (echonest_react)"** |
| `.env` | Copied from A3 (`GEMINI_API_KEY=...`, key starts with `AQ.`), git-ignored |
| Tests | `tests/test_setup.py`, `test_business_files.py`, `test_tools.py`, `test_app_export.py` all pass in the A4 copy |
| A3 repo | `C:\Graduate Studies\Agentic Systems\Assignment 3\business_bot` → github.com/Mustafa-Abbara/business_bot. **Never commit A4 work there.** |

**Still open for A3 (not A4's job):** the user records the demo video; then the video link goes in the A3 README and
the A3 tag `a3-final` is moved to that commit (`git tag -fa a3-final -m "Assignment 3 as submitted"`, then
`git push origin a3-final --force`). The A3 repo is private: it must become public, or the grader must be invited.

## 2. The A3 project in one paragraph
**EchoNest**, a fictional digital-memory studio (Memory Capsule $79, Event Story $149, Life Timeline $299, Legacy
Edition $499, Corporate Story with no fixed price). The agent is **Milo, the Memory Concierge**. Knowledge lives in
`me/about_business.pdf` + `me/business_summary.txt`, with deliberate information boundaries:
- some facts only in the PDF, some only in the summary;
- a "not currently offered" list (film restoration, physical photo restoration, videography, deleted-file recovery);
- unknown topics mentioned nowhere (gift cards, discounts, albums, rush orders, a "Platinum" tier).

**Notebook `business_agent.ipynb`, sections 1–12:**
- setup with `call_llm()`;
- 🎭 PERSONA and 📏 INSTRUCTIONS (12 rules);
- tools `record_customer_interest(email, name, message)` and `record_feedback(question)`, with MCP-style schemas;
- a hybrid router (LLM + keyword fallback, 97% on 39 cases);
- a tool-call loop using **native function calling** (`run_agent` + `safe_execute`);
- the orchestrator `respond()`, with Gradio 6 history conversion;
- a reflection bonus;
- Gradio.

`app.py` is **generated** from the notebook by `scripts/export_app.py` (and has a ZeroGPU placeholder). The README
documents everything, including "What testing taught us".

## 3. Assignment 4 requirements (summary of the PDF)
Extend the A3 chatbot into a **ReAct agent** built in **one framework**: LangGraph, CrewAI, AutoGen or the OpenAI
Agents SDK. **No prebuilt executors** (e.g. LangChain AgentExecutor); the ReAct loop must be implemented manually.

| Item | Points |
|---|---|
| Use-case summary + write-up (goal, audience, tools, constraints; A3's scenario may be reused) | 10 |
| ReAct logic implemented by hand: system prompt with tool descriptions, **detect when the model suggests an action**, run the tool, return the observation, continue the loop, parse the final answer | 30 |
| Persona design: **≥ 2 personas**, each defined by prompt traits (tone, vocabulary, style, values) **and** matching LLM settings | 20 |
| Settings experiments: temperature, top-p, top-k, frequency/presence penalty, max tokens, model; plus prompt experiments: with/without chain-of-thought, zero-shot vs few-shot, system prompt vs in-message instructions. **Log and compare** | 15 |
| Instructions block: one purpose per instruction, explicit inputs and outputs with their format, **at least one worked example inside it**, no conflict with the persona | 10 |
| Creativity, clarity, reflection (5 questions: best persona, best prompt and config, reasoning and tool use, did instructions change behavior, biggest challenges) | 15 |

## 4. Recommended plan (agreed in the A3 session; the user hasn't committed to details yet)
- **Framework: LangGraph.** The ReAct loop becomes an explicit graph (reason → act → observe → reason, or → answer),
  with a conditional edge that detects actions. **Do not use `langgraph.prebuilt.create_react_agent`**: it's a
  prebuilt executor.
- **Text-based ReAct** (`Thought:` / `Action:` / `Observation:` / `Final Answer:`), parsed by our own code, so that
  action detection and answer parsing are visible and gradable, and chain-of-thought can be switched on and off.
  Contrast this with A3's native function calling in the reflection.
- **Make tools necessary:** keep the documents **out** of the system prompt and add lookup tools
  (e.g. `search_business_docs(query)`, `get_package(name)`, maybe `estimate_quote(...)`), plus the two A3 tools. In
  A3, the documents were in the prompt, so few lookups were needed.
- **Three personas with matching settings**, for example: Warm Concierge (temperature ~0.7), Precise Specialist
  (temperature ~0.1, low top-p), Creative Storyteller (temperature ~1.0, presence penalty).
- **Reuse A3's labelled tests** (`tests/knowledge_checks.json`, `tests/router_cases.json`, the P1–P8 / T1–T8 / M /
  R cases in the notebook) as the **scoring set** for comparing personas and settings. Log every run to CSV/JSONL.
- **First task:** verify which settings Gemini's OpenAI-compatible endpoint actually honours (top_k? frequency and
  presence penalty? max_tokens? temperature 0–2?). If some aren't supported, decide between the native `google-genai`
  SDK and documenting the limitation.
- Build in stages with a test gate per stage, like the A3 roadmap
  (`C:\Graduate Studies\Agentic Systems\Assignment 3\Roadmap.md`).

## 5. Lessons from A3 that matter for A4
- **Quota:** `gemini-3.5-flash-lite` free tier = **500 requests/day per model and project** (resets around 10:00
  Beirut), ~15 per minute. A3's full notebook run cost ~95 requests. An A4 experiment grid can be large: estimate
  requests before running it, and spread it over days or use subsets. The user ran out once in A3; track usage.
- **Gemini returns HTTP 503 ("high demand") often.** A3's `call_llm()` retries 5xx twice, 429 once, paces requests
  under the per-minute limit, and stops immediately when the *daily* quota is gone (it parses "retry in 18h…").
  Reuse it.
- **Thought signatures:** with native tool calling on Gemini's OpenAI endpoint, the assistant message must be
  appended **exactly as returned**. This doesn't apply to text-based ReAct, but does if the framework uses native
  tools.
- **Prompt findings:**
  - Flash-Lite needed explicit "**first** call `record_feedback`, then reply" wording.
  - A rule forbidding claimed actions without a tool call was necessary.
  - Grounding rules must say "questions **about EchoNest**", or conversation facts are treated as unknown.
  - Language examples in rules primed the wrong language ("English gets English…" fixed it).
  - Reflection needs the full history and must "report only clear violations".
- **Tests:** keep tests offline where possible; redirect logs to a temporary folder in tests
  (`temporary_logs()`); LLM tests are probabilistic, so repeat the important ones.
- **Windows specifics:**
  - Running Python with `PYTHONIOENCODING=utf-8` avoids emoji print crashes.
  - Avoid very deep folder paths: pip hit the 260-character path limit in a deep temp folder.
  - Pick the notebook kernel explicitly; `ModuleNotFoundError: openai` means the wrong kernel.
- **Hugging Face (if A4 is deployed):** free Gradio Spaces run on ZeroGPU and need a `@spaces.GPU` function
  (A3 uses a never-called placeholder). Logs inside a Space are lost on restart.

## 6. How the user likes to work
- **Stage by stage**, with a test gate and a short summary after each stage. The user says "push stage N and build
  stage N+1"; commit after each stage, and **push only when asked**.
- Wants **explicit, concrete step-by-step instructions** ("no vague steps"), e.g. exact clicks and commands.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never put the key in git: scan history before each push (`git log --all -p | grep -E "AIza|sk-|AQ\."` should only
  find the test/README pattern lines).
