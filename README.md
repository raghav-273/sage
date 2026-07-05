<div align="center">

# SAGE
### Standards and Guidelines Engine

**Engineering RAG Platform for Evidence-Backed Technical Standards**

Natural Language Search • Hybrid Retrieval • Verified Citations • Engineering Research

<br>

![Version](https://img.shields.io/badge/Version-v1.0-2ea44f?style=for-the-badge)
![Status](https://img.shields.io/badge/Status-Stable-success?style=for-the-badge)
![Tests](https://img.shields.io/badge/Tests-152%2F152%20Passing-brightgreen?style=for-the-badge)
![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Django](https://img.shields.io/badge/Django-5.x-092E20?style=for-the-badge&logo=django)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=for-the-badge&logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)

</div>

---

SAGE is an engineering research platform that transforms complex technical standards into an evidence-backed search experience.

Built for engineering and government workflows, SAGE combines AI-powered search, hybrid retrieval, asynchronous document processing, and citation-enforced answer generation to help engineers explore large collections of technical documentation with confidence.

Unlike traditional AI chat systems, SAGE prioritizes **trust, traceability, and verifiable evidence**, ensuring every answer can be traced back to its original source.

---

## Tech Stack

| Category | Technologies |
|----------|--------------|
| **Backend** | Django 5, Django REST Framework |
| **Database** | PostgreSQL 16, pgvector |
| **AI** | Gemini, Local Embeddings |
| **Retrieval** | Vector Search, PostgreSQL FTS, Reciprocal Rank Fusion |
| **Background Jobs** | Celery, Redis |
| **Frontend** | Bootstrap 5, HTMX, Vanilla JavaScript |
| **Infrastructure** | Docker Compose, Gunicorn |
| **Testing** | 152 Automated Unit & Integration Tests |

---

## Features

### AI-Powered Engineering Search

- Natural language querying across technical standards
- Hybrid retrieval using semantic embeddings and keyword search
- Reciprocal Rank Fusion (RRF) for improved retrieval quality
- Gemini-powered response generation
- Citation-enforced answers with supporting evidence
- Confidence-aware response rendering

---

### Intelligent Document Processing

- Asynchronous document ingestion pipeline
- PDF parsing and text extraction
- Automatic document chunking
- Figure and diagram extraction
- Vision-based image caption generation
- Local embedding generation
- Background processing with Celery

---

### Research Workflow

- Persistent document research sessions
- Multi-turn document conversations
- Evidence-first answer generation
- Source navigation
- Diagram-aware citations
- Conversation history

---

### Engineering Portal

- Government-style responsive interface
- Document library
- Dashboard with system health monitoring
- Document search and filtering
- Upload status tracking
- Authentication and secure access
- HTMX-powered interactive experience

---

### Reliability

- Citation enforcement for every generated response
- Structured logging across all services
- Redis-backed caching
- Production-ready Docker deployment
- Clean migration history
- Comprehensive automated testing

---

# Architecture

```
                    Documents (PDF)
                           │
                           ▼
                  Async Ingestion Pipeline
                           │
     ┌───────────────┬───────────────┬──────────────┐
     │               │               │              │
     ▼               ▼               ▼              ▼
 PDF Extraction  Figure Extraction Chunking  Vision Captioning
                           │
                           ▼
                  Embedding Generation
                           │
                           ▼
                  PostgreSQL + pgvector
                           │
               Hybrid Retrieval Engine
       (Vector + PostgreSQL FTS + RRF)
                           │
                           ▼
                 Gemini Response Generation
                 + Citation Enforcement
                           │
                           ▼
                    Engineering Portal
```

---

# Technology Stack

## Backend

- Django 5
- Django REST Framework
- PostgreSQL 16
- pgvector
- Celery
- Redis
- Gunicorn

---

## AI & Retrieval

- Gemini
- Local Embedding Models
- Vector Search
- PostgreSQL Full Text Search
- Reciprocal Rank Fusion (RRF)
- Vision-based Figure Captioning

---

## Frontend

- Bootstrap 5
- HTMX
- Vanilla JavaScript

---

## Infrastructure

- Docker Compose
- Environment-based configuration
- Structured logging
- Session authentication
- Cloudflare Turnstile
- Production deployment support

---

# Core Capabilities

- Natural language engineering search
- Evidence-backed AI answers
- Hybrid semantic retrieval
- Figure-aware document understanding
- Engineering document navigation
- Persistent research sessions
- Citation validation
- Confidence scoring
- Background document processing
- Secure authentication

---

# Project Status

## Version

**v1.0 — Engineering RAG Platform**

SAGE v1.0 is feature complete and fully validated.

### Validation

- 152 / 152 automated tests passing
- Unit tests
- Integration tests
- Retrieval validation
- Citation enforcement testing
- Async ingestion testing

---

# Repository Structure

```
apps/
├── api/
├── authentication/
├── chunks/
├── conversation/
├── documents/
├── embeddings/
├── generation/
├── ingestion/
├── retrieval/
└── ...
```

---

# Design Principles

SAGE is built around four core principles.

### Evidence First

Every generated answer is supported by citations.

### Engineering over Chat

The system is designed for professional engineering workflows rather than general conversation.

### Trust through Transparency

Users should always be able to verify where information originated.

### Production-Oriented Architecture

Every major component is designed to operate as an independent service suitable for real deployments.

---

# Current Capabilities

Asynchronous document ingestion
Hybrid vector + keyword retrieval
Citation-enforced AI generation
Figure and diagram extraction
Vision caption generation
Research sessions
Government-style engineering portal
Secure authentication
Docker deployment
Comprehensive automated testing

---

# Roadmap

The current release represents **SAGE v1.0**.

Future development (v2.0) focuses on evolving SAGE from an Engineering RAG Platform into a complete Engineering Knowledge Platform with richer research workflows, document intelligence, and advanced evidence exploration.

---

# License

This repository is intended for educational, research, and engineering demonstration purposes.

---

## SAGE v1.0

**Standards and Guidelines Engine**

*Engineering Knowledge Platform built for trustworthy technical document research.*
