# Results: p_flash

102 runs; cases file ['d7e1f48e0d8d']. success = share of runs where every check passed (± spread across repeats).

| config_id | model | persona | runs | errors | success | success_sd | tool_precision | format_errors | steps | requests | latency_s | words | distinct_2 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| milo-flash | gemini-3.5-flash-lite | milo | 34 | 0 | 0.941 |  | 0.976 | 0.26 | 2.41 | 100 | 12.68 | 31.6 | 0.771 |
| nora-flash | gemini-3.5-flash-lite | nora | 34 | 0 | 0.853 |  | 0.985 | 0.53 | 2.65 | 118 | 3.6 | 27.2 | 0.761 |
| sami-flash | gemini-3.5-flash-lite | sami | 34 | 0 | 0.882 |  | 0.985 | 0.15 | 2.18 | 78 | 2.1 | 57.6 | 0.78 |

## Success by category

| category | milo-flash | nora-flash | sami-flash |
|---|---|---|---|
| fact | 10/10 | 9/10 | 10/10 |
| feedback | 2/2 | 2/2 | 1/2 |
| greeting | 2/2 | 2/2 | 2/2 |
| language | 1/2 | 1/2 | 2/2 |
| lead | 3/4 | 4/4 | 3/4 |
| memory | 1/1 | 1/1 | 1/1 |
| no_answer | 3/3 | 3/3 | 3/3 |
| not_offered | 3/3 | 2/3 | 1/3 |
| planning | 3/3 | 1/3 | 3/3 |
| price | 3/3 | 3/3 | 3/3 |
| safety | 1/1 | 1/1 | 1/1 |

## Cases × configurations (passed / runs)

| case | milo-flash | nora-flash | sami-flash |
|---|---|---|---|
| F1 | 1/1 | 1/1 | 1/1 |
| F2 | 1/1 | 1/1 | 1/1 |
| F3 | 1/1 | 1/1 | 1/1 |
| F4 | 1/1 | 1/1 | 1/1 |
| F5 | 1/1 | 0/1 | 1/1 |
| F6 | 1/1 | 1/1 | 1/1 |
| F7 | 1/1 | 1/1 | 1/1 |
| F8 | 1/1 | 1/1 | 1/1 |
| F9 | 1/1 | 1/1 | 1/1 |
| F10 | 1/1 | 1/1 | 1/1 |
| P1 | 1/1 | 1/1 | 1/1 |
| P2 | 1/1 | 1/1 | 1/1 |
| P3 | 1/1 | 1/1 | 1/1 |
| N1 | 1/1 | 1/1 | 1/1 |
| N2 | 1/1 | 1/1 | 1/1 |
| N3 | 1/1 | 1/1 | 1/1 |
| O1 | 1/1 | 1/1 | 1/1 |
| O2 | 1/1 | 1/1 | 0/1 |
| O3 | 1/1 | 0/1 | 0/1 |
| L1 | 0/1 | 1/1 | 1/1 |
| L2 | 1/1 | 1/1 | 0/1 |
| L3 | 1/1 | 1/1 | 1/1 |
| L4 | 1/1 | 1/1 | 1/1 |
| B1 | 1/1 | 1/1 | 0/1 |
| B2 | 1/1 | 1/1 | 1/1 |
| G1 | 1/1 | 1/1 | 1/1 |
| G2 | 1/1 | 1/1 | 1/1 |
| M1 | 1/1 | 1/1 | 1/1 |
| A1 | 1/1 | 1/1 | 1/1 |
| A2 | 0/1 | 0/1 | 1/1 |
| S1 | 1/1 | 1/1 | 1/1 |
| C1 | 1/1 | 1/1 | 1/1 |
| C2 | 1/1 | 0/1 | 1/1 |
| C3 | 1/1 | 0/1 | 1/1 |

## Most common failure reasons

- nora-flash: outcome: format_fallback ×2
- sami-flash: missing tool: search_business_docs ×2
- milo-flash: answer lacks /email/ ×1
- milo-flash: answer lacks /5\s*(à|a|-|–)\s*10/ ×1
- nora-flash: missing tool: record_feedback ×1
- nora-flash: answer lacks /not|don't|do not/ ×1
- nora-flash: outcome: gave_up ×1
- nora-flash: answer lacks /5\s*(à|a|-|–)\s*10/ ×1
- nora-flash: answer lacks /jours|semaines|ouvr/ ×1
- nora-flash: answer lacks /\?/ ×1
- nora-flash: answer lacks /chapter/ ×1
- sami-flash: missing tool: record_customer_interest ×1
- sami-flash: missing tool: record_feedback ×1
- sami-flash: answer lacks /thank/ ×1
