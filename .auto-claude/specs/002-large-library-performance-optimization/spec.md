# Large Library Performance Optimization

Optimize the database layer, file scanning pipeline, and AI processing queue to handle directories with 50,000-100,000+ files without degradation. Add database indexing for common queries, implement chunked/streaming file listing, optimize SQLAlchemy query patterns, and add caching for repeated metadata lookups. Publish benchmarks comparing performance against competitor tools.

## Rationale
Performance at scale is the #1 recurring pain point across competitors. TagSpaces becomes unusable at hundreds of tags (pain-3-1), Hazel degrades with hundreds of rules (pain-1-3), and TagStudio's search is broken entirely (pain-5-1). Winning on performance with large libraries is a massive differentiator. The current SQLite-backed metadata store needs optimization to deliver on this promise.

## User Stories
- As a power user with 80,000 files across my documents and media folders, I want the tool to scan and organize them without freezing or taking hours
- As a creative professional with a large media library, I want search to return results instantly even with thousands of tagged files

## Acceptance Criteria
- [ ] Scanning a directory with 50,000 files completes initial indexing within 60 seconds
- [ ] File listing API responds within 200ms for paginated requests regardless of total file count
- [ ] Duplicate detection on 10,000 files completes within 5 minutes
- [ ] BM25 search returns results within 500ms for libraries with 100,000+ indexed files
- [ ] Memory usage stays below 500MB during batch processing of 50,000 files
- [ ] Database queries use proper indexes — no full table scans for common operations
- [ ] Published benchmark comparison document shows performance vs. competitor tools
