# langextract evaluation run

- Started: 2026-09-25T00:58:48+00:00
- Backend / model: `ollama` / `qwen2.5:3b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 12 × repeats 1
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=None

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| baseline_generate_structured | 0.803 | 0.645 | 0.715 | 0.759 | 0.984 | — | 0/12 | 14.298 | 12 |
| langextract_adapter | 0.662 | 0.671 | 0.667 | 0.758 | 0.922 | 0.973 | 0/12 | 16.299 | 13 |
| langextract_adapter+grounded | 0.718 | 0.671 | 0.694 | 0.776 | 1.000 | 1.000 | 0/12 | 16.299 | 13 |
| langextract_native_ollama | 0.713 | 0.750 | 0.731 | 0.808 | 0.925 | 0.974 | 0/12 | 17.663 | 13 |
| langextract_native_ollama+grounded | 0.770 | 0.750 | 0.760 | 0.827 | 1.000 | 1.000 | 0/12 | 17.663 | 13 |

## Strict F1 by class

| Class | baseline_generate_structured | langextract_adapter | langextract_adapter+grounded | langextract_native_ollama | langextract_native_ollama+grounded |
|---|---|---|---|---|---|
| document_type | 0.526 | 0.600 | 0.632 | 0.632 | 0.667 |
| organization | 0.828 | 0.690 | 0.714 | 0.759 | 0.786 |
| person | 0.786 | 0.643 | 0.643 | 0.690 | 0.690 |
| date | 0.848 | 0.757 | 0.824 | 0.789 | 0.857 |
| amount | 0.500 | 0.720 | 0.750 | 0.815 | 0.846 |
| reference_id | 0.545 | 0.429 | 0.429 | 0.571 | 0.571 |

## Strict F1 vs baseline_generate_structured (paired bootstrap over documents)

| Extractor | ΔF1 | 95% CI | Resolved? |
|---|---|---|---|
| langextract_adapter | -0.049 | [-0.199, +0.114] | no (CI spans 0) |
| langextract_adapter+grounded | -0.021 | [-0.166, +0.133] | no (CI spans 0) |
| langextract_native_ollama | +0.015 | [-0.088, +0.143] | no (CI spans 0) |
| langextract_native_ollama+grounded | +0.045 | [-0.069, +0.172] | no (CI spans 0) |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a span that reproduces their text (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
