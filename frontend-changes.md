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
