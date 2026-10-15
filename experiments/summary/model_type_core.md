# Results: model_type_core

72 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| milo-flash | gemini-3.5-flash-lite | milo | 12 | 0 | 0.917 |  | 1.0 | 0.25 | 2.42 | 36 | 12.61 | 31.1 | 0.876 |
| nora-flash | gemini-3.5-flash-lite | nora | 12 | 0 | 1 |  | 1.0 | 0.42 | 2.67 | 39 | 3.6 | 31.7 | 0.819 |
| sami-flash | gemini-3.5-flash-lite | sami | 12 | 0 | 0.917 |  | 1.0 | 0.17 | 2.33 | 30 | 2.12 | 56.6 | 0.858 |
| milo-qwen | qwen3:4b-instruct | milo | 12 | 0 | 0.833 |  | 1.0 | 0.17 | 2.08 | 25 | 14.08 | 23 | 0.866 |
| nora-qwen | qwen3:4b-instruct | nora | 12 | 0 | 0.833 |  | 1.0 | 0.08 | 2.17 | 26 | 13.09 | 21.7 | 0.848 |
| sami-qwen | qwen3:4b-instruct | sami | 12 | 0 | 0.667 |  | 1.0 | 0.08 | 2 | 24 | 17.96 | 50.7 | 0.869 |

## Success by category

| category | milo-flash | nora-flash | sami-flash | milo-qwen | nora-qwen | sami-qwen |
|---|---|---|---|---|---|---|
| fact | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| feedback | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| greeting | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 |
| lead | 1/2 | 2/2 | 1/2 | 2/2 | 2/2 | 1/2 |
| no_answer | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| not_offered | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| price | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 2/3 |

## Cases × configurations (passed / runs)

| case | milo-flash | nora-flash | sami-flash | milo-qwen | nora-qwen | sami-qwen |
|---|---|---|---|---|---|---|
| F1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P3 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| N1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| O1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| L1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 |
| L2 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| B2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| G1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 |

## Most common failure reasons

- milo-flash: answer lacks /email/ ×1
- sami-flash: missing tool: record_customer_interest ×1
- milo-qwen: missing tool: search_business_docs ×1
- nora-qwen: outcome: format_fallback ×1
- sami-qwen: missing tool: search_business_docs ×1
- sami-qwen: outcome: format_fallback ×1
- milo-qwen: missing tool: get_package or search_business_docs ×1
- milo-qwen: answer lacks /quot|consult/ ×1
- nora-qwen: missing tool: get_package or search_business_docs ×1
- nora-qwen: answer lacks /quot|consult/ ×1
- sami-qwen: missing tool: get_package or search_business_docs ×1
- sami-qwen: answer lacks /quot|consult/ ×1
- sami-qwen: answer lacks /email/ ×1
