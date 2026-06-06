Run the ask-foreign-agent (remote LLM node) with the following message and display its output in this session.

Message: $ARGUMENTS

Steps:
1. Check the topology (load-topology-skill) to confirm the target node is online and its inference server is active.
2. Run the agent via Bash using the command below. Use the current project working directory as `--cwd`.
3. All output is prefixed with `[node-name]` — display it verbatim.
4. After the agent finishes, briefly relay its final answer in plain text.

```bash
"${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/.venv/bin/python3" \
  "${SKILLS_HOME:-$HOME/.agents/skills}/ask-foreign-agent-skill/agent.py" \
  --cwd <current working directory> \
  "<message>"
```

Do not summarise or paraphrase the agent's tool calls — show them as-is. If the agent errors, show the error and stop.
