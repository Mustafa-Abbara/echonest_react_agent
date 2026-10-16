# Results: s_flash

84 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | gemini-3.5-flash-lite | milo | 12 | 0 | 0.917 |  | 1.0 | 0.33 | 2.5 | 34 | 2.6 | 29.8 | 0.858 |
| max_tokens-150 | gemini-3.5-flash-lite | milo | 12 | 0 | 0.917 |  | 1.0 | 0.33 | 2.42 | 34 | 2.8 | 29.2 | 0.897 |
| max_tokens-600 | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.25 | 2.42 | 34 | 4.5 | 29.5 | 0.885 |
| reasoning-minimal | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.42 | 2.5 | 36 | 6.5 | 32 | 0.866 |
| reasoning-high | gemini-3.5-flash-lite | milo | 12 | 0 | 0.417 |  | 1.0 | 0.75 | 2.75 | 38 | 13.14 | 18.3 | 0.925 |
| temp-0.0-control | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.17 | 2.33 | 32 | 12.22 | 32.2 | 0.878 |
| reasoning-high-1200 | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.25 | 2.42 | 33 | 15.26 | 35.2 | 0.852 |

## Success by category

| category | base | max_tokens-150 | max_tokens-600 | reasoning-minimal | reasoning-high | temp-0.0-control | reasoning-high-1200 |
|---|---|---|---|---|---|---|---|
| fact | 3/3 | 3/3 | 3/3 | 3/3 | 1/3 | 3/3 | 3/3 |
| feedback | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| greeting | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| lead | 1/2 | 2/2 | 2/2 | 2/2 | 0/2 | 2/2 | 2/2 |
| no_answer | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| not_offered | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| price | 3/3 | 2/3 | 3/3 | 3/3 | 2/3 | 3/3 | 3/3 |

## Cases × configurations (passed / runs)

| case | base | max_tokens-150 | max_tokens-600 | reasoning-minimal | reasoning-high | temp-0.0-control | reasoning-high-1200 |
|---|---|---|---|---|---|---|---|
| F1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| P1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P3 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| N1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| O1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| L1 | 0/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| L2 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| B2 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| G1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |

## Most common failure reasons

- reasoning-high: outcome: format_fallback ×6
- base: answer lacks /email/ ×1
- max_tokens-150: answer lacks /quot|consult/ ×1
- reasoning-high: answer lacks /\b60\b/ ×1
- reasoning-high: answer lacks /50\s*%|50 percent|half/ ×1
- reasoning-high: answer lacks /quot|consult/ ×1
- reasoning-high: answer lacks /not|don't|do not/ ×1
- reasoning-high: answer lacks /email/ ×1
- reasoning-high: missing tool: record_customer_interest ×1
