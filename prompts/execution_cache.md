Cache upstream AI stages aggressively.

Prompt changes should not invalidate:
- frame extraction
- OCR
- embeddings
- tagging
- motion analysis

Prefer dependency-aware cache invalidation.