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
Flash-Lite sweep (72, finished on 2026-10-16 with the follow-up below), the qwen variance
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
max_tokens at 400. **Follow-up (2026-10-16): high reasoning with max_tokens 1200 scored 12/12**, so the
failure was the token budget, not the reasoning. The temperature control (a request identical to the baseline)
finished 12/12 vs the baseline's 11/12: one case is the noise floor.

**5. Temperature and variety** (`v_qwen.md`, Sami, 3 planning cases × 3 repeats): variety across repeats of the
same question was 0.31 at temperature 0.0 and 0.84 at 1.4: at 0.0 the repeats are near copies, at 1.4 they are new
wording each time. Answers were long (146 to 153 words) at both. But **0/18 passed**: qwen wrote every plan without
looking up the package first (one step, no tool), so the plans could not respect the package limits. Temperature
changed the wording, not the grounding.

## 2026-10-16: Stage 9, prompt engineering (`prompt_flash.md`, Milo on Flash-Lite, core set)

- **Quota:** Google's 429 said "retry in 20h18m", but the daily quota came back at about 10:00 Beirut (midnight
  Pacific), as the docs say: the retry delay in the error is not the reset time.
- One factor at a time from the shipped default (Thought lines, one worked example, instructions in the system prompt):

  | variant | success | format corrections per turn | requests |
  |---|---|---|---|
  | default | 12/12 | 0.08 | 30 |
  | no CoT (no Thought lines; hidden reasoning unchanged) | 10/12 | 0 | 22 |
  | zero-shot (no worked example) | 12/12 | 0.33 | 36 |
  | few-shot (3 examples) | 12/12 | 0.33 | 33 |
  | in-message (instructions in front of the customer's message) | 12/12 | 0.08 | 29 |

- **Chain-of-thought:** the only factor that cost success. Without the Thought line Milo skipped the lookup twice
  (`missing tool: search_business_docs` ×2): fewer steps (1.83 vs 2.17) and fewer requests, but less grounding.
  Writing "what I know and what I need next" seems to be what makes the model check before answering.
- **Shots:** zero-shot and few-shot reached the same success but needed 4× the format corrections of the single
  example. The traces show these were not wrong formats but Flash-Lite's empty "malformed" replies (4 each vs 1 for
  the default; few-shot also had one reply cut off at max_tokens), the same quirk Stage 5 found to depend on the
  prompt's structure (without a worked example, 3 of 6 identical requests came back empty). One example was the
  sweet spot, which is the shipped block.
- **Placement:** tied at the ceiling on the core set, so the confirmation run repeated both on the full set.

## 2026-10-16: Stage 9 confirmation (`prompt_confirm.md`, Milo on Flash-Lite, full set of 34)

| placement | success | format corrections per turn | requests | latency per turn |
|---|---|---|---|---|
| system prompt (shipped default) | 31/34 (91%) | 0.32 | 98 | 13.5 s |
| in-message | 32/34 (94%) | 0.03 | 75 | 9.3 s |

- The best value of every factor on the core set was the shipped default, so the confirmation run is the default
  itself: 91% on the full set (94% for the same configuration in Stage 8: one case apart, i.e. noise).
- **In-message placement made Flash-Lite far more reliable:** 1 format correction in 34 turns instead of 11, so 23%
  fewer requests and faster turns, with the same success. The instructions right before the customer's message
  seem to keep the text format in front of the model, so it stops attempting native tool calls (the empty
  "malformed" replies).
- **Decision: keep the system prompt.** PDF 2.2 asks for "a system prompt defining agent behavior and available
  tools", and success is the same. In-message is the better choice for cost and latency on this model: a trade-off
  for the reflection, not a change to ship.

## 2026-10-16: human ratings (`experiments/ratings/ratings_sample_flash.csv`)

30 answers from `p_flash` (10 cases × 3 personas), rated 1–5 by the author for helpfulness and persona fit.

| persona | helpfulness | persona fit |
|---|---|---|
| Milo | 4.6 | 4.7 |
| Nora | 4.4 | 4.9 |
| Sami | 4.5 | 3.9 |

- **Milo** was the most helpful, matching his top automatic score. One answer was cut mid-sentence
  (`p_flash:milo-flash:L1:0`, rated 3/4): the trace shows `finish: length`, with his *low* reasoning using 309 of his 400
  max_tokens. It is the Stage 8 reasoning/max_tokens interaction again, at a lower level: 400 is too tight for Milo
  (about 800 would be safer). Not changed after the fact; reported.
- **Nora** was the most in character (4.9), but precise turned cold once: a thank-you got two flat sentences (3/4).
  On "help me plan" she gave only specs and a contact request (3/5).
- **Sami** was the least consistent in character (3.9): strong on her own task (the graduation plan was rated the best
  answer in the set, 5/5: the photo split sums to the 60-photo limit and uses all 3 recordings), but on plain price
  questions she sounded like Nora (2/5). A persona's voice is weakest outside its own focus.
- The ratings confirm two automatic failures: Nora and Sami declined film restoration without logging the demand.

## 2026-10-16: final run on the submission code (Stage 12)

- **G1–G6: 12/12** (G1, G2, G5 three times each; `docs/evidence/stage12_final_graph.jsonl`).
- **M1–M2: 5/6** (`docs/evidence/stage12_final_chat.jsonl`). All three personas remembered the name (M1); Milo and
  Nora handled the 3-turn lead perfectly. **Sami failed M2:** to "I'd like a Memory Capsule for my sister's
  graduation" he wrote a full plan (60 photos, 3 recordings, correct) instead of asking for name and email, then on
  "My name is Rania" called `record_customer_interest` without an email (the tool rejected it and nothing was saved)
  before asking for it; turn 3 saved the lead correctly. He passed the same test in Stage 6. It is the persona vs
  rule tension the human ratings showed (a persona's voice is strongest on its own task), appearing run to run;
  reported, not tuned after the experiments.
- **UI check:** in the Gradio app two first requests stalled on the network and the 120 s timeout plus retry (the
  Stage 4 fix) recovered both without an error; screenshots `docs/screenshots/12`–`14` (Milo: NO_MATCH then
  `record_feedback`; Sami: the lookup, then a plan whose photo split sums to the 60-photo limit).
