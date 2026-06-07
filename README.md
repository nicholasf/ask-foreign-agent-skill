# ask-foreign-agent-skill

Delegate tasks to a remote autonomous agent runtime (Hermes, Goose ACP). The remote agent receives the task, executes it using its own local tools, and returns the result. No tool proxying — the agent is fully autonomous.

Depends on [load-topology-skill](https://github.com/nicholasf/load-topology-skill) to discover available nodes and their gateway URLs. The topology also defines **agent handles** — the `<machine>-<llm>-<runtime>` names used to address a specific agent, e.g. `pond-qwen-hermes`, `gollum-mistral-goose`.

---

## Examples

Each command takes an **agent handle** — a `<machine>[-<llm>[-<runtime>]]` address that identifies exactly which agent to talk to. Start with just the machine name and add specificity as needed; unspecified parts are filled in from the topology.

### Delegate a task

```
/ask-foreign-agent run pond "Summarise how the auth module works"
```
Agent handle `pond` — machine only. Runtime and model are auto-selected from the topology.

```
/ask-foreign-agent run pond-hermes "Summarise how the auth module works"
```
Agent handle `pond-hermes` — machine and runtime specified, model defaults to whatever Hermes is running on pond.

```
/ask-foreign-agent run pond-qwen3-hermes "Summarise how the auth module works"
```
Agent handle `pond-qwen3-hermes` — machine, LLM family, and runtime all specified.

```
/ask-foreign-agent run pond-qwen3-32b-hermes "Refactor the retry logic and open a PR"
```
Agent handle `pond-qwen3-32b-hermes` — fully qualified: machine `pond`, model `qwen3-32b`, runtime Hermes.

### Sync repo and language state

```
/ask-foreign-agent sync yggd
```

That's it for the common case. The repo is detected from the current git root; language versions are auto-detected from the project's indicator files (`pyproject.toml`, `go.mod`, `package.json`, etc.) and the local runtime versions. The remote agent locates the repo or returns what it needs to catch up.

With an explicit agent handle and repo:

```
/ask-foreign-agent sync yggd-qwen-hermes --repo /home/user/code/my-project
```

Returns structured JSON showing whether the remote has the local HEAD commit and whether language versions match:

```json
{
  "repo_path": "/home/user/code/my-project",
  "sha1_present": true,
  "remote_sha1": "4f9a2c1...",
  "git_commands": [],
  "languages": {
    "python": {"requested": "3.11.0", "found": "3.12.0", "match": false},
    "node":   {"requested": "20.11.0", "found": "20.11.0", "match": true}
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
