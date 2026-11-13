# langextract evaluation run

- Started: 2026-09-24T22:05:29+00:00
- Backend / model: `ollama` / `qwen2.5:7b-instruct-q4_K_M`
- langextract: 1.1.1
- Cases: 12 × repeats 1
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False, context_window_chars=None

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| baseline_generate_structured | 0.785 | 0.816 | 0.800 | 0.877 | 1.000 | — | 0/12 | 32.405 | 12 |
| langextract_adapter | 0.812 | 0.908 | 0.857 | 0.907 | 0.988 | 0.976 | 0/12 | 37.681 | 13 |
| langextract_adapter+grounded | 0.819 | 0.895 | 0.855 | 0.893 | 1.000 | 1.000 | 0/12 | 37.681 | 13 |
| langextract_native_ollama | 0.784 | 0.908 | 0.841 | 0.878 | 0.977 | 0.966 | 0/12 | 39.68 | 13 |
| langextract_native_ollama+grounded | 0.800 | 0.895 | 0.845 | 0.882 | 1.000 | 1.000 | 0/12 | 39.68 | 13 |

## Strict F1 by class

| Class | baseline_generate_structured | langextract_adapter | langextract_adapter+grounded | langextract_native_ollama | langextract_native_ollama+grounded |
|---|---|---|---|---|---|
| document_type | 0.667 | 0.667 | 0.667 | 0.737 | 0.737 |
| organization | 0.824 | 0.941 | 0.941 | 0.875 | 0.875 |
| person | 0.800 | 0.880 | 0.833 | 0.846 | 0.800 |
| date | 0.947 | 0.950 | 0.950 | 0.950 | 0.950 |
| amount | 0.846 | 0.733 | 0.759 | 0.727 | 0.774 |
| reference_id | 0.429 | 0.857 | 0.857 | 0.857 | 0.857 |

## Strict F1 vs baseline_generate_structured (paired bootstrap over documents)

| Extractor | ΔF1 | 95% CI | Resolved? |
|---|---|---|---|
| langextract_adapter | +0.057 | [-0.007, +0.134] | no (CI spans 0) |
| langextract_adapter+grounded | +0.055 | [-0.005, +0.124] | no (CI spans 0) |
| langextract_native_ollama | +0.041 | [-0.031, +0.131] | no (CI spans 0) |
| langextract_native_ollama+grounded | +0.045 | [-0.019, +0.124] | no (CI spans 0) |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a span that reproduces their text (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
