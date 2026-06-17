SAGE Product Vision

SAGE is a multimodal GraphRAG engineering assistant for standards compliance and technical question answering.

Primary users:
Railway engineers, quality assurance teams, and vendors.

Problem:

Engineering specifications are distributed across lengthy PDFs, tables, diagrams, and schematics. Users spend significant time manually locating relevant clauses, resolving conflicting requirements, and cross-referencing diagrams with text.

Goal:

Enable users to ask natural-language questions and receive deterministic, cited answers grounded in engineering documents.

Target documents:

* RDSO specifications
* Technical manuals
* Engineering standards
* CAD schematics
* Inspection procedures

Example queries:

* Which clause governs this component?
* Does this design comply with the specification?
* Which requirements override this section?
* Which diagrams are associated with this rule?
* Summarize all exceptions related to this component.

Why GraphRAG:

Answers frequently depend on relationships between clauses, diagrams, tables, and exceptions rather than isolated text chunks.

Success criteria:

* Process PDFs up to 500 pages.
* Return cited answers within 10 seconds.
* Achieve high retrieval accuracy on a predefined evaluation set.
* Demonstrate clause-to-diagram linking.

MVP scope:

* PDF upload
* Text and image extraction
* Embedding generation
* pgvector storage
* Lightweight knowledge graph
* Hybrid retrieval
* Cited answers

Out of scope:

* Multi-tenancy
* Enterprise security features
* Advanced DevOps infrastructure
* Fine-tuned models
* Distributed deployments