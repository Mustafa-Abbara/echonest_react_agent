# Free-tier rate limits (Gemini API project)

Limits apply **per Google Cloud project, not per key**, and daily quotas reset at midnight Pacific time
(about 10:00 Beirut). Google changes them often, so read them from AI Studio:
**aistudio.google.com → Dashboard → Usage & limits (Rate limits)**, with this key's project selected.

The pacing and quota stops in `scripts/probe_settings.py` (and later the LLM layer) read `rpm` / `rpd` from
`config/models.json`; update that file when the numbers below change. `null` = unknown → paced at 10/min.

| Model | RPM | RPD | Source / date |
|---|---|---|---|
| `gemini-3.5-flash-lite` | 15 | 500 | A3 measurement (429 quota fields), 2026-09; **confirm in AI Studio** |
| `gemma-4-26b-a4b-it` | _fill in_ | _fill in_ | unofficial report says 1,500 RPD; **confirm in AI Studio** |
| `gemma-4-31b-it` | _fill in_ | _fill in_ | **confirm in AI Studio** |
| `gemini-3.6-flash` / `3.7` / `3.8` | _fill in_ | _fill in_ | A3: Flash models about 20 RPD on the free tier |

Not usable with this key: `gemini-2.5-flash-lite` is listed by `--list-models` but returns
HTTP 404 "no longer available to new users" (checked 2026-10-12).
