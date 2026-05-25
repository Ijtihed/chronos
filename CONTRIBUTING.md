# Contributing to CHRONOS

Thanks for taking the time to look. CHRONOS is a personal/research project,
so contributions are welcome but the bar for merging is "does it fit the
design as it stands today."

## Before you open a PR

1. **Read the design context.** The source of truth lives in
   [`context/game logic context/`](context/game%20logic%20context/) —
   especially `overview.md`, `gameplay.md`, `simulation-and-world.md`, and
   `roadmap.md`. Code serves the design, not the other way around.
2. **Check open questions.** If your change touches anything in
   `context/game logic context/open-questions.md`, that question needs to be
   resolved (in an issue or discussion) before code.
3. **Stay within the current phase.** `context/game logic context/roadmap.md`
   tells you what phase the project is in and what is explicitly **not** in
   scope for that phase.

## Setting up

See the [README](README.md) for the canonical quick-start. In short:

```bash
python3.11 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env              # then fill in GEMINI_API_KEY
python -m pytest tests/ -m "not live" -q
```

## Running tests

- Offline (CI-equivalent): `python -m pytest tests/ -m "not live" -q`
- Live (requires `GEMINI_API_KEY` and burns real API credit):
  `python -m pytest tests/test_live.py -v`

CI runs the offline suite on every push and pull request.

## Coding conventions

- Python 3.11, type hints on new code.
- Keep functions small enough to be tested in isolation; the test suite is
  the contract.
- Every LLM call has a corresponding prompt template in
  [`prompts/`](prompts/). If you add a new call site, add its template in
  the same PR and flag it for review in the PR description.
- Model policy is binding — read
  [`.cursor/rules/chronos-model-tier.mdc`](.cursor/rules/chronos-model-tier.mdc)
  before adding any new LLM call. New call sites need an estimated
  per-run cost contribution in the PR description.

## Commit messages

Short, imperative, prefer one logical change per commit. Examples:

```
fix(map): clamp NPC marker latitude to ±85°
feat(npc): personality-driven flee threshold for survival need
docs(readme): correct default model name
```

## Reporting bugs and proposing features

Open a GitHub issue. For bugs include:

- What you ran and what you expected
- What actually happened (full traceback if there is one)
- The era / seed / approximate turn number if reproducible
- Your `CHRONOS_GEMINI_MODEL` if you've overridden the default

For security issues, see [SECURITY.md](SECURITY.md) — please **do not** open
a public issue.

## License

By contributing you agree that your contributions are licensed under the
project's [MIT License](LICENSE).
