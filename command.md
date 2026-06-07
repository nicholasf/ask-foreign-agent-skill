# Ask Foreign Agent

Delegate a task to a remote autonomous agent runtime (Hermes, Goose). The
remote agent receives the task, executes it using its own local tools, and
returns the result. No tool proxying — the agent is fully autonomous.

All output is prefixed with `[node-name]`.

## Agent naming convention

Refer to agents as `<machine>-<llm>-<runtime>`, e.g. `pond-qwen-hermes`,
`pond-qwen-goose`, `gollum-mistral-hermes`. This makes it unambiguous which
machine, model, and runtime is acting. The node argument to both subcommands
follows this convention — omit parts you don't need and defaults are applied.

## Before invoking

1. Load the topology (load-topology-skill) — this sources `$SKILLS_HOME/.env`
   and reads `topology.md`.
2. Confirm the target node has a `hermes_gateway` or `goose_acp_url` entry.
3. Verify the gateway is reachable:

```bash
# Hermes
curl -s -H "Authorization: Bearer $<NODE>_HERMES_KEY" http://<hostname>:8642/v1/models

# Goose — a 404 with acp headers confirms the server is up
curl -sv http://<hostname>:3284/ 2>&1 | grep "acp-connection-id"
```

---

## Subcommands

### run — delegate a task

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/peer.py" \
  run <node> "<task>"
```

`<node>` is `<machine>[-<llm>[-<runtime>]]`, e.g. `pond`, `pond-qwen-hermes`,
`pond-qwen-goose`. The gateway URL and Bearer token are read automatically from
`topology.md` and `$SKILLS_HOME/.env`.

### sync — negotiate repo and language state

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/peer.py" \
  sync <node> [--repo /path/to/repo] [--lang python=3.11]
```

`--repo` defaults to the git root of the current working directory. `--lang`
defaults to auto-detection from indicator files (`pyproject.toml`, `go.mod`,
`package.json`, etc.) and local runtime versions — no flags required for the
common case.

Reads the local repo's current branch and HEAD SHA1, sends them to the remote
agent along with detected language versions, and returns a JSON report:

```json
{
  "repo_path": "/home/user/repo",
  "sha1_present": true,
  "remote_sha1": "<HEAD at repo_path>",
  "git_commands": [],
  "languages": {
    "python": {"requested": "3.11", "found": "3.12.0", "match": false}
  }
}
```

If `sha1_present` is false, `git_commands` contains the steps to bring the
remote up to date. The remote agent can act on the report autonomously.

---

## Supported agent runtimes

| Runtime | Setup guide | topology columns |
|---|---|---|
| Hermes | `docs/agents/hermes.md` | `hermes_gateway`, `hermes_key_env` |
| Goose | `docs/agents/goose.md` | `goose_acp_url` |

---

## Output format

- `[node-name] ...` — agent response

## Triggers

Invoke when the user says "ask [node]", "delegate to [node]", "let [node]
handle this", or "what does [node] think". For direct LLM interaction without
an agent runtime, use ask-foreign-llm-skill instead.
