---
issue: 81
title: Add PARA smart suggestions
analyzed: 2026-01-24T11:37:58Z
estimated_hours: 24
parallelization_factor: 3.5
---

# Parallel Work Analysis: Issue #81

## Overview
Implement AI-powered smart suggestions for PARA categorization with content analysis, user feedback loops, and PARA-aware file movement. This is the intelligence layer that makes PARA organization intuitive and learns from user behavior.

## Parallel Streams

### Stream A: AI Content Analysis Engine
**Scope**: Build content analysis pipeline using Claude API
**Files**:
- `file_organizer_v2/src/file_organizer/ai/content_analyzer.py`
- `file_organizer_v2/src/file_organizer/ai/feature_extractor.py`
- `file_organizer_v2/src/file_organizer/ai/claude_integration.py`
- `file_organizer_v2/src/file_organizer/ai/text_analysis.py`
**Agent Type**: ai-specialist
**Can Start**: immediately
**Estimated Hours**: 7 hours
**Dependencies**: none

**Tasks:**
- Create `FeatureExtractor` class for text/metadata features
- Build Claude API integration for content analysis
- Extract key phrases, topics, and temporal indicators
- Implement document structure analysis
- Add multi-modal analysis (text, spreadsheets, images with OCR)
- Implement caching for performance
- Handle API rate limiting and errors

### Stream B: Suggestion & Classification Engine
**Scope**: Generate smart categorization suggestions with confidence scoring
**Files**:
- `file_organizer_v2/src/file_organizer/ai/suggestion_engine.py`
- `file_organizer_v2/src/file_organizer/ai/para_classifier.py`
- `file_organizer_v2/src/file_organizer/ai/confidence_scorer.py`
- `file_organizer_v2/src/file_organizer/ai/explainer.py`
**Agent Type**: ml-specialist
**Can Start**: immediately
**Estimated Hours**: 6 hours
**Dependencies**: none

**Tasks:**
- Create `SuggestionEngine` class
- Implement `PARAClassifier` with AI + rule-based hybrid
- Build confidence scoring (0.0-1.0)
- Generate human-readable explanations
- Support batch analysis
- Implement alternative suggestion ranking
- Add subfolder and tag suggestions

### Stream C: Feedback Loop & Learning System
**Scope**: Collect user feedback and improve suggestions over time
**Files**:
- `file_organizer_v2/src/file_organizer/ai/feedback_collector.py`
- `file_organizer_v2/src/file_organizer/ai/feedback_database.py`
- `file_organizer_v2/src/file_organizer/ai/continuous_learner.py`
- `file_organizer_v2/src/file_organizer/ai/pattern_analyzer.py`
**Agent Type**: ml-specialist
**Can Start**: immediately
**Estimated Hours**: 5 hours
**Dependencies**: none

**Tasks:**
- Create `FeedbackCollector` to record user actions
- Build `FeedbackDatabase` for storing feedback
- Implement `ContinuousLearner` for model improvement
- Add pattern recognition from corrections
- Build rule refinement based on feedback
- Implement periodic retraining logic
- Support user-specific personalization

### Stream D: PARA-Aware File Movement
**Scope**: Smart file movement with context preservation
**Files**:
- `file_organizer_v2/src/file_organizer/ai/para_file_mover.py`
- `file_organizer_v2/src/file_organizer/ai/bulk_organizer.py`
- `file_organizer_v2/src/file_organizer/ai/archive_suggester.py`
- `file_organizer_v2/src/file_organizer/utils/link_updater.py`
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4 hours
**Dependencies**: none

**Tasks:**
- Create `PARAFileMover` class
- Implement smart move suggestions
- Build context preservation (update links, maintain relationships)
- Add bulk organization capabilities
- Implement archive suggestion logic
- Create conflict detection and resolution
- Add move history tracking

### Stream E: User Interface Components
**Scope**: UI for displaying suggestions and collecting feedback
**Files**:
- `file_organizer_v2/src/file_organizer/cli/para_suggest_command.py`
- `file_organizer_v2/src/file_organizer/ui/suggestion_display.py`
- `file_organizer_v2/src/file_organizer/ui/feedback_ui.py`
- `file_organizer_v2/src/file_organizer/ui/bulk_organize_ui.py`
**Agent Type**: frontend-specialist
**Can Start**: after Streams A & B reach 30%
**Estimated Hours**: 4 hours
**Dependencies**: Streams A, B (needs suggestion format)

**Tasks:**
- Create CLI command for suggestions
- Build suggestion display with reasoning
- Implement interactive feedback collection
- Add bulk organization UI with preview
- Create progress tracking for batch operations
- Implement approval/rejection workflows

### Stream F: Testing & Integration
**Scope**: Comprehensive testing across all components
**Files**:
- `file_organizer_v2/tests/ai/test_content_analyzer.py`
- `file_organizer_v2/tests/ai/test_suggestion_engine.py`
- `file_organizer_v2/tests/ai/test_feedback_loop.py`
- `file_organizer_v2/tests/ai/test_para_file_mover.py`
- `file_organizer_v2/tests/integration/test_para_suggestions_workflow.py`
- `file_organizer_v2/tests/fixtures/para_suggestions/`
**Agent Type**: qa-specialist
**Can Start**: after Streams A-D reach 50%
**Estimated Hours**: 6 hours
**Dependencies**: Streams A, B, C, D

