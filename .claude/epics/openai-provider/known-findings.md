# OpenAI Provider — Known Findings

Findings parked during issue #335 development for future investigation.

## F1: No Semantic Quality Measurement for Generated Filenames

**Source**: User feedback from @TheBadFella — "qwen3.5:4b produces poor quality filenames"

**Current state**: We have structural validation (`_clean_ai_generated_name()` strips bad words, enforces length, deduplicates) but zero semantic quality measurement. No way to detect or quantify whether a generated name actually describes the file content.

**Missing capabilities**:
- No scoring of name meaningfulness or descriptiveness
- No comparison of generated name against file content
- No user feedback loop on name quality
- No model-specific quality baselines

**Impact**: Users experience poor naming with weaker models but we can't detect it programmatically. Only manifests as user complaints.

**Potential approaches** (not yet evaluated):
- LLM-as-judge scoring pass on generated names
- Embedding similarity between file content and generated name
- User satisfaction signal collection (accept/rename tracking)

**Priority**: Low — park for future sprint
