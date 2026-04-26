# Testing Framework Changes

## Files Modified

### `pyproject.toml`
- Added `httpx>=0.28.0` to `[dependency-groups] dev` (required by starlette's TestClient).
- Added `[tool.pytest.ini_options]` section:
  - `testpaths = ["backend/tests"]` — pytest discovers tests here when run from project root.
  - `pythonpath = ["backend"]` — makes `backend/` importable without manual `sys.path` manipulation.
  - `addopts = "-v"` — verbose output by default.

### `backend/tests/conftest.py`
Added three shared fixtures available to all test modules:
- `mock_rag_system` — fully mocked `RAGSystem` with pre-configured return values for `session_manager.create_session`, `query`, and `get_course_analytics`. No ChromaDB, embedding model, or Anthropic API needed.
- `sample_course_titles` — list of course title strings for test data setup.
- `sample_query_text` — a sample query string fixture.

## Files Created

### `backend/tests/test_api_endpoints.py`
API endpoint tests for `POST /api/query` and `GET /api/courses`.

**Approach**: A self-contained test app (`build_test_app`) is defined inline in this file. It mirrors the routes from `app.py` without mounting the frontend static files (`../frontend`), which avoids the `StaticFiles` import failure and the module-level `RAGSystem(config)` initialization that require external services.

**`TestQueryEndpoint` (16 tests)**:
- 200 response with correct fields (`answer`, `sources`, `session_id`)
- Session creation when no `session_id` is provided
- Session reuse when `session_id` is provided in the request
- `rag_system.query` called with the correct query and session arguments
- Source propagation (multiple, empty)
- 500 returned with error detail when `RAGSystem.query` raises
- 422 returned for missing `query` field
- Response `Content-Type` is `application/json`

**`TestCoursesEndpoint` (12 tests)**:
- 200 response with correct fields (`total_courses`, `course_titles`)
- Type checks (int, list)
- Values match mock analytics
- `get_course_analytics` called exactly once per request
- 500 returned with error detail when analytics raises
- Edge cases: empty catalog, large catalog (100 courses)
