#!/usr/bin/env bash
set -euo pipefail

FRONTEND_DIR="$(cd "$(dirname "$0")/frontend" && pwd)"

echo "=== Frontend Quality Checks ==="
echo ""

cd "$FRONTEND_DIR"

echo "--- Prettier (format check) ---"
npx prettier --check .
echo ""

echo "--- ESLint (lint) ---"
npx eslint script.js
echo ""

echo "All frontend quality checks passed."
