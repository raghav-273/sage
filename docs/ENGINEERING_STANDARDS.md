SAGE Engineering Standards

Project Objective

Build an internship-scale MVP that demonstrates advanced engineering document intelligence capabilities while maintaining production-inspired software engineering practices.

The project will be evaluated primarily on functionality, reliability, explainability, and architectural clarity.

⸻

Functional Standards

The system must:

* Accept PDF uploads up to 500 pages.
* Extract text, tables, and embedded images.
* Generate semantic embeddings.
* Store embeddings using PostgreSQL with pgvector.
* Build relationships between clauses, tables, and diagrams.
* Support natural-language question answering.
* Return answers with explicit citations.

Answers without citations are considered failures.

⸻

Retrieval Standards

The system must:

* Combine semantic and keyword retrieval.
* Support graph-based context expansion.
* Retrieve relevant content within 10 seconds.
* Achieve at least 80% accuracy on a manually curated evaluation dataset of 20 engineering questions.

⸻

Explainability Standards

Every answer must include:

* Source document name
* Page number
* Relevant clause or section identifier
* Confidence score

Users must be able to verify every generated answer.

⸻

Engineering Standards

The codebase must:

* Follow a modular architecture.
* Separate ingestion, retrieval, and generation responsibilities.
* Include type hints.
* Include docstrings for public methods.
* Use environment variables for secrets.
* Include unit tests for core services.
* Use Docker Compose for reproducible deployment.

No hard-coded secrets are permitted.

⸻

MVP Constraints

The following capabilities are intentionally excluded:

* Multi-tenancy
* Kubernetes
* Advanced RBAC
* Immutable audit ledgers
* Distributed rate limiting
* Field-level encryption
* Cross-encoder reranking
* Zero-trust security architecture
* Real-time streaming

These features may be proposed as future work but must not delay MVP delivery.

⸻

Performance Standards

Target metrics:

* PDF ingestion time: under 5 minutes for a 300-page document
* Query response time: under 10 seconds
* System uptime during demonstration: 100%
* Successful processing rate: above 95%

Reliability is prioritized over optimization.

⸻

Demonstration Standards

The final demo must show:

1. Uploading an engineering document.
2. Automatic ingestion and indexing.
3. Asking a compliance question.
4. Retrieving related clauses and diagrams.
5. Returning a cited answer.
6. Displaying graph relationships.

A simple, reliable demonstration is preferred over advanced but unstable features.

⸻

Decision Framework

When selecting between multiple approaches:

1. Prefer simplicity over complexity.
2. Prefer reliability over optimization.
3. Prefer explainability over model sophistication.
4. Prefer demonstrable features over infrastructure sophistication.
5. Prefer completion over completeness.