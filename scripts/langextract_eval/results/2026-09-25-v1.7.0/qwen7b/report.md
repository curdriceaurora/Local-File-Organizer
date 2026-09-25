# langextract evaluation run

- Started: 2026-09-25T00:18:09+00:00
- Backend / model: `ollama` / `qwen2.5:7b-instruct-q4_K_M`
- langextract: 1.7.0
- Cases: 12 × repeats 1
- Options: temperature=0.0, max_char_buffer=1000, passes=1, suppress_parse_errors=False

> **Note:** baseline_generate_structured taken from a separate warm run started 2026-09-25T00:51:04+00:00; its run inside this batch failed invoice_plain on an Ollama model-load timeout (cold start).

## Summary

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | Verbatim | Offset acc. | Failed cases | s/case | LLM calls |
|---|---|---|---|---|---|---|---|---|---|
| baseline_generate_structured | 0.786 | 0.868 | 0.825 | 0.888 | 1.000 | — | 0/12 | 34.56 | 12 |
| langextract_adapter | 0.812 | 0.908 | 0.857 | 0.907 | 0.988 | 0.976 | 0/12 | 39.906 | 13 |
| langextract_adapter+grounded | 0.812 | 0.908 | 0.857 | 0.907 | 0.988 | 0.976 | 0/12 | 39.906 | 13 |
| langextract_native_ollama | 0.784 | 0.908 | 0.841 | 0.878 | 0.977 | 0.966 | 0/12 | 40.963 | 13 |
| langextract_native_ollama+grounded | 0.784 | 0.908 | 0.841 | 0.878 | 0.977 | 0.966 | 0/12 | 40.963 | 13 |

## Strict F1 by class

| Class | baseline_generate_structured | langextract_adapter | langextract_adapter+grounded | langextract_native_ollama | langextract_native_ollama+grounded |
|---|---|---|---|---|---|
| document_type | 0.667 | 0.667 | 0.667 | 0.737 | 0.737 |
| organization | 0.941 | 0.941 | 0.941 | 0.875 | 0.875 |
| person | 0.880 | 0.880 | 0.880 | 0.846 | 0.846 |
| date | 0.947 | 0.950 | 0.950 | 0.950 | 0.950 |
| amount | 0.774 | 0.733 | 0.733 | 0.727 | 0.727 |
| reference_id | 0.429 | 0.857 | 0.857 | 0.857 | 0.857 |

## Strict F1 vs baseline_generate_structured (paired bootstrap over documents)

| Extractor | ΔF1 | 95% CI | Resolved? |
|---|---|---|---|
| langextract_adapter | +0.032 | [-0.030, +0.115] | no (CI spans 0) |
| langextract_adapter+grounded | +0.032 | [-0.030, +0.115] | no (CI spans 0) |
| langextract_native_ollama | +0.016 | [-0.062, +0.117] | no (CI spans 0) |
| langextract_native_ollama+grounded | +0.016 | [-0.062, +0.117] | no (CI spans 0) |

`+grounded` rows re-score the same run keeping only predictions langextract aligned to a source span (no extra LLM calls). Metric definitions: `scripts/langextract_eval/scoring.py`. Raw predictions and errors: `results.json`.
