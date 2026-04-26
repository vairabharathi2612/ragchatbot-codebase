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

---

# Frontend Code Quality Changes

## Summary

Added essential code quality tooling to the frontend (`frontend/`) and a root-level quality check script.

---

## New Files

### `frontend/package.json`
Manages frontend dev dependencies. Defines four npm scripts:
- `npm run format` — rewrites all files with Prettier
- `npm run format:check` — checks formatting without modifying files (used in CI)
- `npm run lint` — runs ESLint on `script.js`
- `npm run lint:fix` — auto-fixes ESLint violations where possible
- `npm run check` — runs both `format:check` and `lint` together

### `frontend/.prettierrc`
Prettier configuration:
- Single quotes for JS, double for CSS
- 2-space indentation
- 100 char print width (120 for HTML)
- Trailing commas in ES5 positions
- LF line endings

### `frontend/.eslintrc.json`
ESLint 8 configuration for the browser environment:
- `no-var`: error — enforces `const`/`let`
- `prefer-const`: error — catches unnecessary `let`
- `eqeqeq`: error — bans `==` in favour of `===`
- `no-unused-vars`: warning
- `no-console`: warning (allows `console.error` for error reporting)
- `marked` declared as a global (loaded from CDN in `index.html`)

### `frontend/.prettierignore`
Excludes `node_modules/` from Prettier.

### `check-frontend.sh`
Root-level shell script that runs both Prettier (check mode) and ESLint against the frontend directory. Exit code is non-zero if any check fails, making it suitable for CI integration.

---

## Modified Files

### `frontend/script.js`
- Removed two debug `console.log` statements from `loadCourseStats()` that were flagged by ESLint's `no-console` rule (`'Loading course stats...'` and `'Course data received:'`).
- Applied Prettier formatting: consistent 2-space indentation, single quotes, trailing commas.

### `frontend/index.html`
- Applied Prettier formatting: consistent attribute quoting, indentation.

### `frontend/style.css`
- Applied Prettier formatting: consistent spacing, property order normalisation.

---

## How to Use

```bash
# From the frontend/ directory:
npm run check          # format check + lint (non-destructive)
npm run format         # auto-format all files
npm run lint:fix       # auto-fix lint issues

# From the project root:
./check-frontend.sh    # runs both checks, exits non-zero on failure
```

---

# Frontend Changes: Dark/Light Theme Toggle

## Summary
Added a dark/light theme toggle button to the Course Materials Assistant UI.

## Files Modified

### `frontend/index.html`
- Added an inline `<script>` in `<head>` that reads `localStorage` and sets `data-theme` on `<html>` before the page renders, preventing a flash of the wrong theme on load.
- Added a `<button id="themeToggle" class="theme-toggle">` fixed to the top-right corner, containing two SVG icons: a sun (shown in dark mode to indicate "switch to light") and a moon (shown in light mode to indicate "switch to dark").
- Bumped the CSS/JS cache-busting version query string from `?v=9` to `?v=10`.

### `frontend/style.css`
- **Light theme CSS variables**: Added a `[data-theme="light"]` selector with a full set of overriding CSS custom properties:
  - Background: `#f8fafc` (near-white)
  - Surface: `#ffffff`
  - Text: `#0f172a` (near-black for high contrast)
  - Secondary text: `#64748b`
  - Borders: `#e2e8f0`
  - Assistant message bubble: `#f1f5f9`
  - Shadows: reduced opacity for light backgrounds
- **Dark theme selector**: Changed `:root` to `:root, [data-theme="dark"]` so both the default and explicit dark attribute are covered.
- **`--code-bg` variable**: Introduced this new variable (`rgba(0,0,0,0.25)` dark / `rgba(0,0,0,0.05)` light) and replaced the two hardcoded `rgba(0,0,0,0.2)` values in `.message-content code` and `.message-content pre`.
- **Theme transition**: Added a grouped selector covering all major structural elements (`body`, `.sidebar`, `.chat-messages`, `.message-content`, `#chatInput`, etc.) with `transition: background-color 0.3s ease, color 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease` for smooth switching.
- **Toggle button styles**: Fixed position (top-right), circular (36×36 px), uses `--surface`/`--border-color`/`--text-secondary` variables, hover highlights with `--primary-color`, accessible focus ring via `--focus-ring`, subtle `scale(0.9)` on `:active`.
- **Icon visibility**: `.icon-moon` is hidden by default (dark mode shows sun); under `[data-theme="light"]` the sun is hidden and the moon is shown.

### `frontend/script.js`
- Added `toggleTheme()` function: reads `data-theme` from `document.documentElement`, flips to the opposite value, writes it back, and persists the choice in `localStorage`.
- Wired `toggleTheme` to the `#themeToggle` button's `click` event inside `setupEventListeners()`.

## Behavior
- Theme defaults to **dark** on first visit.
- Preference is persisted in `localStorage` under the key `theme` and restored on every subsequent page load without any visible flash.
- The toggle button is always visible at the top-right corner, is keyboard-navigable (native `<button>`), and has an `aria-label="Toggle theme"` for screen readers.
- All theme color changes animate smoothly over 300 ms.
