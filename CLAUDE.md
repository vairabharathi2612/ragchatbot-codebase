# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the Application

Always use `uv` to manage all dependencies — never `pip` directly.

```bash
# Install dependencies (from project root)
uv sync

# Start the server (from project root)
./run.sh

# Or manually
cd backend && uv run uvicorn app:app --reload --port 8000
```

Requires a `.env` file in the project root with `ANTHROPIC_API_KEY=...`. The server starts at `http://localhost:8000`.

## Architecture

The backend lives entirely in `backend/` and is started from that directory — all relative paths (ChromaDB at `./chroma_db`, docs at `../docs`) are relative to `backend/`.

**Request flow for `POST /api/query`:**
1. `app.py` receives the request, creates a session if needed, delegates to `RAGSystem.query()`
2. `rag_system.py` fetches conversation history from `SessionManager`, then calls `AIGenerator.generate_response()` with the search tool attached
3. `ai_generator.py` calls Claude (Round 1) with `tool_choice: auto`. If Claude issues a `tool_use`, it executes `CourseSearchTool.execute()` and calls Claude again (Round 2) with the results — this second call has no tools
4. `search_tools.py` → `vector_store.py` → ChromaDB performs a semantic search over the `course_content` collection, optionally filtered by `course_title` and/or `lesson_number`
5. Sources collected from the tool are returned alongside the answer; the exchange is saved to `SessionManager`

**Two ChromaDB collections:**
- `course_catalog` — one document per course (title, instructor, link, lessons JSON). Used only for fuzzy course name resolution via `_resolve_course_name()`.
- `course_content` — one document per chunk with metadata `{course_title, lesson_number, chunk_index}`. This is what all semantic search runs against.

**Document format expected in `docs/`:**
```
Course Title: ...
Course Link: ...
Course Instructor: ...

Lesson 0: Title
Lesson Link: ...
[content]

Lesson 1: Title
...
```
Documents are ingested on server startup via `add_course_folder()`, which skips courses already present in ChromaDB by title.

## Key Configuration (`backend/config.py`)

| Setting | Default | Effect |
|---|---|---|
| `ANTHROPIC_MODEL` | `claude-sonnet-4-20250514` | Claude model used for generation |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence Transformers model for embeddings |
| `CHUNK_SIZE` | `800` | Max chars per chunk |
| `CHUNK_OVERLAP` | `100` | Overlap chars between chunks |
| `MAX_RESULTS` | `5` | Top-K chunks returned per search |
| `MAX_HISTORY` | `2` | Conversation turns kept in session (stores `MAX_HISTORY * 2` messages) |
| `CHROMA_PATH` | `./chroma_db` | ChromaDB persistence path (relative to `backend/`) |

## Adding a New Tool

1. Subclass `Tool` in `backend/search_tools.py`, implement `get_tool_definition()` and `execute()`
2. Register it in `RAGSystem.__init__()` via `self.tool_manager.register_tool(your_tool)`

Claude will automatically have access to it via `tool_choice: auto`. If the tool should expose sources to the UI, add a `last_sources: list` attribute — `ToolManager.get_last_sources()` checks all registered tools for this attribute.
