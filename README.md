# ask-foreign-agent-skill

Delegate tasks to a remote autonomous agent runtime (Hermes, Goose ACP). The remote agent receives the task, executes it using its own local tools, and returns the result. No tool proxying — the agent is fully autonomous.

Depends on [load-topology-skill](https://github.com/nicholasf/load-topology-skill) to discover available nodes and their gateway URLs.

---

## Examples

### Invoke as a skill (natural language)

```
ask the foreign agent on pond to summarise the auth module
```

```
delegate to pond-qwen-agent: refactor the retry logic and open a PR
```

```
let gollum handle this — run the test suite and report failures
```

### Delegate a task (`run`)

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/peer.py" \
  run --peer-node pond "Summarise how the auth module works"
```

Output is prefixed with `[pond]`:

```
[pond] The auth module uses JWT tokens issued at login...
```

### Force a specific runtime

```bash
# Use Hermes (HTTP) explicitly
peer.py run --peer-node pond --runtime hermes "What models are loaded?"

# Use Goose ACP (WebSocket) explicitly
peer.py run --peer-node pond --runtime goose "Run the test suite"
```

Default is `auto`: prefers Goose if `goose_acp_url` is set, falls back to Hermes on connection failure.

### Sync repo and language state (`sync`)

Ask the remote agent whether it has the local HEAD commit and the expected language versions:

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/peer.py" \
  sync \
  --peer-node pond \
  --repo /home/user/code/my-project \
  --lang python=3.11 \
  --lang node=20
```

Returns structured JSON:

```json
{
  "repo_path": "/home/user/code/my-project",
  "sha1_present": true,
  "remote_sha1": "4f9a2c1...",
  "git_commands": [],
  "languages": {
    "python": {"requested": "3.11", "found": "3.12.0", "match": false},
    "node":   {"requested": "20",   "found": "20.11.0", "match": true}
  }
}
```

If `sha1_present` is `false`, `git_commands` lists the steps to bring the remote up to date. The remote agent can act on the report autonomously.

---

## Supported runtimes

| Runtime | Protocol | Topology columns | Setup |
|---|---|---|---|
| Hermes | HTTP (OpenAI-compatible) | `hermes_gateway`, `hermes_key_env` | `docs/agents/hermes.md` |
| Goose ACP | JSON-RPC 2.0 over WebSocket | `goose_acp_url` | `docs/agents/goose.md` |

---

## Topology dependency

The topology file (managed by [load-topology-skill](https://github.com/nicholasf/load-topology-skill)) is the source of truth for which nodes are available and how to reach them. Before invoking a foreign agent, load the topology to confirm the target node is online.

Example topology entry for `pond`:

```
| pond | http://pond:8642 | POND_HERMES_KEY | ws://pond:3284 |
```

Gateway URLs and API keys are read automatically from `topology.md` and `$SKILLS_HOME/.env`.

---

## Security

Delegating to a remote agent grants it autonomous execution on the target node. Before use:

- The LLM is not sandboxed. Adversarial prompt content (including content read from source files) could cause destructive commands to execute on the remote node.
- Review all results — diffs, branches, PRs — before merging or applying. Never auto-merge remote agent output.
- Use a dedicated agent user with restricted permissions where possible. Prefer nodes that are not shared with production workloads.

---

## Setup

```bash
cd "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill"
uv sync
```

Dependencies: `langchain-core`, `langchain-openai`, `websockets`.
