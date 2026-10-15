# Experiment notes (Stage 8 onward)

Running notes: what we noticed while running the experiments, written down as it happened. The summaries
(`experiments/summary/`) hold the numbers; this file holds the surprises and the decisions, for the reflection
(PDF 2.5).

## 2026-10-15: setting up Stage 8

- **The eval set was frozen before Stage 8** with two creative planning cases added (C2 interview questions, C3
  chapter ideas) for the variance plan. Every Stage 8 row carries the case-file hash.
- **Gemma smoke test (5 runs):** about 60 s per call on the free tier (48 to 115 s), one run lost to "temporarily
  unavailable" even after the retries, and one empty reply. That empty reply exposed a bug in our own `recover`
  node: it wrote "(empty reply)" into the transcript as the model's previous text, and Gemma copied it back as its
  answer. Fixed (the correction now just says the reply was empty; `test_two_empty_replies_get_two_corrections`), and
  the 5 smoke rows were discarded because they ran under the old behaviour.
- **Scope decision:** at about 60 s per call, the planned Gemma programme (192 runs) would take 8+ hours. qwen
  already honours every setting, and Flash-Lite vs qwen already gives two model types, so Gemma runs the personas
  on the core set and a temperature sweep only (72 runs): a third model type and a hosted check of the temperature
  effect.
- **qwen smoke test (9 runs, about 14 s per run):** two behaviours we will see again. (1) On "Do you sell gift
  cards?" Milo and Sami called `record_feedback` without searching first: they assumed the answer instead of looking
  it up (rule 1). Nora searched first. (2) On "Hi!" Nora and Sami answered in plain prose without "Final Answer:",
  twice, so the turn ended as a format fallback: the customer still gets a good greeting, but the format rule failed.
- **Controls:** `s_flash` includes temperature 0.0 and `s_gemma` dropped its top_k control. On a model that ignores
  a setting the layer does not send it, so that "config" is the baseline again: its difference from `base` is the
  run-to-run noise floor, which every other difference must beat.

## 2026-10-15: Stage 8 results (summaries in `experiments/summary/`)

**Coverage.** Done: personas on Flash-Lite and qwen (full set, 102 runs each), the qwen settings sweep (144), the
Flash-Lite sweep (67 of 72: the last 5 runs of the temperature control wait for the quota reset), the qwen variance
plan (18). **Gemma was dropped:** only 5 of 19 runs succeeded (Google's free endpoint answered "temporarily
unavailable" for over an hour; finished runs took 100 to 170 s per turn), and the assignment does not need it: "model
type" is one setting to vary, which Flash-Lite vs qwen already covers, and qwen honours temperature and top_p live.
Its plans and rows were removed; Gemma stays in the Stage 0 probe evidence.

**1. Model type matters most** (`model_type_core.md`, Flash-Lite vs qwen on the same 12 core cases): Flash-Lite 92 to 100% task success,
qwen3:4b-instruct 67 to 83%. On the full set: Flash-Lite 85 to 94%, qwen 59 to 62%. qwen's main failure is
grounding: it answers from its own assumptions instead of looking facts up (`missing tool` is its top failure for
every persona, 6 to 8 times each), and it never answered Arabic or French in the customer's language (0/2).

**2. Personas** (`personas_by_model.md`): on Flash-Lite, Milo 94%, Sami 88%, Nora 85%; on qwen, Milo and Nora 62%,
Sami 59%. Differences of 1 to 3 cases out of 34 are small. The **voices differ clearly on both models**: Sami's
answers are twice as long (58 / 51 words vs 27 to 32), Nora's the shortest. Because the length gap is the same on
Flash-Lite (which ignores temperature, top_p and top_k and rejects the penalties) as on qwen (which honours them
all), the persona's **prompt traits** set the voice and length; the sampling settings add variety on top: Sami's
lexical variety (distinct-2) beats Nora's by 0.02 on Flash-Lite but by 0.09 on qwen, where her temperature 1.1 vs 0.1
is actually applied. Nora's weak spot is format: most corrections on Flash-Lite (0.53 per turn).

**3. Settings, one at a time on qwen** (`s_qwen.md`, baseline Milo 67%):
- temperature 0.0, top_p 0.3 and top_k 1 gave **identical** runs (83%, same requests, words and variety): all three
  collapse sampling to the single most likely token, so they are three routes to greedy decoding.
- temperature 1.4: the lowest score (58%).
- frequency penalty 1.0: the longest answers (27 vs 21 words) with the lowest variety among the penalty runs;
  presence penalty 1.0: 75%. Penalties barely moved task success.
- max_tokens 150 vs 600: no effect on success: answers are about 22 words, far below either cap.
- Noise: 12 cases × 1 repeat, so one case is 8 points. The `temp-0.0-control` on Flash-Lite (a request identical to
  the baseline, because Flash-Lite drops temperature) scored 7/7 vs the baseline's 11/12: differences of one case
  are noise.

**4. Settings on Flash-Lite** (`s_flash.md`, baseline 92%): max_tokens 150 / 600 and reasoning minimal: 92 to 100%.
**reasoning high: 42%**, with 0.75 format corrections per turn, 18-word answers and 13 s per turn (vs 2.6 s). The
traces show why: the hidden thinking used about 380 of the 400 max_tokens, so the visible reply was cut off
(`finish: length`) or empty. It is an interaction, not "more reasoning is worse": one-factor-at-a-time kept
max_tokens at 400. Follow-up config `reasoning-high-1200` (high reasoning, max_tokens 1200) runs after the reset.

**5. Temperature and variety** (`v_qwen.md`, Sami, 3 planning cases × 3 repeats): variety across repeats of the
same question was 0.31 at temperature 0.0 and 0.84 at 1.4: at 0.0 the repeats are near copies, at 1.4 they are new
wording each time. Answers were long (146 to 153 words) at both. But **0/18 passed**: qwen wrote every plan without
looking up the package first (one step, no tool), so the plans could not respect the package limits. Temperature
changed the wording, not the grounding.
