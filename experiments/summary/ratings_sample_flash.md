# Results: ratings_sample_flash

30 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| milo-flash | gemini-3.5-flash-lite | milo | 10 | 0 | 0.9 |  | 1.0 | 0.2 | 2.4 | 29 | 13.52 | 32.2 | 0.913 |
| nora-flash | gemini-3.5-flash-lite | nora | 10 | 0 | 1 |  | 1.0 | 0.5 | 2.7 | 34 | 3.97 | 30 | 0.881 |
| sami-flash | gemini-3.5-flash-lite | sami | 10 | 0 | 0.9 |  | 1.0 | 0.2 | 2.3 | 25 | 2.08 | 62.1 | 0.91 |

## Success by category

| category | milo-flash | nora-flash | sami-flash |
|---|---|---|---|
| fact | 1/1 | 1/1 | 1/1 |
| feedback | 1/1 | 1/1 | 0/1 |
| greeting | 1/1 | 1/1 | 1/1 |
| language | 1/1 | 1/1 | 1/1 |
| lead | 0/1 | 1/1 | 1/1 |
| no_answer | 1/1 | 1/1 | 1/1 |
| not_offered | 1/1 | 1/1 | 1/1 |
| planning | 1/1 | 1/1 | 1/1 |
| price | 2/2 | 2/2 | 2/2 |

## Cases × configurations (passed / runs)

| case | milo-flash | nora-flash | sami-flash |
|---|---|---|---|
| F2 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 |
| P3 | 1/1 | 1/1 | 1/1 |
| N1 | 1/1 | 1/1 | 1/1 |
| O1 | 1/1 | 1/1 | 1/1 |
| L1 | 0/1 | 1/1 | 1/1 |
| B1 | 1/1 | 1/1 | 0/1 |
| G1 | 1/1 | 1/1 | 1/1 |
| A1 | 1/1 | 1/1 | 1/1 |
| C1 | 1/1 | 1/1 | 1/1 |

## Most common failure reasons

- milo-flash: answer lacks /email/ ×1
- sami-flash: missing tool: record_feedback ×1
- sami-flash: answer lacks /thank/ ×1
