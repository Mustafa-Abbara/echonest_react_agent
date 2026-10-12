# Stage 0 — What the free Gemini API really does with each LLM setting

Measured on 2026-10-12 with `scripts/probe_settings.py` (about 180 requests in total). The full table is in
[settings_support.md](settings_support.md); every request and reply is in [probe/](probe/).

## Method

A setting the API **accepts** (HTTP 200) is not necessarily a setting the model **honours**. For each setting the
probe sends a valid value, then runs an **effect test** whose result can be counted:

| Setting | Test | Honoured if |
|---|---|---|
| temperature / top_p / top_k | 5 × "write 8 random words" at 0.0 / 0.01 / 1 vs 5 × the default | the answers collapse to ≤ 2 distinct (control: 5/5 distinct) |
| frequency / presence penalty | "write *echo* 50 times" at 1.9 vs no penalty | the count drops below 60 % of the control |
| max_tokens | 16 tokens for "count to 200" | `finish_reason=length` |
| stop | `["7"]` on "count to 10", `["Observation:"]` on a ReAct trace | the output ends before the stop string |
| seed | same seed twice, two seeds | identical pairs |
| reasoning_effort | `minimal` vs `high` on a small marble puzzle | clearly more hidden reasoning tokens |

An out-of-range value is also sent: an HTTP 400 there shows the server reads the field, even when it then ignores
it. Two request paths were probed for each model: Gemini's **OpenAI-compatible endpoint** (`gemini`) and Google's
**native `google-genai` SDK** (`gemini_native`).

## Results

| Setting | gemini-3.5-flash-lite | gemma-4-26b-a4b-it |
|---|---|---|
| temperature, top_p | **ignored** (range-checked, then no effect: 5/5 distinct at 0.0 and at 0.01) | **honoured** (1/5 distinct) |
| top_k | rejected (compat: "Unknown name") · ignored (native) | rejected (compat) · ignored (native) |
| frequency / presence penalty | **rejected**: "Penalty is not enabled for this model" | **rejected** (same message) |
| max_tokens | honoured | honoured, but **thinking can use the whole budget**: at 16 tokens the answer was empty |
| stop | honoured, including `["Observation:"]` | honoured (it applies to the answer, not to the inline thought) |
| seed | rejected (compat) · **honoured (native)** | rejected (compat) · **honoured (native)** |
| reasoning_effort | honoured: 0 vs ~450 hidden tokens; `minimal` got the puzzle **wrong** (9–10), `high` right (11) | honoured: 0 vs ~300–435 tokens, 0.8 s vs 7–10 s; `minimal` wrong (8), `high` right |
| system role | yes | yes |
| n > 1 | no ("Multiple candidates is not enabled") | no |
| reasoning levels accepted | minimal, low, medium, high | **only minimal and high** ("Thinking level is not supported for this model" for low/medium, both paths) |

Other observations:
- On the compatible endpoint **Gemma writes its thinking inline**: `<thought>…</thought>answer`. The agent's
  parser must strip it before looking for `Action:` / `Final Answer:`. The native SDK returns thoughts as separate
  parts, so the text is clean.
- Gemma is slow (5–10 s per reply with thinking) and returned HTTP 500 several times; the retries handled it.
- `gemini-2.5-flash-lite` is listed by the API but returns 404 "no longer available to new users".
- This matches Google's documentation that general-use Gemini 3.x models ignore temperature/top-p/top-k.

## Decision (Roadmap Stage 0, step 8)

1. **Development and demo model: `gemini-3.5-flash-lite`** (fast, 500 requests/day). On it, the persona knobs
   that really change behaviour are `reasoning_effort`, `max_tokens`, `stop` and the model choice.
2. **Sampling experiments (temperature, top_p) run on `gemma-4-26b-a4b-it`**, the free model that honours them.
   It is also the second model for the "model type" comparison.
3. **Personas still declare their full intended settings** (temperature, top_p, top_k, penalties). The LLM layer
   reads the capability file and sends only what the active model accepts, logging what it dropped. So when a model
   that supports penalties or top_k is configured (e.g. an OpenAI key), they take effect with no code change.
4. **top_k and the penalties are honoured by no free model on either path**: this is reported as a finding in the
   experiments instead of being swept.
5. **Add the native backend (`google_genai`) in Stage 1**, because it honours `seed` (reproducible experiment
   runs) and returns Gemma's thoughts separately. The OpenAI-compatible backend stays, because it is the path to
   OpenAI and other providers. Which one is the default for Gemini is a one-line choice in `.env`
   (`LLM_PROVIDER=gemini` or `gemini_native`).
6. **Gemma needs head-room in `max_tokens`** (or `reasoning_effort=minimal`), or its thinking eats the answer.
7. **Reasoning levels a model doesn't accept are mapped to the nearest accepted one** (Gemma: low → minimal,
   medium → high), and every result records the change in `settings_adjusted`. A persona's "low" thinking still
   runs on Gemma. Found by the Stage 1 switch drill; the probe now records `levels_accepted`.

## Re-running

```powershell
python scripts\probe_settings.py --provider gemini --list-models
python scripts\probe_settings.py --provider gemini --model <id> --dry-run
python scripts\probe_settings.py --provider gemini --model <id>            # or --quick, or --only stop,seed
python scripts\probe_settings.py --report                                  # regenerates settings_support.md
```
