# Security review and deployment checklist

Review of the Streamlit prototype before its first deployment, done on 2026-10-14. It was run against the real app,
not only the code. Re-run the checks below after any change to input handling, rendering or dependencies.

## Attack surface

| Surface | Who controls it | Where it goes |
| --- | --- | --- |
| Pantry text box | visitor | `PantryToPlateService.review_pantry` → rules parser (+ optional LLM) → rendered back as review rows |
| Profile form (diet, allergens, food names, numbers) | visitor | `build_profile` → fuzzy name resolution → hard rules / scorer; notes rendered back |
| Recipe names and steps (Food.com) | third-party dataset | rendered on day cards |
| LLM answers (optional) | model | validated against the user's words / the solver's facts before use |
| Environment (`PTP_*`, `.streamlit/config.toml`) | operator | data dir, LLM endpoint and key, log level and file |

There is no file upload, no database, no `eval`/`exec`, and nothing untrusted is unpickled. The CP-SAT backend starts
`python -I` with an argument list (no shell) and loads its result with NumPy's default `allow_pickle=False`.

## Findings and fixes

| # | Severity | Finding | Fix |
| --- | --- | --- | --- |
| 1 | High (public deployment) | **Resource exhaustion.** No input limits; parsing runs in the shared server process. Measured: 57 KB pantry text = 22 s, 3,000 food names = 42 s of server time | Limits enforced in the service (`MAX_PANTRY_CHARS` 2,000, `MAX_FOOD_NAMES` 40, `MAX_QUERY_CHARS` 100; refused with a clear `ValueError`, never silently truncated) and mirrored as `max_chars` in the UI. Worst allowed input now: 0.13 s / 0.55 s |
| 2 | Medium | **Vulnerable dependencies** (pip-audit against OSV): gitpython 3.1.50 (26 advisories), urllib3 2.7.0 (3), anyio 4.12.1 (2), all pulled in transitively | Upgraded; minimum versions added to `requirements.txt`. Re-audit: no known vulnerabilities |
| 3 | Medium | **Tracebacks shown to visitors** (`client.showErrorDetails = "full"`, the default) reveal file paths and source | `.streamlit/config.toml`: `showErrorDetails = "none"`, `toolbarMode = "viewer"` |
| 4 | Low | **Markdown injection.** Typed text was echoed as Markdown: `![x](https://…)` loaded an outside image, `[x](…)` became a live link (self-only: a visitor sees only their own text) | `ui.logic.md_escape` on every user- or dataset-derived string put into Markdown. It also restores Food.com steps whose stray `<…>` text was being dropped |

Checks that passed:

- **HTML/script injection:** `<script>`, `<img onerror>`, `<svg onload>` and `<iframe>` in every text field were all escaped. Every `unsafe_allow_html` call goes through `ui.theme`, which uses `html.escape`.
- **Secrets:** none in the git history (key and token patterns) and no credential files tracked.
- **Streamlit protections:** cross-site request (XSRF) and CORS protection on (defaults).
- **LLM output:** cannot add markup or links (the paraphrase validator rejects markup characters, and parsed items are re-checked against the user's words).
- **Sessions:** the cached service shared across visitors holds no per-user data.

## Deployment checklist (not solvable in code)

- [ ] **Put the app behind authentication** (Streamlit Community Cloud viewer allow-list, `st.login`, or a reverse
      proxy). Streamlit has none, so anyone with the URL can use it, including a configured LLM.
- [ ] **Rate-limit at the proxy.** Each plan costs up to `DEFAULT_TIME_LIMIT_S` (8 s) of solver CPU. The input limits
      bound one request, not many.
- [ ] **Serve over HTTPS** (TLS at the proxy or the host).
- [ ] **Hosted LLM:** `PTP_LLM_BASE_URL` must be `https://`; the API key is sent as a Bearer header on every request.
      Keep keys in the host's secret store, never in the repo.
- [ ] **Log level `INFO`** in production. At `DEBUG` the log records users' pantry text; protect `PTP_LOG_FILE` if set.
- [ ] **Install from pinned versions** (`pip freeze` of a tested environment, or `pip-compile --generate-hashes`), so
      the deployment gets exactly the audited versions.
- [ ] **Re-run the dependency audit** before each release:
      `pip-audit -r <pinned requirements> --no-deps --disable-pip --vulnerability-service osv`.

## Regression tests

- `tests/app/test_service.py`: oversized pantry text and too many food names are refused; a huge autocomplete query is harmless.
- `tests/ui/test_logic.py`: `md_escape` neutralises links, images, colour directives, emphasis, LaTeX and headings, and is reversible.
- `tests/ui/test_app.py`: typed Markdown and HTML are shown as text on the real page; every text box has `max_chars`.

## Change log

- 2026-10-14 — First review; findings 1-4 fixed; checklist written.
