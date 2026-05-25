# Test status

> Living document. Update when the quarantine list shrinks.

## Headline

- **Offline pytest suite** (`pytest -m "not live"`): **834 passed, 5 xfail,
  3 skipped, 13 deselected** — currently green on CI.
- **Live tests** (`pytest tests/test_live.py`): require a real
  `GEMINI_API_KEY`; not run in CI; burn a small amount of API credit.

## Quarantined (`xfail`)

The 5 tests below all date from the pre-2026-04-23 era when the action
parser routed through a local Ollama instance. They mock the Ollama HTTP
endpoint with `respx`. After the [all-Gemini migration](../.cursor/rules/chronos-model-tier.mdc),
those mocks no longer intercept anything — the parser calls Gemini, sees
no key in CI, and falls through to the NoOp `"..."` response. So the
canned `FAKE_TRAVEL_ACTION` fixtures never reach the parser, travel never
fires, and these assertions go red.

| Test | Root cause |
|---|---|
| `tests/test_api.py::TestUnifiedTurn::test_travel_via_turn` | Ollama mock, parser is Gemini |
| `tests/test_phase1.py::TestUnifiedTurnTravel::test_travel_changes_location` | Ollama mock, parser is Gemini |
| `tests/test_phase1.py::TestUnifiedTurnTravel::test_travel_returns_info` | Ollama mock, parser is Gemini |
| `tests/test_map_integration.py::TestTravelUpdatesMarkers::test_travel_adds_destination_to_visited` | Ollama mock, parser is Gemini |
| `tests/test_divergence_e2e.py::TestDivergenceE2E::test_prevent_sack_of_rome_registers_divergence` | `historical_events` table empty in CI (`build_events_db.py` is not run — it hits Wikidata SPARQL) |

## How to un-quarantine

Two repairs are needed:

### 1. Port LLM mocks to Gemini

The cleanest path is a `conftest.py` fixture that monkeypatches
`backend.llm_provider.call_llm` to return canned `(text, UsageInfo|None)`
tuples keyed by `call_site`. This makes the tests provider-agnostic
going forward.

A heavier-weight option is to keep `respx` and mock the `google-genai`
SDK's HTTP endpoint. Be aware that the SDK's request shape and retry
behavior are implementation details that may move under you.

Once mocks land, remove the `xfail` markers on the four travel-related
tests above.

### 2. Seed minimum canonical events for divergence

For `test_prevent_sack_of_rome_registers_divergence`, add a fixture that
inserts the small set of Roman canonical events the test depends on
(notably `Sack of Rome 410`). A JSON seed under `seeds/` plus an
`asyncio` fixture that calls `insert_historical_event` should be enough.

Avoid pulling in `build_events_db.py` for CI — it makes live Wikidata
SPARQL + Wikipedia calls and is the wrong shape for unit tests.

## Why these are `xfail` and not `skip`

`xfail(strict=False)` keeps the tests visible in pytest output (they show
up under "expected failures") rather than silently disappearing. If
either repair lands and the test starts passing, it will surface as
`XPASS`, which is the trigger to remove the marker.
