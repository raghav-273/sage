# SAGE API Reference

Base URL: `/api/v1/`
Authentication: `Authorization: Token <token>` (TokenAuthentication) or session cookie (SessionAuthentication).
All endpoints require authentication.

---

## Documents

### Upload a document
POST /api/documents/
Content-Type: multipart/form-data

**Request fields**

| Field | Type | Required | Notes |
|---|---|---|---|
| `file` | File | Yes | PDF only. Maximum 100 MB. |
| `name` | String | No | Display name. Defaults to original filename. |

**Response 202**
```json
{
  "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "RDSO_Spec_T_2024.pdf",
  "status": "QUEUED",
  "page_count": null,
  "chunk_count": 0,
  "error_message": null,
  "created_at": "2026-07-09T10:30:00Z",
  "updated_at": "2026-07-09T10:30:00Z"
}
```

**Error 400** — invalid file type, file too large, or missing file field.

---

### Get document status
GET /api/documents/{document_id}/

Poll this endpoint after upload. The document becomes queryable when `status` is `READY`.

**Status lifecycle:** `PENDING` → `QUEUED` → `EXTRACTING` → `CHUNKING` → `CAPTIONING` → `EMBEDDING` → `READY` | `FAILED`

**Response 200**
```json
{
  "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "name": "RDSO_Spec_T_2024.pdf",
  "status": "READY",
  "page_count": 247,
  "chunk_count": 891,
  "error_message": null,
  "created_at": "2026-07-09T10:30:00Z",
  "updated_at": "2026-07-09T10:34:22Z"
}
```

**Error 404** — document not found.

---

## Question Answering

### Ask a question
POST /api/query/
Content-Type: application/json

The primary retrieval and generation endpoint. Returns a cited answer or an explicit refusal if the documents do not contain sufficient information.

**Request**
```json
{
  "query": "What is the minimum tensile strength for fish plate joints?",
  "document_ids": ["3fa85f64-5717-4562-b3fc-2c963f66afa6"]
}
```

| Field | Type | Required | Notes |
|---|---|---|---|
| `query` | String | Yes | The question. 1–2000 characters. |
| `document_ids` | Array\<UUID\> | No | Restrict retrieval to specific documents. If omitted, searches all READY documents. |

**Response 200 — cited answer**
```json
{
  "query": "What is the minimum tensile strength for fish plate joints?",
  "answer_text": "The minimum tensile strength for fish plate joints is 720 MPa. [CITE:b2d4f891-...]",
  "citations": [
    {
      "chunk_id": "b2d4f891-3b7d-4bad-9bdd-2b0d7b3dcb6d",
      "document_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
      "page_number": 42,
      "section_identifier": "4.3.2",
      "excerpt": "The tensile strength of fish plate joints shall not be less than 720 MPa.",
      "confidence_score": 0.92,
      "retrieval_method": "hybrid",
      "image_path": null
    }
  ],
  "has_valid_citations": true,
  "retrieved_chunk_count": 5,
  "rejected_citation_count": 0
}
```

**Response 200 — refusal (insufficient evidence)**
```json
{
  "query": "What are the fire suppression requirements for rolling stock?",
  "answer_text": "",
  "citations": [],
  "has_valid_citations": false,
  "retrieved_chunk_count": 0,
  "rejected_citation_count": 0
}
```

`has_valid_citations: false` with `retrieved_chunk_count: 0` means no relevant content was found.
`has_valid_citations: false` with `retrieved_chunk_count > 0` means content was retrieved but the model could not produce a citation-grounded answer — treat the response with caution.

**Error 400** — empty or missing `query`.
**Error 503** — generation or retrieval service failure (transient Gemini error, database unavailable, etc.).

**Rate limit:** 8 requests per minute per authenticated user. Exceeding the limit returns HTTP 429.

---

## Response field reference

### Citation object

| Field | Type | Notes |
|---|---|---|
| `chunk_id` | UUID | Internal chunk identifier. Stable for the lifetime of a document. |
| `document_id` | UUID | Source document identifier. |
| `page_number` | Integer | 1-indexed page number in the original PDF. |
| `section_identifier` | String \| null | Parsed clause identifier, e.g. `"4.3.2"`. Null if no heading was detected. |
| `excerpt` | String | The specific text span that supports the answer. |
| `confidence_score` | Float | 0.0–1.0. Derived from retrieval score; not a model confidence estimate. |
| `retrieval_method` | String | `"vector"`, `"keyword"`, or `"hybrid"`. |
| `image_path` | String \| null | Relative path under `/media/` for figure citations. Null for text citations. |

---

## Authentication

**Token authentication** (programmatic access):
Authorization: Token <your-token>

Tokens are provisioned by an operator via the Django admin (`/admin/authtoken/token/`) or the management command:
```bash
docker compose exec web python manage.py drf_create_token <username>
```

**Session authentication** (DRF browsable API):
Navigate to `/api-auth/login/` in a browser and sign in. The browsable API is available at each endpoint URL when accessed from a browser with `Accept: text/html`.

---

## Error format

All 4xx/5xx responses from API endpoints use the following structure:

```json
{
  "error": "Human-readable error message.",
  "code": "MACHINE_READABLE_CODE"
}
```

| Code | HTTP | Meaning |
|---|---|---|
| `INVALID_FILE_TYPE` | 400 | Upload rejected: not a PDF |
| `NO_READY_DOCUMENTS` | 422 | No READY documents available for querying |
| `GENERATION_FAILED` | 503 | Gemini API unavailable or timed out |

DRF validation errors (missing fields, wrong types) use DRF's standard format: `{"field_name": ["error message"]}`.

---

## Known limitations

- `answer_text` in API responses retains raw `[CITE:chunk_id]` citation markers. Rendering (replacing markers with numbered references) is the caller's responsibility. The portal's own rendering logic is in `services/generation/answer_rendering.py` and may be used as a reference.
- There is no streaming endpoint. The entire answer is returned in one response once generation completes. Typical latency is 2–8 seconds per query.
- Rate limits apply per authenticated user account, not per API key. Multiple requests from the same token count against a single shared budget.
- The comparison, compliance, and investigation endpoints are portal-only (HTML/HTMX, no JSON API equivalent). Extend `apps/api/` if programmatic access to those features is required.
