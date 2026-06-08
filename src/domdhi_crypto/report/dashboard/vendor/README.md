# Vendored third-party assets

These files are committed to the repo and inlined into `dashboard.html` at
generation time (see `dashboard.py`). They are **not** Python dependencies — the
runtime core stays at three deps (requests/pandas/numpy, ADR-007). Per ADR-009
the dashboard ships a single self-contained offline HTML file with no CDN, no
build step, and no server.

## uPlot

| Field | Value |
|-------|-------|
| Files | `uplot.min.js` (IIFE build), `uplot.min.css` |
| Version | **1.6.31** |
| Source | https://github.com/leeoniya/uPlot |
| Fetched from | https://unpkg.com/uplot@1.6.31/dist/uPlot.iife.min.js · https://unpkg.com/uplot@1.6.31/dist/uPlot.min.css |
| License | MIT (© Leon Sorokin) — https://github.com/leeoniya/uPlot/blob/master/LICENSE |
| sha256 (js) | `2d27e8ad3d228164525ce213f9dc716f39b4e3aee0cc773fb3491c96cf4921a2` |
| sha256 (css) | `df630c6a8d6f8eeaff264b50f73ce5b114f646ffd9a0bb74f049b0a00135fa04` |

### Maintenance (ADR-009)

To upgrade: download the pinned version's `uPlot.iife.min.js` + `uPlot.min.css`
from unpkg (or the GitHub release `dist/`), overwrite the two files here, and
update the version + sha256 rows above. The `iife` build is required — it exposes
a global `uPlot` constructor with no module loader, which is what the inlined
`<script>` block relies on. Re-run `pytest tests/test_dashboard.py` to confirm
the inlined-source + offline assertions still pass.
