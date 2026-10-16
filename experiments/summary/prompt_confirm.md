# Results: prompt_confirm

68 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| default-full | gemini-3.5-flash-lite | milo | 34 | 0 | 0.912 |  | 0.971 | 0.32 | 2.44 | 98 | 13.46 | 30.0 | 0.754 |
| in-message-full | gemini-3.5-flash-lite | milo | 34 | 0 | 0.941 |  | 0.971 | 0.03 | 2.12 | 75 | 9.31 | 31.6 | 0.724 |

## Success by category

| category | default-full | in-message-full |
|---|---|---|
| fact | 9/10 | 10/10 |
| feedback | 2/2 | 2/2 |
| greeting | 2/2 | 2/2 |
| language | 1/2 | 2/2 |
| lead | 4/4 | 4/4 |
| memory | 1/1 | 1/1 |
| no_answer | 3/3 | 3/3 |
| not_offered | 3/3 | 2/3 |
| planning | 2/3 | 2/3 |
| price | 3/3 | 3/3 |
| safety | 1/1 | 1/1 |

## Cases × configurations (passed / runs)

| case | default-full | in-message-full |
|---|---|---|
| F1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 |
| F4 | 1/1 | 1/1 |
| F5 | 1/1 | 1/1 |
| F6 | 1/1 | 1/1 |
| F7 | 0/1 | 1/1 |
| F8 | 1/1 | 1/1 |
| F9 | 1/1 | 1/1 |
| F10 | 1/1 | 1/1 |
| P1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 |
| P3 | 1/1 | 1/1 |
| N1 | 1/1 | 1/1 |
| N2 | 1/1 | 1/1 |
| N3 | 1/1 | 1/1 |
| O1 | 1/1 | 1/1 |
| O2 | 1/1 | 0/1 |
| O3 | 1/1 | 1/1 |
| L1 | 1/1 | 1/1 |
| L2 | 1/1 | 1/1 |
| L3 | 1/1 | 1/1 |
| L4 | 1/1 | 1/1 |
| B1 | 1/1 | 1/1 |
| B2 | 1/1 | 1/1 |
| G1 | 1/1 | 1/1 |
| G2 | 1/1 | 1/1 |
| M1 | 1/1 | 1/1 |
| A1 | 1/1 | 1/1 |
| A2 | 0/1 | 1/1 |
| S1 | 1/1 | 1/1 |
| C1 | 1/1 | 1/1 |
| C2 | 0/1 | 0/1 |
| C3 | 1/1 | 1/1 |

## Most common failure reasons

- default-full: answer lacks /2023/ ×1
- default-full: answer lacks /5\s*(à|a|-|–)\s*10/ ×1
- default-full: answer lacks /\?/ ×1
- in-message-full: missing tool: search_business_docs ×1
- in-message-full: answer lacks /\?/ ×1
