# langextract evaluation run

- Started: 2026-09-24T22:27:27+00:00
- Backend / model: `ollama` / `qwen2.5:3b-instruct-q4_K_M`
- langextract: 1.1.1
- Cases: 12 × repeats 1
- Options: temperature=0.0, max_char_buffer=3000, passes=1, suppress_parse_errors=False, context_window_chars=None

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 0.722 | 0.684 | 0.703 | 0.784 | 0.958 | 0.986 | 0/12 | 15.36 | 12 |
| langextract_native_ollama+grounded | 0.754 | 0.684 | 0.717 | 0.786 | 1.000 | 1.000 | 0/12 | 15.36 | 12 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded |
|---|---|---|
| document_type | 0.632 | 0.667 |
| organization | 0.786 | 0.786 |
| person | 0.593 | 0.593 |
| date | 0.833 | 0.857 |
| amount | 0.720 | 0.750 |
| reference_id | 0.462 | 0.462 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a span that reproduces their text (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
