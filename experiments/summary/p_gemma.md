# Results: p_gemma

19 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| milo-gemma | gemma-4-26b-a4b-it | milo | 12 | 8 | 1 |  | 1.0 | 0.25 | 1.75 | 7 | 103.92 | 31.2 | 0.96 |
| nora-gemma | gemma-4-26b-a4b-it | nora | 7 | 6 | 1 |  | 1.0 | 0 | 2 | 2 | 165.88 | 22 | 0.895 |

## Success by category

| category | milo-gemma | nora-gemma |
|---|---|---|
| fact |  | 1/1 |
| feedback | 1/1 |  |
| greeting | 1/1 |  |
| lead | 2/2 |  |

## Cases × configurations (passed / runs)

| case | milo-gemma | nora-gemma |
|---|---|---|
| F1 | 0/1 (1 error) | 1/1 |
| F2 | 0/1 (1 error) | 0/1 (1 error) |
| F3 | 0/1 (1 error) | 0/1 (1 error) |
| P1 | 0/1 (1 error) | 0/1 (1 error) |
| P2 | 0/1 (1 error) | 0/1 (1 error) |
| P3 | 0/1 (1 error) | 0/1 (1 error) |
| N1 | 0/1 (1 error) | 0/1 (1 error) |
| O1 | 0/1 (1 error) |  |
| L1 | 1/1 |  |
| L2 | 1/1 |  |
| B2 | 1/1 |  |
| G1 | 1/1 |  |
