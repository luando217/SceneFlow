Graph readability > compactness.

Prefer:
- left → right execution flow
- stable node positions
- grouped execution stages
- visual lanes
- deterministic spacing

Never:
- crossing edges excessively
- random auto-layout
- mixed execution directions
- unrelated nodes in same cluster

Execution stages:
1. ingest
2. preprocessing
3. extraction
4. embedding
5. indexing
6. retrieval
7. reranking
8. reasoning
9. export

Each stage:
- own lane
- own color
- own group
- own minimap region