# Contributing to domdhi.crypto

Thanks for considering a contribution! This is a small, focused project and PRs
are welcome. Please read the design constraints below first — they're what keep
the project worth using.

## Design constraints (please respect these)

1. **No cloud, no telemetry.** Everything runs locally. Nothing about a user's
   holdings, keys, or activity should ever leave their machine.
2. **Indicators stay hand-rolled and auditable.** `ta.py` deliberately depends
   only on `pandas`/`numpy` — **no `pandas-ta`** or other black-box TA libraries
   (they also break on numpy 2.x / Python 3.13). If you add an indicator, write
   the math out and add a test that pins it against an independent reference.
3. **Secrets and holdings are never committed.** `config.local.json`,
   `coins.local.json`, `crypto.db`, and `dashboard.html` are git-ignored. Only the
   `*.example.json` templates ship.
4. **Keep the root tidy.** Library code lives under `src/domdhi_crypto/`, tests
   under `tests/`.

## Dev setup

The repo uses a standard `src/` layout and is installable.

```bash
git clone https://github.com/Domdhi/Domdhi.Crypto domdhi.crypto && cd domdhi.crypto

# with uv (recommended)
uv venv && uv pip install -e . pytest ruff pre-commit

# or with plain pip
python -m venv .venv && source .venv/bin/activate
pip install -e . pytest ruff pre-commit
```

Install the git hooks once:

```bash
pre-commit install
```

## Running things

```bash
ruff check .          # lint (ruff check --fix to autofix)
pytest                # run the test suite
```

The CLI resolves user files from the **current working directory** (or
`$DOMDHI_CRYPTO_HOME`), so run it from a folder containing your `config.local.json`
and `coins.local.json`:

```bash
domdhi-crypto init
python -m domdhi_crypto report   # equivalent module form
```

## Tests

- `tests/test_ta.py` — indicator math, including cross-checks against
  independently-coded textbook RSI/EMA references. **Add a test for any new or
  changed indicator.**
- `tests/test_db.py` — the idempotent-upsert and gap-filling guarantees.
- `tests/test_coingecko.py` — client wiring and 429 backoff (fully mocked; no
  network calls — please keep it that way).

## Submitting a PR

1. Branch off `master`.
2. Make focused changes; keep one logical change per PR.
3. Ensure `ruff check .` and `pytest` pass.
4. Add a line to `CHANGELOG.md` under **Unreleased**.
5. Open the PR and fill in the template. CI runs ruff + pytest on Python
   3.11–3.13.

## Reporting bugs / security issues

Open an issue using the bug template for ordinary bugs. For anything with
security implications, follow [SECURITY.md](SECURITY.md) and report privately.
