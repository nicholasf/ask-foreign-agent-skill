# Ask Foreign Agent

Invoke a remote LLM node as an interactive agent. All output is prefixed with `[node-name]`.

## Agent naming convention

Refer to agents as `<machine>-<llm>-agent`, e.g. `dtv-claude-agent`, `pond-qwen-agent`. This makes it clear which machine and which model is acting at each step.

## Before invoking

Read the topology (load-topology-skill) to find the node hostname and verify its inference server is active:

```bash
curl -s http://<hostname>:9337/v1/models
```

Set `$FOREIGN_AGENT_URL` and `$FOREIGN_AGENT_MODEL` to target the node.

---

## Bridge mode — local (default)

**dtv-claude-agent** drives **pond-qwen-agent** via HTTP. Tool calls execute on the orchestrating machine (dtv). Use when working against the local codebase.

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/agent.py" \
  --cwd <working directory> \
  "<message>"
```

### Toolset

| Tool | Description |
|---|---|
| `read_file` | Read a file by path |
| `write_file` | Write content to a file |
| `edit_file` | Replace an exact string in a file |
| `bash` | Run a bash command in the working directory |
| `find_files` | Find files by name pattern |
| `grep` | Search for a pattern across files |
| `list_directory` | List directory tree |
| `git_diff` | Show unstaged and staged changes |

---

## Bridge mode — SSH

**dtv-claude-agent** drives **pond-qwen-agent** via HTTP. Tool calls execute on the remote node via SSH. Use when the remote node has the repo and toolchain but no agent runtime (Hermes). `$AGENT_SSH_USER` must be set.

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/agent.py" \
  --cwd <local working directory> \
  --ssh-node <hostname> \
  --ssh-cwd <remote working directory> \
  "<message>"
```

In SSH mode only `bash` is exposed — commands execute on the remote node via SSH.

---

## Peer mode — agent to agent (requires Hermes on remote node)

**dtv-claude-agent** sends a task to a remote agent runtime (e.g. Hermes running **pond-qwen-agent**). The remote agent executes autonomously using its own local tools and returns a result. No SSH proxying, no middleware loop from dtv.

**Prerequisite:** Hermes must be installed and running on the remote node, configured to use the node's local LLM endpoint.

Implementation pending — Hermes setup on pond in progress.

---

## Output format

- `[node-name] ...` — text response
- `[node-name:tool:tool_name] ...` — tool call
- `[node-name:result] ...` — tool result (truncated if long)

## Triggers

Invoke when the user says "ask [node]", "what does [node] think", or "let [node] look at this".
