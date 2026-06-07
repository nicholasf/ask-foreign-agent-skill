# Hermes Agent Setup

[Hermes](https://github.com/NousResearch/hermes-agent) is an optional agent runtime
for peer mode. When installed on a remote node, it receives tasks from the
orchestrating machine via HTTP, executes them autonomously using its own local tools,
and returns results. No SSH proxying required.

## Prerequisites

- Hermes installed at `~/.hermes/` on the remote node
- llama-server (llama.cpp) running with the target model
- Always invoke Hermes via the venv binary:
  `~/.hermes/hermes-agent/venv/bin/hermes`
  (the bare `~/.hermes/hermes-agent/hermes` binary is missing dependencies)

---

## Step 1 — Verify llama-server context size

Hermes requires at least 64K active context. Check what the running server reports:

```bash
curl -s http://localhost:9337/props | python3 -m json.tool | grep n_ctx
```

If `n_ctx` is below 65536, restart with a larger value:

```bash
ps aux | grep llama-server | grep -v grep   # find the PID

kill <PID>
nohup /path/to/llama-server \
  --model /path/to/model.gguf \
  -np 1 --ctx-size 65536 --port 9337 --host 0.0.0.0 \
  > ~/.hermes/logs/llama-server.log 2>&1 &

curl -s http://localhost:9337/health          # wait until {"status":"ok"}
curl -s http://localhost:9337/props | grep n_ctx
```

Note: `n_ctx_train` in `/v1/models` shows the model's training max, not the
running context window. Always check `/props` for the real value.

---

## Step 2 — Configure Hermes to use the local llama-server

Edit `~/.hermes/config.yaml`, model section:

```yaml
model:
  default: "qwen3-coder-30b.gguf"   # replace with your model name
  provider: "llamacpp"
  base_url: "http://localhost:9337/v1"
```

Verify:

```bash
~/.hermes/hermes-agent/venv/bin/hermes config
```

Smoke test:

```bash
~/.hermes/hermes-agent/venv/bin/hermes -z 'say hello in one word' --yolo
# Expected: Hello!
```

Note: `cli-config.yaml` is not auto-loaded despite what the comment in
`config.yaml` suggests. Edit `config.yaml` directly.

---

## Step 3 — Generate an API key

On the orchestrating machine:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

---

## Step 4 — Enable the API server

Append to `~/.hermes/.env` on the remote node:

```bash
# Peer mode — agent-to-agent HTTP
API_SERVER_ENABLED=true
API_SERVER_KEY=<generated-key>
API_SERVER_HOST=0.0.0.0
API_SERVER_PORT=8642
```

`API_SERVER_HOST=0.0.0.0` is required — without it the gateway only listens
on localhost and remote requests are refused.

---

## Step 5 — Start the gateway

```bash
nohup ~/.hermes/hermes-agent/venv/bin/hermes gateway run --accept-hooks \
  > ~/.hermes/logs/gateway.log 2>&1 &

tail -20 ~/.hermes/logs/gateway.log
# Expected: API server listening on http://0.0.0.0:8642 (model: hermes-agent)
#           ✓ api_server connected
```

To auto-start on reboot: `hermes gateway install` (creates a systemd unit).

---

## Step 6 — Register in topology and env

On the orchestrating machine, add the node to `$SKILLS_HOME/topology.md`:

| column | value |
|---|---|
| `hermes_gateway` | `http://<hostname>:8642` |
| `hermes_key_env` | `<NODE>_HERMES_KEY` |

Add the key to `$SKILLS_HOME/.env`:

```bash
<NODE>_HERMES_KEY=<generated-key>
```

---

## Step 7 — Verify end-to-end

From the orchestrating machine:

```bash
# Health check
curl -s -H "Authorization: Bearer <key>" http://<hostname>:8642/v1/models

# Full agent invocation
python3 agent.py --peer-node <hostname> "say hello in one word"
```
