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
