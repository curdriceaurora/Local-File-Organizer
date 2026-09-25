# langextract evaluation run

- Started: 2026-09-25T03:03:30+00:00
- Backend / model: `ollama` / `qwen2.5:7b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 1 × repeats 3
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=200

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 0.727 | 0.533 | 0.615 | 0.615 | 1.000 | 1.000 | 0/3 | 71.162 | 6 |
| langextract_native_ollama+grounded | 1.000 | 0.467 | 0.636 | 0.636 | 1.000 | 1.000 | 0/3 | 71.162 | 6 |
| langextract_adapter | 0.935 | 0.956 | 0.945 | 0.945 | 1.000 | 1.000 | 0/3 | 90.469 | 6 |
| langextract_adapter+grounded | 0.935 | 0.956 | 0.945 | 0.945 | 1.000 | 1.000 | 0/3 | 90.469 | 6 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded | langextract_adapter | langextract_adapter+grounded |
|---|---|---|---|---|
| document_type | 1.000 | 1.000 | 0.667 | 0.667 |
| organization | 0.667 | 0.400 | 1.000 | 1.000 |
| person | 0.667 | 0.800 | 1.000 | 1.000 |
| date | 0.000 | 0.000 | 1.000 | 1.000 |
| amount | 0.667 | 0.800 | 0.875 | 0.875 |
| reference_id | 0.667 | 1.000 | 1.000 | 1.000 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a source span (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
