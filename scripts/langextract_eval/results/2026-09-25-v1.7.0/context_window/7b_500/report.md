# langextract evaluation run

- Started: 2026-09-25T03:11:36+00:00
- Backend / model: `ollama` / `qwen2.5:7b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 1 × repeats 3
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=500

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 1.000 | 0.800 | 0.889 | 0.889 | 1.000 | 1.000 | 0/3 | 70.276 | 6 |
| langextract_native_ollama+grounded | 1.000 | 0.800 | 0.889 | 0.889 | 1.000 | 1.000 | 0/3 | 70.276 | 6 |
| langextract_adapter | 1.000 | 0.889 | 0.941 | 0.941 | 1.000 | 1.000 | 0/3 | 76.51 | 6 |
| langextract_adapter+grounded | 1.000 | 0.889 | 0.941 | 0.941 | 1.000 | 1.000 | 0/3 | 76.51 | 6 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded | langextract_adapter | langextract_adapter+grounded |
|---|---|---|---|---|
| document_type | 1.000 | 1.000 | 1.000 | 1.000 |
| organization | 0.667 | 0.667 | 1.000 | 1.000 |
| person | 1.000 | 1.000 | 1.000 | 1.000 |
| date | 0.800 | 0.800 | 0.800 | 0.800 |
| amount | 1.000 | 1.000 | 0.875 | 0.875 |
| reference_id | 1.000 | 1.000 | 1.000 | 1.000 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a span that reproduces their text (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
