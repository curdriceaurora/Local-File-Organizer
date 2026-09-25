# langextract evaluation run

- Started: 2026-09-25T02:54:26+00:00
- Backend / model: `ollama` / `qwen2.5:7b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 1 × repeats 3
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=None

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 0.929 | 0.867 | 0.897 | 0.897 | 1.000 | 1.000 | 0/3 | 79.526 | 6 |
| langextract_native_ollama+grounded | 0.929 | 0.867 | 0.897 | 0.897 | 1.000 | 1.000 | 0/3 | 79.526 | 6 |
| langextract_adapter | 0.938 | 1.000 | 0.968 | 0.968 | 1.000 | 1.000 | 0/3 | 91.195 | 6 |
| langextract_adapter+grounded | 0.938 | 1.000 | 0.968 | 0.968 | 1.000 | 1.000 | 0/3 | 91.195 | 6 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded | langextract_adapter | langextract_adapter+grounded |
|---|---|---|---|---|
| document_type | 0.667 | 0.667 | 0.667 | 0.667 |
| organization | 0.667 | 0.667 | 1.000 | 1.000 |
| person | 1.000 | 1.000 | 1.000 | 1.000 |
| date | 1.000 | 1.000 | 1.000 | 1.000 |
| amount | 1.000 | 1.000 | 1.000 | 1.000 |
| reference_id | 1.000 | 1.000 | 1.000 | 1.000 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a source span (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
