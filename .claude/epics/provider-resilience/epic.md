---
name: provider-resilience
title: Provider Resilience & Graceful Degradation
status: in-progress
created: 2026-03-09T06:21:05Z
updated: 2026-03-09T06:43:13Z
progress: 100%
github: https://github.com/curdriceaurora/Local-File-Organizer/issues/677
---

# Epic: Provider Resilience & Graceful Degradation

## Overview

Make the pipeline verifiably resilient when AI providers (Ollama) are unavailable.
Establishes the foundation for the "Local First" positioning with provable fallback behavior.

## Goals

- Graceful degradation for all file types when Ollama is unreachable
- Verifiable via `pytest -m no_ollama`
- Extends to future provider abstraction (OpenAI-compatible endpoints)

## Tasks

- [ ] #677 — Verifiable graceful degradation when Ollama is unavailable
