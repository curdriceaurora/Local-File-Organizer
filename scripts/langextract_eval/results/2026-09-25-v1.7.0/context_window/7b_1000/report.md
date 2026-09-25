# langextract evaluation run

- Started: 2026-09-25T03:18:59+00:00
- Backend / model: `ollama` / `qwen2.5:7b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 1 × repeats 3
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=1000

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 0.524 | 0.733 | 0.611 | 0.611 | 0.857 | 1.000 | 0/3 | 117.639 | 6 |
| langextract_native_ollama+grounded | 1.000 | 0.644 | 0.784 | 0.784 | 1.000 | 1.000 | 0/3 | 117.639 | 6 |
| langextract_adapter | 0.514 | 0.800 | 0.626 | 0.626 | 0.871 | 1.000 | 0/3 | 132.974 | 6 |
| langextract_adapter+grounded | 1.000 | 0.756 | 0.861 | 0.861 | 1.000 | 1.000 | 0/3 | 132.974 | 6 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded | langextract_adapter | langextract_adapter+grounded |
|---|---|---|---|---|
| document_type | 0.667 | 1.000 | 0.667 | 1.000 |
| organization | 0.750 | 0.588 | 0.727 | 1.000 |
| person | 0.667 | 1.000 | 0.667 | 1.000 |
| date | 0.000 | 0.000 | 0.000 | 0.000 |
| amount | 0.750 | 1.000 | 0.818 | 0.875 |
| reference_id | 0.667 | 1.000 | 0.667 | 1.000 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a source span (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
