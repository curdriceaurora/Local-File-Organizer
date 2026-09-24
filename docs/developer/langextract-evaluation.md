# langextract Evaluation

How we evaluate [langextract](https://pypi.org/project/langextract/) 1.1.1 as a grounded entity extractor for Local File Organizer, and what we found.

---

## Overview

langextract turns unstructured text into typed extractions and records where each extraction sits in the source text. The question for this repo: does it extract document facts (dates, amounts, organizations, people, reference numbers) more accurately or more verifiably than the structured-output path we already have (`BaseModel.generate_structured`), at acceptable cost?

This page is for maintainers deciding whether to adopt it. The harness lives in `scripts/langextract_eval/`, is off-CI, and nothing under `src/` imports langextract.

---

## Setup

The `eval` extra pins `langextract==1.1.1`. It is deliberately not part of `all`.

```bash
pip install -e ".[dev,eval]"
```

A real run needs a model backend. The default is Ollama with the project default text model:

```bash
ollama pull qwen2.5:3b-instruct-q4_K_M
python -m scripts.langextract_eval
```

Useful variants:

```bash
# Offline plumbing check (oracle stub, no model)
python -m scripts.langextract_eval --backend stub

# Another model, several repeats, two langextract passes
python -m scripts.langextract_eval --model qwen2.5:7b-instruct-q4_K_M --repeats 3 --passes 2

# Any shipped provider (the lx-native extractor is Ollama-only)
python -m scripts.langextract_eval --backend openai --model gpt-4o-mini
```

Each run writes `results.json` (config, versions, per-case predictions and errors) and `report.md` to `output/langextract_eval/<UTC timestamp>/` (gitignored), or to `--output-dir`.

---

## Method

### Extractors compared

| Extractor | What it runs |
|---|---|
| `baseline_generate_structured` | Our current approach: one `generate_structured` call per document with a Pydantic schema. No grounding. |
| `langextract_adapter` | `langextract.extract` driven through `FileOrganizerLanguageModel`, an adapter over any project `BaseModel`, so every provider we ship works unchanged. |
| `langextract_native_ollama` | `langextract.extract` with langextract's own Ollama provider, which uses Ollama JSON mode. |

All three get the same task description and the same single worked example, so differences come from the extraction machinery rather than prompt content. Temperature defaults to 0.

### Corpus

`scripts/langextract_eval/corpus.py` holds 12 gold-labelled documents across the source formats our pipeline sees: plain text, PDF, scanned PDF, OCR, spreadsheet, email and code. There are 6 entity classes: `document_type`, `organization`, `person`, `date`, `amount` and `reference_id`. One document is longer than langextract's 1,000-character chunk size, so chunking is exercised, and one has no entities. The annotation rules are in the module docstring. Every gold span must occur verbatim in its document, and a unit test enforces this.

### Metrics

Metrics are defined in `scripts/langextract_eval/scoring.py`:

- **Strict P/R/F1**: same class and identical text after normalization (case, whitespace, edge punctuation). One-to-one matching, so duplicate predictions count as false positives.
- **Lenient F1**: same class, and one text contains the other ("Invoice #INV-4821" vs "INV-4821").
- **Verbatim rate**: share of predictions that occur in the source text. Its complement is the hallucination rate.
- **Offset accuracy**: for predictions with character offsets (langextract only), the share where `text[start:end]` reproduces the prediction.
- **Failed cases**: documents where the extractor raised an error (parse failure or model error). Their gold entities count as missed.
- **s/case** and **LLM calls**: cost. langextract makes one call per chunk per pass.

### Tests

`tests/unit/scripts/` covers the corpus invariants, the scoring and the baseline path without langextract. It also covers the langextract adapter, chunking, grounding of a fabricated entity and the CLI against the stub model. Those last tests skip when the `eval` extra is absent.

---

## Findings

Recorded runs (raw predictions plus reports) are in `scripts/langextract_eval/results/2026-09-24/`. Re-score any of them without a model:

```bash
python -m scripts.langextract_eval --rescore scripts/langextract_eval/results/2026-09-24/qwen7b/results.json --output-dir output/langextract_eval/rescored
```

Run environment: 4 vCPU, no GPU, Ollama 0.34.4, Python 3.11.15, langextract 1.1.1, temperature 0, `max_char_buffer=1000`, 1 extraction pass, 12 documents with 76 gold entities.

### Headline numbers

`qwen2.5:3b-instruct-q4_K_M` (project default):

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | s/case |
|---|---|---|---|---|---|
| baseline | 0.754 | 0.645 | 0.695 | 0.738 | 13.5 |
| langextract adapter | 0.671 | 0.697 | 0.684 | 0.787 | 16.3 |
| langextract native Ollama | 0.713 | 0.750 | 0.731 | 0.808 | 16.8 |
| langextract native Ollama, grounded-only | 0.750 | 0.750 | 0.750 | 0.829 | 16.8 |

`qwen2.5:7b-instruct-q4_K_M` (project large default):

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | s/case |
|---|---|---|---|---|---|
| baseline | 0.785 | 0.816 | 0.800 | 0.877 | 32.4 |
| langextract adapter | 0.812 | 0.908 | 0.857 | 0.907 | 37.7 |
| langextract native Ollama | 0.784 | 0.908 | 0.841 | 0.878 | 39.7 |

Paired bootstrap over documents (strict F1, langextract minus baseline): 3B native grounded-only +0.055, 95% CI [−0.058, +0.206]. 7B adapter +0.057, 95% CI [−0.007, +0.134]. **Every interval spans zero.** The direction favours langextract with both models, but 12 documents cannot resolve a difference of this size.

### What drives the differences

1. **Recall, via chunking, on long documents.** On the 1,572-character vendor report (two 1,000-character chunks), 3B baseline recall was 0.33, against 0.53 for langextract native. Re-running native with `--max-char-buffer 3000` (one chunk) dropped it to 0.20. At 7B the gap mostly disappears (baseline 0.93, adapter 1.00, native 0.87).
2. **Small-model early stops.** On the lease, 3B baseline returned one entity (0/7 strict). Both langextract paths found 6/7.
3. **Reference IDs at 7B.** Strict F1 for `reference_id` was 0.429 for the baseline, against 0.857 for both langextract paths.
4. **Parse robustness is not a differentiator.** No extractor had a failed case with either model at temperature 0.

### What grounding does and does not give you

- **It catches few-shot leakage.** On the long report, 3B langextract emitted entities copied from the worked example ("Ana Silva", garbled "Coho Winery") and dates reformatted to ISO. langextract left these unaligned. Dropping unaligned predictions raised 3B native strict F1 from 0.731 to 0.750 with no recall loss. At 7B there were no unaligned predictions, so the filter changed nothing.
- **Alignment is not verification.** Fuzzy or lesser alignment still attaches offsets to text that is not in the source. For example, 7B returned "$12,410.33" for a source "12,410.33", and one ISO date got `match_lesser`. Offset accuracy was 0.966–0.986, not 1.0. Code that relies on offsets must itself check that `text[start:end]` equals the extraction.

### Adapter versus native provider

There is no consistent winner: native led at 3B and the adapter led at 7B. The adapter (`FileOrganizerLanguageModel`) lets every provider we ship run langextract unchanged, so the native provider is not needed.

### Cost

- **Calls and latency:** one extra call on the chunked document, and about 20% more wall time per document (3B: 13.5 → 16.3–16.8 s; 7B: 32.4 → 37.7–39.7 s).
- **Dependencies:** the `eval` extra adds 27 packages to `uv.lock`, including google-genai, google-cloud-storage, pandas and aiohttp. `import langextract` loads pandas and absl eagerly.

### Recommendation

Do not adopt into the core pipeline yet. The signal is consistently in langextract's favour for recall (long documents, reference IDs, small-model early stops), and its alignment works as a cheap hallucination filter. But no difference is statistically resolved, and it costs about 20% latency plus a heavy dependency tree. Next steps, in order:

1. Grow the corpus to roughly 50–100 labelled documents from real sample files. This is a rough estimate: interval widths shrink about as 1/√n, and the observed 95% intervals are ±0.07–0.13 at 12 documents.
2. Re-run on the current langextract release (1.1.1 is six releases behind; bumping the `eval` pin is a one-line change) and with `--passes 2`.
3. If adoption follows, use it through the adapter in an optional extra with a lazy import, keep only grounded predictions, and verify offsets in our own code.
