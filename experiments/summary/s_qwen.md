# Results: s_qwen

144 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| base | qwen3:4b-instruct | milo | 12 | 0 | 0.667 |  | 1.0 | 0.25 | 2.17 | 26 | 12.15 | 21.3 | 0.886 |
| temp-0.0 | qwen3:4b-instruct | milo | 12 | 0 | 0.833 |  | 1.0 | 0.17 | 2.08 | 25 | 11.84 | 23.9 | 0.892 |
| temp-1.4 | qwen3:4b-instruct | milo | 12 | 0 | 0.583 |  | 1.0 | 0.25 | 2.17 | 26 | 11.78 | 23.2 | 0.893 |
| top_p-0.3 | qwen3:4b-instruct | milo | 12 | 0 | 0.833 |  | 1.0 | 0.17 | 2.08 | 25 | 12.51 | 23.9 | 0.892 |
| top_p-1.0 | qwen3:4b-instruct | milo | 12 | 0 | 0.667 |  | 1.0 | 0.25 | 2.17 | 26 | 11.92 | 22.3 | 0.887 |
| top_k-1 | qwen3:4b-instruct | milo | 12 | 0 | 0.833 |  | 1.0 | 0.17 | 2.08 | 25 | 11.76 | 23.9 | 0.892 |
| freq-0.0 | qwen3:4b-instruct | milo | 12 | 0 | 0.667 |  | 1.0 | 0.17 | 2.08 | 25 | 11.37 | 22.5 | 0.914 |
| freq-1.0 | qwen3:4b-instruct | milo | 12 | 0 | 0.667 |  | 1.0 | 0.25 | 2.17 | 26 | 13.01 | 27.3 | 0.865 |
| pres-0.0 | qwen3:4b-instruct | milo | 12 | 0 | 0.667 |  | 1.0 | 0.25 | 2.17 | 26 | 11.82 | 22.2 | 0.888 |
| pres-1.0 | qwen3:4b-instruct | milo | 12 | 0 | 0.75 |  | 1.0 | 0.17 | 2.08 | 25 | 11.75 | 23.1 | 0.896 |
| max_tokens-150 | qwen3:4b-instruct | milo | 12 | 0 | 0.75 |  | 1.0 | 0.25 | 2.17 | 26 | 11.64 | 22.2 | 0.866 |
| max_tokens-600 | qwen3:4b-instruct | milo | 12 | 0 | 0.75 |  | 1.0 | 0.17 | 2.08 | 25 | 11.75 | 23.2 | 0.832 |

## Success by category

| category | base | temp-0.0 | temp-1.4 | top_p-0.3 | top_p-1.0 | top_k-1 | freq-0.0 | freq-1.0 | pres-0.0 | pres-1.0 | max_tokens-150 | max_tokens-600 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| fact | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 | 3/3 |
| feedback | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| greeting | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 |
| lead | 1/2 | 2/2 | 1/2 | 2/2 | 1/2 | 2/2 | 2/2 | 1/2 | 1/2 | 2/2 | 1/2 | 2/2 |
| no_answer | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| not_offered | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| price | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 | 2/3 |

## Cases × configurations (passed / runs)

| case | base | temp-0.0 | temp-1.4 | top_p-0.3 | top_p-1.0 | top_k-1 | freq-0.0 | freq-1.0 | pres-0.0 | pres-1.0 | max_tokens-150 | max_tokens-600 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P3 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| N1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| O1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| L1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| L2 | 0/1 | 1/1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 0/1 | 0/1 | 1/1 | 0/1 | 1/1 |
| B2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| G1 | 0/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 1/1 | 0/1 |

## Most common failure reasons

- base: outcome: format_fallback ×2
- temp-1.4: outcome: format_fallback ×2
- freq-1.0: outcome: format_fallback ×2
- pres-0.0: outcome: format_fallback ×2
- base: missing tool: get_package or search_business_docs ×1
- base: answer lacks /quot|consult/ ×1
- base: missing tool: search_business_docs ×1
- temp-0.0: missing tool: get_package or search_business_docs ×1
- temp-0.0: answer lacks /quot|consult/ ×1
- temp-0.0: missing tool: search_business_docs ×1
- temp-1.4: missing tool: get_package or search_business_docs ×1
- temp-1.4: answer lacks /quot|consult/ ×1
- temp-1.4: missing tool: search_business_docs ×1
- temp-1.4: answer lacks /not|don't|do not/ ×1
- top_p-0.3: missing tool: get_package or search_business_docs ×1
