# ask-foreign-agent-skill

A bridge between an orchestrating/local agent and a remote LLM running on a node in your topology.

## Dependency on load-topology-skill

The topology file (managed by [load-topology-skill](https://github.com/nicholasf/load-topology-skill)) is the source of truth for which LLM nodes are available, what models they are running, and how to reach them. Before invoking a foreign agent, read the topology to confirm the target node is online and its inference server is active.

Set these environment variables to target a node:

```bash
export FOREIGN_AGENT_URL=http://<node-hostname>:9337/v1
export FOREIGN_AGENT_MODEL=<model-name>
```

## Modes

### Bridge mode

The remote agent has no copy of the codebase. The orchestrating agent proxies tool calls on its behalf — the remote agent requests `read_file`, `bash`, `grep`, etc., and the orchestrating agent executes them locally and returns results. Useful for focused inspection tasks where a full clone is unnecessary.

```bash
python3 agent.py --cwd /path/to/project "Summarise how authentication works"
```

### Peer mode

The remote agent clones the repository to its own machine and works against it directly. Tool calls execute on the remote node via SSH. The orchestrating agent's working copy is untouched. Results are returned via `git diff`, a pushed branch, or a pull request — the remote agent decides based on the task.

```bash
python3 agent.py \
  --node <hostname> \
  --repo https://github.com/user/repo \
  "Refactor the auth module and open a PR"
```

The node hostname comes from the topology. `--remote-path` overrides the default clone location (`/tmp/ask-foreign-agent/<repo-name>`).

In peer mode, only `bash` is exposed as a tool. The remote agent has full shell access on its own machine and uses bash for everything: reading files, running tests, committing, pushing, opening PRs.

## Security

**Peer mode grants the remote agent shell access to the target node.** Consider the following before use:

- The LLM is not sandboxed. A sufficiently adversarial prompt — including content read from source files — could cause the remote agent to request destructive bash commands that execute on the remote node.
- The SSH key used (`$SSH_USER`) has full shell access. Use a dedicated agent user with restricted permissions where possible, and prefer nodes that are not shared with other workloads.
- Treat the remote node as an execution environment for agent work, not a production machine.
- Review results (diff or PR) before merging. Never auto-merge output from a remote agent.

Bridge mode does not have this exposure — tool calls execute locally under the orchestrating agent's control.

## Toolset (bridge mode)

| Tool | What it does |
|---|---|
| `read_file` | Read a file by path |
| `write_file` | Write content to a file |
| `edit_file` | Replace an exact string in a file |
| `bash` | Run a bash command in the working directory |
| `find_files` | Find files by name pattern |
| `grep` | Search for a pattern across files |
| `list_directory` | List directory tree |
| `git_diff` | Show unstaged and staged changes |

## Setup

```bash
uv sync
# or: pip install langchain-core langchain-openai
```

## Usage

Bridge mode — ask a question about the local codebase:
```
ask the foreign agent what the tradeoffs are between X and Y
```

Peer mode — delegate a task to a remote node:
```
ask the foreign agent on gollum to clone the repo and refactor the auth module
```
