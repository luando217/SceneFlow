# .clinerules

```md
# RULE 0 — TOOL LOCK DEFAULT (MUST BE ENFORCED)
# =============================================
# FORBIDDEN TOOLS (unless explicitly unlocked in task prompt):
# - search_files / grep / regex / pattern search
# - find_symbol / find references / go to definition
# - function search / method search / class search
# - symbol lookup / reference lookup / identifier lookup
# - cross reference / dependency lookup
# - code index lookup / workspace index query
# - repository exploration / folder exploration / directory exploration
# - auto locate / auto discovery / any tool-assisted code location
# - ANY tool that locates code by name or uses symbol/reference index
#
# FOR AUDIT TASKS:
# - Only use read_file tool
# - Only read physically visible blocks
# - No code location by name
# - No symbol index lookup
# - No reference index lookup
#
# Expected metrics for audit tasks:
# - Search Count = 0
# - Pattern Search Count = 0
# - Repository Exploration = 0
# - Symbol Lookup Count = 0
# - Reference Lookup Count = 0
#
# If any forbidden tool is attempted:
# 1. STOP immediately
# 2. Log "RULE 0 VIOLATION"
# 3. Continue with allowed tools only
# =============================================

PATCH MODE ONLY.

Read minimal code only.

Never refactor entire architecture.
Never rewrite stable systems.
Never move modules unless required.

Preserve:
- grouped export
- UI layout
- async pipeline
- execution graph
- node architecture
- cache behavior
- observability
- retrieval ordering

System philosophy:
This is not a normal AI app.
This is a local-first modular AI operating system.

Architecture priorities:
1. execution correctness
2. inspectability
3. graph readability
4. reproducibility
5. modular isolation
6. partial re-execution
7. provenance tracking
8. UI consistency
9. retrieval quality
10. visual polish

Always preserve:
- deterministic graph behavior
- stable node positions
- execution traceability
- cache lineage
- node contracts
- workflow serialization
- dock layout consistency

Avoid:
- monolithic rewrites
- giant UI rewrites
- spaghetti event systems
- hidden side effects
- implicit state mutations
- brute-force reruns
- cosine-only retrieval
- random graph auto-layout

Execution model:
- DAG-based execution
- async queue system
- partial downstream rerun only
- node-level cache
- node isolation
- traceable execution spans

Node architecture:
Each module must behave like isolated node runtime.

Each node should define:
- node_id
- category
- input schema
- output schema
- async support
- cache strategy
- retry policy
- debug serializer
- execution metadata

Node categories:
- SOURCE
- PREPROCESS
- DETECTOR
- TAGGER
- EMBEDDER
- RETRIEVER
- RERANKER
- MEMORY
- REASONER
- EXPORT
- DEBUG
- CACHE
- CONTROL

Graph layout rules:
- left → right flow
- execution lanes
- grouped stages
- stable spacing
- minimal edge crossing
- deterministic positioning

Execution stages:
1. ingest
2. preprocessing
3. scene segmentation
4. frame sampling
5. tagging
6. OCR/ASR
7. embeddings
8. indexing
9. retrieval
10. reranking
11. reasoning
12. export
13. observability

UI/UX rules:
UI consistency > fancy visuals.

Never place controls randomly.

Dock layout:
LEFT:
- node library
- workflow templates
- assets

CENTER:
- graph canvas

RIGHT:
- inspector
- node state
- metadata
- execution trace

BOTTOM:
- logs
- queue
- terminal
- cache state

FLOATING:
- preview
- retrieval compare
- embedding inspector

Debug philosophy:
Every failure must be inspectable.

Every node should expose:
- last input
- last output
- cache status
- execution duration
- upstream dependencies
- downstream impact
- error reason

Observability:
Use trace-first architecture.

All important operations should expose:
- trace_id
- workflow_id
- node_id
- scene_id
- model_version
- embedding_version
- retrieval_version

Semantic retrieval rules:
Scene retrieval is NOT timeline stitching.

Prioritize:
- entity overlap
- action overlap
- visual tag overlap
- temporal continuity
- nearby future scenes
- reranking fusion

Avoid:
- intro/outro overmatching
- reused scenes
- cosine-only matching
- isolated frame reasoning

Retrieval architecture:
Always prefer hybrid retrieval:
- BM25
- dense vectors
- graph traversal
- temporal reranking
- metadata filters

Anime-specific rules:
Prefer structured metadata over prose.

Preferred extraction:
- characters
- actions
- emotions
- objects
- environment
- OCR
- dialogue
- timestamps

Avoid:
- poetic descriptions
- lore generation
- atmosphere writing
- hallucinated objects

Temporal memory rules:
Narrative continuity matters.

Track:
- entity state changes
- relationship changes
- temporal validity
- scene continuity
- story arcs

Plugin system:
Plugins must never mutate global runtime state.

Plugins should be:
- sandboxed
- typed
- versioned
- traceable
- cache-aware

Code generation style:
Prefer:
- minimal patches
- modular code
- explicit state
- isolated services
- debug-friendly systems

Avoid:
- magic abstractions
- giant manager classes
- hidden dependency injection
- tightly coupled UI logic

Always return:
1. probable issue
2. execution impact
3. minimal patch plan
4. raw code only
```

