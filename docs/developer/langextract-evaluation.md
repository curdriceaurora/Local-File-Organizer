# langextract Evaluation

How we evaluate [langextract](https://pypi.org/project/langextract/) (currently 1.7.0; first evaluated at 1.1.1) as a grounded entity extractor for Local File Organizer, and what we found.

---

## Overview

langextract turns unstructured text into typed extractions and records where each extraction sits in the source text. The question for this repo: does it extract document facts (dates, amounts, organizations, people, reference numbers) more accurately or more verifiably than the structured-output path we already have (`BaseModel.generate_structured`), at acceptable cost?

This page is for maintainers deciding whether to adopt it. The harness lives in `scripts/langextract_eval/`, is off-CI, and nothing under `src/` imports langextract.

---

## Setup

The `eval` extra pins `langextract==1.7.0`. It is deliberately not part of `all`.

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

Recorded runs (raw predictions plus reports) are committed so anyone can re-score them without a model:

- `scripts/langextract_eval/results/2026-09-25-v1.7.0/`: langextract 1.7.0 (current pin)
- `scripts/langextract_eval/results/2026-09-24/`: langextract 1.1.1 (first evaluation)

```bash
python -m scripts.langextract_eval --rescore scripts/langextract_eval/results/2026-09-25-v1.7.0/qwen7b/results.json --output-dir output/langextract_eval/rescored
```

Run environment: 4 vCPU, no GPU, Ollama 0.34.4, Python 3.11.15, temperature 0, `max_char_buffer=1000`, 1 extraction pass, 12 documents with 76 gold entities.

### Headline numbers (langextract 1.7.0)

`qwen2.5:3b-instruct-q4_K_M` (project default):

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | s/case |
|---|---|---|---|---|---|
| baseline | 0.803 | 0.645 | 0.715 | 0.759 | 14.3 |
| langextract adapter | 0.662 | 0.671 | 0.667 | 0.758 | 16.3 |
| langextract native Ollama | 0.713 | 0.750 | 0.731 | 0.808 | 17.7 |
| langextract native Ollama, grounded-only | 0.750 | 0.750 | 0.750 | 0.829 | 17.7 |

`qwen2.5:7b-instruct-q4_K_M` (project large default):

| Extractor | Strict P | Strict R | Strict F1 | Lenient F1 | s/case |
|---|---|---|---|---|---|
| baseline | 0.786 | 0.868 | 0.825 | 0.888 | 34.6 |
| langextract adapter | 0.812 | 0.908 | 0.857 | 0.907 | 39.9 |
| langextract native Ollama | 0.784 | 0.908 | 0.841 | 0.878 | 41.0 |

The 7B baseline row comes from a separate warm run. Inside the batch run, the baseline's first document failed with an Ollama model-load timeout, so the recorded `results.json` notes this merge. The harness now makes an untimed warm-up call before any extractor runs, to prevent that.

Paired bootstrap over documents (strict F1, langextract minus baseline): 3B native grounded-only +0.035, 95% CI [−0.078, +0.164]. 7B adapter +0.032, 95% CI [−0.030, +0.115]. **Every interval spans zero.**

### 1.1.1 → 1.7.0

- **Drop-in compatible.** The adapter, the native provider call and all tests work unchanged, with no deprecation warnings. The dependency list is identical, and `uv.lock` changes only the langextract line.
- **Same extractions.** The native Ollama path produced the same entity text on every document with both models, and so did the adapter at 7B. The `--max-char-buffer 3000` ablation is also unchanged (native strict F1 0.703).
- **Better alignment.** Spans that 1.1.1 labelled `match_fuzzy` are now `match_exact` at the same offsets. A repeated name ("Marcus" in the meeting notes) now points to its own occurrence instead of the first mention. This does not move any score, because matching is text-based.
- **New options:** `context_window_chars` carries text from the previous chunk into the next chunk's prompt, for coreference, and is off by default; it is tested below. `fetch_urls` now defaults to off (the harness already passed `False`).

### `context_window_chars` on the long document

The option is exposed as `--context-window-chars`. It was tested on the vendor report, the only document that gets chunked. The report splits into a 922-character chunk ending "Fabrikam Logistics. Spend was $112,900.00, mostly freight." and a 648-character chunk starting "The rate card renegotiated…". Six of the report's 15 gold entities are in chunk 2, and none of them needs the previous chunk to be resolved.

Setup: both langextract extractors, 3 repeats each, context off / 200 / 500 / 1,000 characters. Raw runs are in `scripts/langextract_eval/results/2026-09-25-v1.7.0/context_window/`.

| Model | Context | Native strict F1 (3 runs) | Adapter strict F1 (3 runs) | Chunk-2 gold found (native) | Unaligned (native) |
|---|---|---|---|---|---|
| 3B | off | 0.59 / 0.59 / 0.59 | 0.31 / 0.31 / 0.31 | 1/6 | 3 |
| 3B | 200 | 0.85 / 0.77 / 0.77 | 0.55 / 0.55 / 0.55 | 4/6 | 0 |
| 3B | 500 | 0.81 / 0.74 / 0.74 | 0.58 / 0.52 / 0.52 | 4/6 | 0 |
| 3B | 1000 | 0.61 / 0.52 / 0.52 | 0.36 / 0.21 / 0.21 | 0/6 | 1 |
| 7B | off | 0.90 / 0.90 / 0.90 | 0.97 / 0.97 / 0.97 | 6/6 | 0 |
| 7B | 200 | 0.62 / 0.62 / 0.62 | 0.97 / 0.93 / 0.93 | 0/6 | 4 |
| 7B | 500 | 0.89 / 0.89 / 0.89 | 0.97 / 0.93 / 0.93 | 5/6 | 0 |
| 7B | 1000 | 0.53 / 0.65 / 0.65 | 0.62 / 0.63 / 0.63 | 2–3/6 | 10–12 |

What happened:

- **3B, small window: helps.** Without context, 3B rewrote chunk 2's text instead of copying it ("Tailware Consulting" for "Litware Consulting", dates reformatted to ISO), so those spans could not be aligned. With 200–500 characters of context it copied them verbatim, and the few-shot leakage disappeared.
- **Large window, or 7B: hurts.** The model extracts from the context passage instead of the chunk it was given. At 1,000 characters (the whole previous chunk), both models re-extracted chunk 1's entities; 7B also added the example's "Ana Silva". At 200 characters, 7B native returned only the four entities in the context window for chunk 2 and none of chunk 2's own.
- **Grounding contains the damage but can't undo it.** The re-extracted context entities cannot be aligned inside the chunk, so the grounded-only filter removes them: 7B at 1,000 characters goes from precision 0.52 to 1.00 (native). Chunk-2 entities the model skipped stay missing.
- **The native path stopped reproducing exactly** under some settings (for example, 3B at 200 characters: 0.85, then 0.77 twice). Without context it was identical across all runs. The cause was not investigated.

This is one document with one chunk boundary, so treat it as anecdotal. The option is not a safe default here: it helps the small model only in a narrow window, and it hurts a model that already handles chunks well.

### Run-to-run variation

At temperature 0, calls that go through the project model layer (the baseline and the langextract adapter) did not always reproduce. The native provider (Ollama JSON mode) reproduced exactly in every run without `context_window_chars`, but not with it (see above). The cause was not investigated.

| Extractor | Strict F1 across runs |
|---|---|
| 3B baseline | 0.695, 0.695, 0.715 |
| 3B langextract adapter | 0.684, 0.684, 0.667 |
| 3B langextract native | 0.731, 0.731, 0.731 |
| 7B baseline | 0.800, 0.825 |
| 7B langextract adapter | 0.857, 0.857 |
| 7B langextract native | 0.841, 0.841 |

3B runs are: 1.1.1; a 1.7.0 run whose first document included a cold model load (not committed, and its scores match the 1.1.1 run); and the committed 1.7.0 warm run. The swing of up to about 0.025 F1 on a single extractor is the same order as the langextract-versus-baseline gaps, so comparisons need `--repeats` as well as more documents.

### Initial results (langextract 1.1.1, 2026-09-24)

| Model | Extractor | Strict F1 | s/case |
|---|---|---|---|
| 3B | baseline | 0.695 | 13.5 |
| 3B | langextract adapter | 0.684 | 16.3 |
| 3B | langextract native, grounded-only | 0.750 | 16.8 |
| 7B | baseline | 0.800 | 32.4 |
| 7B | langextract adapter | 0.857 | 37.7 |
| 7B | langextract native | 0.841 | 39.7 |

Bootstrap: 3B native grounded-only +0.055 [−0.058, +0.206]; 7B adapter +0.057 [−0.007, +0.134]. Part of these gaps came from the lower first 7B baseline run (see run-to-run variation).

### What drives the differences

These patterns hold in both the 1.1.1 and 1.7.0 runs:

1. **Recall, via chunking, on long documents.** On the 1,572-character vendor report (two 1,000-character chunks), 3B baseline recall was 0.33, against 0.53 for langextract native, in both versions. Re-running native with `--max-char-buffer 3000` (one chunk) dropped it to 0.20. At 7B the gap mostly disappears.
2. **Small-model early stops.** On the lease, the 3B baseline stopped early: 1 entity (0/7 strict) in the 1.1.1 run, and 3 entities (2/7) in the 1.7.0 run. Both langextract paths found 6/7 in both.
3. **Reference IDs at 7B.** Strict F1 for `reference_id` was 0.429 for the baseline in both the 1.1.1 and the 1.7.0 run, against 0.857 for both langextract paths.
4. **Parse robustness is not a differentiator.** No extractor failed a document on output parsing. The only failure was the model-load timeout described above.

### What grounding does and does not give you

- **It catches few-shot leakage.** On the long report, 3B langextract emitted entities copied from the worked example ("Ana Silva", garbled "Coho Winery") and dates reformatted to ISO. langextract left these unaligned. Dropping unaligned predictions raised 3B native strict F1 from 0.731 to 0.750 with no recall loss. At 7B there were no unaligned predictions, so the filter changed nothing.
- **Alignment is not verification.** Fuzzy or lesser alignment still attaches offsets to text that is not in the source. For example, 7B returned "$12,410.33" for a source "12,410.33", and one ISO date got `match_lesser`. Offset accuracy was 0.966–0.986, not 1.0, in both versions. Code that relies on offsets must itself check that `text[start:end]` equals the extraction.

### Adapter versus native provider

There is no consistent quality winner: native led at 3B and the adapter led at 7B. The native provider was the only path that reproduced exactly across runs, as long as `context_window_chars` was off. The adapter (`FileOrganizerLanguageModel`) lets every provider we ship run langextract unchanged.

### Cost

- **Calls and latency:** one extra call on the chunked document, and roughly 15–25% more wall time per document (1.7.0: 3B 14.3 → 16.3–17.7 s; 7B 34.6 → 39.9–41.0 s).
- **Dependencies:** the `eval` extra adds 27 packages to `uv.lock`, including google-genai, google-cloud-storage, pandas and aiohttp. `import langextract` loaded pandas and absl eagerly in 1.1.1; this was not re-measured for 1.7.0.

### Recommendation

Do not adopt into the core pipeline yet. Upgrading to 1.7.0 changes alignment details, not extraction quality. langextract's advantages are specific: recall on long documents and reference IDs, small-model early stops, and a cheap hallucination filter. But no difference is statistically resolved, run-to-run variation is the same size as the gaps, and it costs 15–25% latency plus a heavy dependency tree. Next steps, in order:

1. Grow the corpus to roughly 50–100 labelled documents from real sample files. This is a rough estimate: interval widths shrink about as 1/√n, and the observed 95% intervals are ±0.07–0.13 at 12 documents.
2. Run every comparison with `--repeats 3` or more, and find out why the project model layer is not reproducible at temperature 0.
3. Try `--passes 2`. Leave `context_window_chars` off unless a larger corpus with real cross-chunk references shows a benefit; if it is used, keep it small (about 200–500 characters) and keep grounded-only filtering on.
4. If adoption follows, use it through the adapter in an optional extra with a lazy import, keep only grounded predictions, and verify offsets in our own code.
