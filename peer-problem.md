# peer.py — runtime selection problem

## What happened

Attempted to delegate a task to pond via `peer.py --peer-node pond`. Goose ACP (`ws://pond:3284`) was not running. Hermes (`http://pond:8642`) was running and authenticated fine. `peer.py` crashed with `ConnectionRefusedError` rather than falling back to Hermes.

## Root cause

`peer.py` auto-selects the runtime based on topology: if `goose_acp_url` is set it tries Goose, else tries Hermes. There is no:
- Error handling / fallback when the preferred runtime is unreachable
- `--runtime` flag to explicitly choose `hermes` or `goose`

## What we want

Either (or both):

1. **`--runtime` flag** — `peer.py --peer-node pond --runtime hermes "<task>"` bypasses auto-selection and goes straight to the specified runtime.
2. **Automatic fallback** — if Goose connection fails with `ConnectionRefusedError`, catch the exception and fall back to Hermes before giving up.

Option 1 is the explicit, predictable path. Option 2 is the resilient path. Both are useful.

## Relevant code

- Runtime selection: `run_peer()` in `peer.py` lines 90–102
- Goose call: `_run_goose()` — uses `websockets.connect(url)` which raises `ConnectionRefusedError` on failure
- Hermes call: `_run_hermes()` — uses `ChatOpenAI` from langchain_openai
