# Results: v_qwen

18 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 | distinct_2_rep |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sami-temp-0.0 | qwen3:4b-instruct | sami | 9 | 0 | 0 | 0.0 | 1.0 | 0 | 1 | 9 | 26.91 | 145.7 | 0.29 | 0.309 |
| sami-temp-1.4 | qwen3:4b-instruct | sami | 9 | 0 | 0 | 0.0 | 1.0 | 0 | 1 | 9 | 30.81 | 153.1 | 0.789 | 0.835 |

## Success by category

| category | sami-temp-0.0 | sami-temp-1.4 |
|---|---|---|
| planning | 0/9 | 0/9 |

## Cases × configurations (passed / runs)

| case | sami-temp-0.0 | sami-temp-1.4 |
|---|---|---|
| C1 | 0/3 | 0/3 |
| C2 | 0/3 | 0/3 |
| C3 | 0/3 | 0/3 |

## Most common failure reasons

- sami-temp-0.0: missing tool: get_package or search_business_docs ×9
- sami-temp-1.4: missing tool: get_package or search_business_docs ×9
- sami-temp-0.0: answer lacks /\b60\b/ ×3
- sami-temp-1.4: answer lacks /\b60\b/ ×3
