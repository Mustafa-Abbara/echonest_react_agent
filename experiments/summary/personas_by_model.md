# Results: personas_by_model

204 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| milo-flash | gemini-3.5-flash-lite | milo | 34 | 0 | 0.941 |  | 0.976 | 0.26 | 2.41 | 100 | 12.68 | 31.6 | 0.771 |
| nora-flash | gemini-3.5-flash-lite | nora | 34 | 0 | 0.853 |  | 0.985 | 0.53 | 2.65 | 118 | 3.6 | 27.2 | 0.761 |
| sami-flash | gemini-3.5-flash-lite | sami | 34 | 0 | 0.882 |  | 0.985 | 0.15 | 2.18 | 78 | 2.1 | 57.6 | 0.78 |
| milo-qwen | qwen3:4b-instruct | milo | 34 | 0 | 0.618 |  | 0.882 | 0.24 | 2.24 | 76 | 14.31 | 23.4 | 0.706 |
| nora-qwen | qwen3:4b-instruct | nora | 34 | 0 | 0.618 |  | 0.868 | 0.21 | 2.24 | 76 | 12.02 | 21.9 | 0.681 |
| sami-qwen | qwen3:4b-instruct | sami | 34 | 0 | 0.588 |  | 0.926 | 0.18 | 2.09 | 72 | 17.58 | 51.4 | 0.773 |

## Success by category

| category | milo-flash | nora-flash | sami-flash | milo-qwen | nora-qwen | sami-qwen |
|---|---|---|---|---|---|---|
| fact | 10/10 | 9/10 | 10/10 | 7/10 | 6/10 | 7/10 |
| feedback | 2/2 | 2/2 | 1/2 | 2/2 | 2/2 | 2/2 |
| greeting | 2/2 | 2/2 | 2/2 | 2/2 | 1/2 | 1/2 |
| language | 1/2 | 1/2 | 2/2 | 0/2 | 0/2 | 0/2 |
| lead | 3/4 | 4/4 | 3/4 | 4/4 | 3/4 | 3/4 |
| memory | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| no_answer | 3/3 | 3/3 | 3/3 | 2/3 | 3/3 | 2/3 |
| not_offered | 3/3 | 2/3 | 1/3 | 1/3 | 1/3 | 1/3 |
| planning | 3/3 | 1/3 | 3/3 | 0/3 | 1/3 | 0/3 |
| price | 3/3 | 3/3 | 3/3 | 2/3 | 2/3 | 2/3 |
| safety | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |

## Cases × configurations (passed / runs)

| case | milo-flash | nora-flash | sami-flash | milo-qwen | nora-qwen | sami-qwen |
|---|---|---|---|---|---|---|
| F1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F4 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F5 | 1/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| F6 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F7 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| F8 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| F9 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| F10 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 |
| P1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| P3 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| N1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| N2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| N3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| O1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| O2 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| O3 | 1/1 | 0/1 | 0/1 | 0/1 | 0/1 | 0/1 |
| L1 | 0/1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 |
| L2 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| L3 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| L4 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 |
| B1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 | 1/1 |
| B2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| G1 | 1/1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 |
| G2 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| M1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 1/1 |
| A1 | 1/1 | 1/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| A2 | 0/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| S1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 | 1/1 |
| C1 | 1/1 | 1/1 | 1/1 | 0/1 | 1/1 | 0/1 |
| C2 | 1/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 |
| C3 | 1/1 | 0/1 | 1/1 | 0/1 | 0/1 | 0/1 |

## Most common failure reasons

- sami-qwen: missing tool: search_business_docs ×4
- milo-qwen: missing tool: get_package or search_business_docs ×4
- sami-qwen: missing tool: get_package or search_business_docs ×4
- milo-qwen: missing tool: search_business_docs ×3
- nora-qwen: missing tool: search_business_docs ×3
- nora-qwen: missing tool: get_package or search_business_docs ×3
- nora-flash: outcome: format_fallback ×2
- sami-flash: missing tool: search_business_docs ×2
- nora-qwen: outcome: format_fallback ×2
- milo-qwen: answer lacks /not|don't|do not/ ×2
- milo-flash: answer lacks /email/ ×1
- milo-flash: answer lacks /5\s*(à|a|-|–)\s*10/ ×1
- nora-flash: missing tool: record_feedback ×1
- nora-flash: answer lacks /not|don't|do not/ ×1
- nora-flash: outcome: gave_up ×1
