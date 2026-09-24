# langextract evaluation run

- Started: 2026-09-24T21:54:27+00:00
- Backend / model: `ollama` / `qwen2.5:3b-instruct-q4_K_M`
- langextract: 1.1.1
- Cases: 12 × repeats 1
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| baseline_generate_structured | 0.754 | 0.645 | 0.695 | 0.738 | 0.985 | — | 0/12 | 13.526 | 12 |
| langextract_adapter | 0.671 | 0.697 | 0.684 | 0.787 | 0.924 | 0.973 | 0/12 | 16.256 | 13 |
| langextract_adapter+grounded | 0.707 | 0.697 | 0.702 | 0.808 | 0.973 | 0.973 | 0/12 | 16.256 | 13 |
| langextract_native_ollama | 0.713 | 0.750 | 0.731 | 0.808 | 0.925 | 0.974 | 0/12 | 16.837 | 13 |
| langextract_native_ollama+grounded | 0.750 | 0.750 | 0.750 | 0.829 | 0.974 | 0.974 | 0/12 | 16.837 | 13 |

## Strict F1 by class

| Class | baseline_generate_structured | langextract_adapter | langextract_adapter+grounded | langextract_native_ollama | langextract_native_ollama+grounded |
|---|---|---|---|---|---|
| document_type | 0.526 | 0.571 | 0.571 | 0.632 | 0.632 |
| organization | 0.786 | 0.774 | 0.800 | 0.759 | 0.786 |
| person | 0.741 | 0.643 | 0.667 | 0.690 | 0.690 |
| date | 0.824 | 0.778 | 0.824 | 0.789 | 0.833 |
| amount | 0.571 | 0.800 | 0.800 | 0.815 | 0.846 |
| reference_id | 0.545 | 0.308 | 0.308 | 0.571 | 0.571 |

## Strict F1 vs baseline_generate_structured (paired bootstrap over documents)

| Extractor | ΔF1 | 95% CI | Resolved? |
|---|---|---|---|
| langextract_adapter | -0.011 | [-0.138, +0.166] | no (CI spans 0) |
| langextract_adapter+grounded | +0.007 | [-0.109, +0.177] | no (CI spans 0) |
| langextract_native_ollama | +0.036 | [-0.074, +0.188] | no (CI spans 0) |
| langextract_native_ollama+grounded | +0.055 | [-0.058, +0.206] | no (CI spans 0) |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a source span (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
