# Security Policy

## Reporting a vulnerability

Please report security issues **privately** — do not open a public issue for
anything with security implications.

- Preferred: open a private advisory via GitHub →
  **Security → Advisories → Report a vulnerability**
  (<https://github.com/Domdhi/Domdhi.Crypto/security/advisories/new>).
- Alternatively, email the maintainer (see the commit author address).

Please include reproduction steps and the impact you're concerned about. You'll
get an acknowledgement as soon as possible, and a fix or mitigation plan after
triage.

## Scope & threat model

This is a **local-first** tool. By design:

- Your **API key** lives only in `config.local.json`, and your **holdings** only
  in `coins.local.json`. Both are git-ignored — they never leave your machine and are
  never sent anywhere except, in the API key's case, to CoinGecko's own API over
  HTTPS.
- `crypto.db` and `dashboard.html` are generated locally and git-ignored.
- There is no server, no account, and no telemetry.

The most likely real-world risks are therefore **accidental disclosure**
(committing a secret, pasting a key into an issue) rather than remote compromise.

## Good hygiene

- Never commit `config.local.json` or `coins.local.json`. The provided `.gitignore`
  excludes them; double-check before `git add -A`.
- Scrub command output before pasting it into issues or PRs.
- Rotate your CoinGecko key any time — it only lives in `config.local.json`.
- Prefer a **Demo** key; it's sufficient for this tool and is lower-privilege.
