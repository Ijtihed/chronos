# Security policy

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

Instead, email the maintainer at **ijtihedk@gmail.com** with:

- A description of the vulnerability
- Steps to reproduce (or a minimal proof of concept)
- The affected commit / branch
- Your assessment of the impact

You can expect an initial acknowledgement within **7 days**. We aim to ship a
fix or a mitigation within **30 days** of confirmation; longer timelines will
be communicated explicitly.

## Scope

CHRONOS is a single-player, locally-hosted simulation. The realistic threat
surface is small, but reports in the following areas are in scope:

- **Secret leakage** — anything that exposes a user's `GEMINI_API_KEY` or
  other credentials through the running app, logs, or persisted state
- **Remote code execution** — any path from a player input, run import, or
  HTTP request to arbitrary code or shell execution on the host
- **Path traversal / arbitrary file write** — endpoints reading or writing
  outside the project's `data/` directory
- **Cost bypass** — bypassing the per-run cost caps (`COST_CAP_SOFT_EUR`,
  `COST_CAP_HARD_EUR`) so that turns can be submitted indefinitely against
  a user's billed API key
- **SQL injection** in any of the SQLite-backed persistence layers
  (`backend/persistence.py`, `backend/hke/store.py`)

The following are explicitly **out of scope** unless they enable one of the
above:

- Issues that require an attacker to already have shell access on the host
- Denial-of-service via crafted LLM responses (the NoOp fallback is the
  intended mitigation)
- Historical-accuracy disputes about generated narrative content

## Disclosure

Once a fix has shipped, we will credit reporters in the release notes unless
they request to remain anonymous.
