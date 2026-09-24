"""Evaluation harness for langextract as a grounded entity extractor.

Compares langextract (pinned in the ``eval`` extra) against the project's
existing ``BaseModel.generate_structured`` path on a gold-labelled corpus.
Off-CI, on-demand tooling: nothing under ``src/`` imports langextract.

Run ``python -m scripts.langextract_eval --help`` from the repo root; see
``docs/developer/langextract-evaluation.md`` for the method and findings.
"""
