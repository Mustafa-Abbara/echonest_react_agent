# Results: prompt_flash

60 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| default | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.08 | 2.17 | 30 | 13.62 | 29.4 | 0.868 |
| no-cot | gemini-3.5-flash-lite | milo | 12 | 0 | 0.833 |  | 1.0 | 0 | 1.83 | 22 | 10.15 | 33.7 | 0.839 |
| zero-shot | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.33 | 2.42 | 36 | 12.38 | 31.9 | 0.887 |
| few-shot | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.33 | 2.42 | 33 | 17.25 | 27.6 | 0.919 |
| in-message | gemini-3.5-flash-lite | milo | 12 | 0 | 1 |  | 1.0 | 0.08 | 2.25 | 29 | 11.93 | 34.8 | 0.888 |

## Success by category

| category | default | no-cot | zero-shot | few-shot | in-message |
|---|---|---|---|---|---|
| fact | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| feedback | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| greeting | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| lead | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| no_answer | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| not_offered | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| price | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |

## Cases × configurations (passed / runs)

| case | default | no-cot | zero-shot | few-shot | in-message |
|---|---|---|---|---|---|
| F1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| N1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| O1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| L1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| L2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| B2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| G1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |

## Most common failure reasons

- no-cot: missing tool: search_business_docs ×2
- no-cot: answer lacks /not|don't|do not/ ×1
