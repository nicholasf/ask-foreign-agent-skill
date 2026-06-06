---
name: ask-foreign-agent
description: Run a remote LLM node as an interactive agent. Supports bridge mode (proxied local tool calls) and peer mode (remote agent clones the repo and works autonomously via SSH). Depends on load-topology-skill to identify available nodes.
depends_on:
  - load-topology-skill
---

# Foreign Agent

Invoke an LLM node from the topology as a peer agent. All output is prefixed with `[node-name]`.

## Modes

**Bridge mode** — remote agent uses proxied tools to access the local filesystem:
```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/agent.py" \
  --cwd <working directory> \
  "<message>"
```

**Peer mode** — remote agent clones the repo to its own machine and works autonomously:
```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/agent.py" \
  --node <hostname> \
  --repo <git-url> \
  "<message>"
```

Read the topology (load-topology-skill) to find the node hostname, confirm it is online, and verify its inference server is active before invoking.

Set `FOREIGN_AGENT_URL` and `FOREIGN_AGENT_MODEL` to target the correct node and model.

## Output format

- `[node-name] ...` — text response
- `[node-name:tool:tool_name] ...` — tool call
- `[node-name:result] ...` — tool result (truncated if long)

## Bridge mode toolset

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

In peer mode only `bash` is exposed — the remote agent has full shell access on its own machine.

## Triggers

Invoke when the user says "ask [node]", "what does [node] think", or "let [node] look at this".