---

# PROJECT_CONTEXT.md

```md
# PROJECT_CONTEXT

Project name:
Semantic Anime Retrieval OS

Project type:
Local-first modular AI operating system.

Main goal:
Build a node-based semantic video retrieval engine for anime/movie recap workflows.

Core workflow:
1. ingest video
2. detect scenes
3. sample keyframes
4. extract OCR/ASR
5. generate anime tags
6. create embeddings
7. build retrieval indexes
8. semantic retrieval
9. reranking
10. reasoning
11. grouped export

Primary philosophy:
Execution-first architecture.

The system must always prioritize:
- inspectability
- reproducibility
- graph readability
- modular isolation
- observability
- deterministic behavior

This is NOT:
- a chatbot
- a simple RAG app
- a monolithic AI tool

This IS:
- a modular graph runtime
- a semantic retrieval workstation
- a local AI orchestration system

Primary architectural inspirations:
- ComfyUI
- Flowise
- Graphiti
- Langfuse
- VideoRAG
- VideoITG
- VFX node editors
- Houdini/Nuke-style workflows

Core architecture:

Frontend:
- graph editor
- dockable workspace
- execution inspector
- retrieval debugger

Backend:
- Python async DAG runtime
- modular worker system
- traceable execution engine

Retrieval:
- hybrid retrieval
- BM25
- dense vectors
- temporal reranking
- graph traversal

Memory:
- narrative-aware graph memory
- temporal relationships
- entity evolution

Observability:
- OpenTelemetry
- Langfuse tracing
- node-level debugging

Execution principles:
- partial downstream rerun
- node-level caching
- async queues
- deterministic execution
- reproducible workflows

UI principles:
- workspace ergonomics
- graph readability
- grouped stages
- stable layouts
- inspector-first UX

Graph organization:
Graph should follow left → right execution.

Recommended lanes:
1. ingest
2. segmentation
3. extraction
4. embeddings
5. indexing
6. retrieval
7. reranking
8. reasoning
9. export
10. debug/observability

Required dock panels:
- graph canvas
- node library
- execution trace
- logs
- queue
- inspector
- retrieval compare
- embedding inspector
- memory graph
- preview viewer

Semantic extraction strategy:
Prefer structured extraction over prose.

Target schema:
- character
- action
- emotion
- magic
- environment
- objects
- OCR
- ASR
- timestamps

Anime tagging:
Use WD14-style structured anime tags.

Avoid:
- prose captions
- atmospheric writing
- hallucinated lore

Retrieval philosophy:
Scene retrieval is NOT frame similarity.

Important signals:
- entity overlap
- action overlap
- visual overlap
- temporal continuity
- dialogue continuity
- nearby chronological relevance

Known problems:
- reused scenes
- intro/outro overmatching
- long-context drift
- retrieval hallucination
- graph spaghetti
- plugin instability

Scaling concerns:
- vector DB growth
- retrieval latency
- cache invalidation
- graph readability
- plugin compatibility
- async synchronization

Future goals:
- reusable workflow templates
- graph serialization
- workflow replay
- provenance-aware exports
- multi-model evaluation
- semantic timeline editing
- automatic scene graph generation

Code style:
- modular
- typed
- inspectable
- execution-safe
- cache-aware
- traceable

Never prefer:
- giant rewrites
- hidden state
- random UI placement
- monolithic managers
- implicit execution

Preferred stack:
- Python
- PySide6 or dockable desktop shell
- React Flow style graph UI
- Qdrant/LanceDB
- Ollama
- OpenTelemetry
- Langfuse
- async workers

End goal:
A production-grade semantic video operating system with modular graph execution, narrative-aware retrieval, and fully inspectable local AI workflows.
```
