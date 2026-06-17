Project: SAGE MVP

Duration: 4 weeks

Goal:
Build a multimodal GraphRAG system for engineering documents.

Primary user flow:
Upload PDF → Extract text/images → Generate embeddings → Build graph → Retrieve context → Generate cited answers.

Tech stack:
- Django 5
- Django REST Framework
- PostgreSQL 16 + pgvector
- Celery
- Redis
- Docker
- PyMuPDF
- OpenCV
- OpenAI/Gemini embeddings

Out of scope:
- Multi-tenancy
- Zero-trust security
- Audit ledger
- Distributed rate limiting
- Field-level encryption
- Kubernetes
- Cross-encoder reranking
- Advanced RBAC
- Channels/SSE

Definition of done:
- End-to-end working demo
- Dockerized deployment
- API documentation
- Evaluation dataset with sample queries