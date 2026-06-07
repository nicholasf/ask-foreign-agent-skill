---
name: ask-foreign-agent
description: Run a remote LLM node as an interactive agent. Bridge mode (local) proxies tool calls on the orchestrating machine. Bridge mode (SSH) executes tool calls on a remote node via SSH. Peer mode (agent-to-agent) requires Hermes on the remote node — pending setup. Depends on load-topology-skill to identify available nodes.
depends_on:
  - load-topology-skill
---

Read the topology (load-topology-skill) to find the node hostname and verify it is online before invoking. Invoke `/ask-foreign-agent` for the full workflow.
