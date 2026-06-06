# ask-foreign-agent-skill

A bridge between an orchestrating/local agent and a remote LLM running on a node in your topology.

The foreign agent — qwen3-coder on pond, or any LLM node you point it at — has no direct access to your filesystem or shell. This skill defines the toolset it *can* request (read files, run bash commands, grep, write files, etc.) and executes those tool calls locally on its behalf. Claude acts as the intermediary: it sends your message to the remote model, receives tool call requests back, runs them against the local working directory, and returns the results — repeating until the foreign agent produces a final answer.

The result is a peer agent visible inside your Claude Code session, with all its reasoning and tool use shown inline.

## Dependency on load-topology-skill

The topology file (managed by [load-topology-skill](https://github.com/nicholasf/load-topology-skill)) is how you know which nodes are available and what models they are running. Before invoking a foreign agent, check the topology to confirm the target node is online and its inference server is active.

The agent connects to an OpenAI-compatible endpoint. Set these environment variables to target a specific node:

```bash
export FOREIGN_AGENT_URL=http://pond:9337/v1     # default
export FOREIGN_AGENT_MODEL=qwen3-coder-30b.gguf  # default
```

If your topology has a different LLM node — say `gollum` running Ollama on port 11434 — just point `FOREIGN_AGENT_URL` there.

## Toolset

The foreign agent can request any of these tools during its reasoning loop. Claude executes each one locally:

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
# Install dependencies into the local venv
uv sync

# Or with pip
pip install langchain-core langchain-openai
```

The skill is registered via [manage-skills-skill](https://github.com/nicholasf/manage-skills-skill).

## Usage

Ask pond a question directly:
```
ask qwen what the tradeoffs are between X and Y
```

Delegate a research task:
```
let qwen look at the auth module and summarise how sessions are managed
```

The foreign agent's output appears inline prefixed with `[pond-qwen]`.
