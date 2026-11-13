# langextract evaluation run

- Started: 2026-09-25T02:46:39+00:00
- Backend / model: `ollama` / `qwen2.5:3b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 1 × repeats 3
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=200

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| langextract_native_ollama | 0.939 | 0.689 | 0.795 | 0.846 | 1.000 | 1.000 | 0/3 | 30.57 | 6 |
| langextract_native_ollama+grounded | 0.939 | 0.689 | 0.795 | 0.846 | 1.000 | 1.000 | 0/3 | 30.57 | 6 |
| langextract_adapter | 0.857 | 0.400 | 0.545 | 0.636 | 1.000 | 1.000 | 0/3 | 21.656 | 6 |
| langextract_adapter+grounded | 0.857 | 0.400 | 0.545 | 0.636 | 1.000 | 1.000 | 0/3 | 21.656 | 6 |

## Strict F1 by class

| Class | langextract_native_ollama | langextract_native_ollama+grounded | langextract_adapter | langextract_adapter+grounded |
|---|---|---|---|---|
| document_type | 1.000 | 1.000 | 1.000 | 1.000 |
| organization | 0.444 | 0.444 | 0.333 | 0.333 |
| person | 1.000 | 1.000 | 0.800 | 0.800 |
| date | 0.500 | 0.500 | 0.500 | 0.500 |
| amount | 1.000 | 1.000 | 0.500 | 0.500 |
| reference_id | 1.000 | 1.000 | 0.000 | 0.000 |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a span that reproduces their text (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
