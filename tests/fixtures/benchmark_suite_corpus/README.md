## Benchmark Suite Corpus Notes

This corpus is intentionally minimal and deterministic.

Why `sample_audio.wav` is a tiny valid WAV:
- The benchmark suite contract here is runner-path execution stability, not codec quality benchmarking.
- A tiny valid WAV exercises audio suite routing/classification without introducing parser variance from compressed codecs.
- Rich codec coverage belongs in dedicated media integration/perf suites, not this CLI contract corpus.
