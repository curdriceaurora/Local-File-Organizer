# langextract evaluation run

- Started: 2026-09-25T02:52:11+00:00
- Backend / model: `ollama` / `qwen2.5:3b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 1 × repeats 3
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=1000

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 0.792 | 0.422 | 0.551 | 0.609 | 1.000 | 1.000 | 0/3 | 25.622 | 6 |
| langextract_native_ollama+grounded | 0.905 | 0.422 | 0.576 | 0.636 | 1.000 | 1.000 | 0/3 | 25.622 | 6 |
| langextract_adapter | 0.533 | 0.178 | 0.267 | 0.367 | 0.933 | 0.917 | 0/3 | 18.78 | 6 |
| langextract_adapter+grounded | 0.667 | 0.178 | 0.281 | 0.386 | 0.917 | 0.917 | 0/3 | 18.78 | 6 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded | langextract_adapter | langextract_adapter+grounded |
|---|---|---|---|---|
| document_type | 0.667 | 1.000 | 0.667 | 1.000 |
| organization | 0.133 | 0.133 | 0.125 | 0.125 |
| person | 0.800 | 0.800 | 0.615 | 0.615 |
| date | 0.000 | 0.000 | 0.000 | 0.000 |
| amount | 0.800 | 0.800 | 0.000 | 0.000 |
| reference_id | 1.000 | 1.000 | 0.000 | 0.000 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a source span (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