**Tasks:**
- Accuracy testing with diverse file sets (1000+ files)
- Confidence score calibration validation
- Learning system effectiveness testing
- Performance testing (single file <2s, batch 100 files <30s)
- User experience testing for suggestion clarity
- Integration testing with complete workflow
- Edge case testing (API failures, malformed content)

## Coordination Points

### Shared Files
- `file_organizer_v2/src/file_organizer/ai/models.py` - Streams A, B, C, D (shared data structures)
- `file_organizer_v2/src/file_organizer/ai/__init__.py` - All streams (coordinate exports)

### Shared Data Structures
All streams need agreement on:
- `PARASuggestion` dataclass
- `FeedbackEvent` structure
- `CategoryPrediction` format
- `MoveSuggestion` structure
- `OrganizationReport` format

### Sequential Requirements
1. Streams A, B, C, D can run fully in parallel (independent)
2. Stream E depends on A & B reaching 30% (needs suggestion format)
3. Stream F starts after A-D reach 50% (needs stable APIs)
4. Integration testing requires all development complete

## Conflict Risk Assessment
- **Low Risk**: Streams A-D work on independent modules
- **Medium Risk**: Stream E depends on A & B API design
- **Coordination needed**: Initial data structure design session required

## Parallelization Strategy

**Recommended Approach**: Full parallel with staggered UI and testing

**Phase 1 (Parallel)**: Launch Streams A, B, C, D simultaneously
- All core development proceeds independently
- Teams coordinate on shared data structure definitions
- Wall time: ~7 hours (longest stream)

**Phase 2 (UI Development)**: Start Stream E after Streams A & B reach 30%
- UI development begins with partially complete suggestion engine
- Early prototyping and user feedback
- Wall time: +4 hours (overlaps with Phase 1)

**Phase 3 (Testing)**: Start Stream F after Streams A-D reach 50%
- Integration testing provides early feedback
- Bug fixes fed back to development streams
- Wall time: +6 hours

**Total Wall Time**: ~13 hours (vs 32 hours sequential)

## Expected Timeline

With parallel execution:
- **Wall time**: 13 hours (7h parallel + 4h UI overlap + 6h testing)
- **Total work**: 32 hours (across 6 streams)
- **Efficiency gain**: 59% time reduction

Without parallel execution:
- **Wall time**: 32 hours

## Notes

**Dependencies:**
- Task 007 (Design PARA categorization system) - Required
- Task 008 (PARA folder generation) - Required
- Claude API access configured
- Feedback storage infrastructure

**AI Model Strategy:**
- Primary: Claude API for content analysis (privacy-first, cloud)
- Fallback: Local models for offline mode (reduced accuracy)
- Caching: Aggressive caching for performance
- Privacy: All analysis local-first, cloud optional with consent

**Confidence Levels:**
- **High (0.85-1.0)**: Auto-categorize with notification
- **Medium (0.60-0.84)**: Suggest with user confirmation
- **Low (0.40-0.59)**: Present multiple options
- **Very Low (<0.40)**: Flag for manual review

**Learning Mechanisms:**
1. **Pattern Recognition**: Learn from user corrections
2. **Rule Refinement**: Adjust rule weights based on accuracy
3. **Model Fine-Tuning**: Periodic retraining with feedback
4. **Personalization**: User-specific model adaptation

**Performance Targets:**
- Single file analysis: <2 seconds
- Batch processing (100 files): <30 seconds
- Real-time suggestion latency: <500ms
- Memory usage: <500MB for typical workload

**Privacy Considerations:**
- All content analysis happens locally by default
- Optional cloud enhancement with explicit user consent
- No file content sent to external services without permission
- Clear data usage policies and opt-in/opt-out

**Testing Priorities:**
1. Categorization accuracy (>85% target)
2. Confidence score calibration
3. Learning effectiveness over time
4. Performance under load
5. API failure handling
6. User experience clarity
7. Privacy compliance

**Suggestion Display Example:**
```
┌─────────────────────────────────────────────────┐
│ PARA Suggestion for: project-proposal.docx     │
├─────────────────────────────────────────────────┤
│ Recommended: Projects/Active                   │
│ Confidence: 92%                                │
│                                                │
│ Reasoning:                                     │
│ • Contains deadline mentions (Due: March 15)   │
│ • Active task list with incomplete items       │
│ • Modified 3 times this week                   │
│ • "Proposal" indicates active project          │
│                                                │
│ Alternative: Areas/Professional (35%)          │
│                                                │
│ [Accept] [Choose Different] [Learn More]      │
└─────────────────────────────────────────────────┘
```

**Critical Success Factors:**
- Accuracy: >85% correct categorizations
- Speed: Real-time suggestions (<2s)
- Explainability: Clear reasoning for all suggestions
- Learning: Measurable improvement from feedback
- Privacy: Local-first with optional cloud
- UX: Intuitive and non-intrusive suggestions
