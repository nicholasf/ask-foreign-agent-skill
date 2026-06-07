#!/usr/bin/env python3
"""
ask-foreign-agent: run a remote LLM node as an interactive agent.

Bridge mode — local (default):
  Tool calls execute on the orchestrating machine (dtv-claude-agent's machine).

  python3 agent.py --cwd /path/to/project "Your message"

Bridge mode — SSH:
  Tool calls execute on a remote node via SSH. The remote node needs the repo
  and toolchain but does not need an agent runtime.

  python3 agent.py --cwd /path/to/project --ssh-node <hostname> --ssh-cwd <remote-path> "Your message"

Peer mode (agent-to-agent):
  The remote node runs Hermes as an agent runtime. The orchestrating agent
  sends a task to the Hermes gateway and receives an autonomous result.
  Requires Hermes configured with API_SERVER_ENABLED=true on the remote node.
  Gateway URL and key are read from topology.md and $SKILLS_HOME/.env.

  python3 agent.py --peer-node <hostname> "Your task"

Environment:
  FOREIGN_AGENT_URL    OpenAI-compatible base URL of the remote model
  FOREIGN_AGENT_MODEL  Model name to request
  AGENT_SSH_USER       Username for SSH connections in bridge (SSH) mode
"""

import argparse
import os
import re
import sys

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from tools import TOOL_MAP, TOOLS
from tools import _context
from tools.bash import bash

AGENT_URL = os.environ.get('FOREIGN_AGENT_URL', 'http://localhost:9337/v1')
AGENT_MODEL = os.environ.get('FOREIGN_AGENT_MODEL', 'qwen3-coder-30b.gguf')
MAX_ITERATIONS = 400


def _load_skills_env() -> dict[str, str]:
    skills_home = os.environ.get('SKILLS_HOME', os.path.expanduser('~/.agents/skills'))
    result: dict[str, str] = {}
    try:
        with open(os.path.join(skills_home, '.env')) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, _, v = line.partition('=')
                    result[k.strip()] = v.strip()
    except FileNotFoundError:
        pass
    return result


def _topology_node(hostname: str) -> dict[str, str]:
    skills_home = os.environ.get('SKILLS_HOME', os.path.expanduser('~/.agents/skills'))
    topology_path = os.environ.get('TOPOLOGY_PATH', os.path.join(skills_home, 'topology.md'))
    try:
        with open(topology_path) as f:
            rows = [l.strip() for l in f if l.strip().startswith('|')]
    except FileNotFoundError:
        return {}
    if len(rows) < 3:
        return {}
    headers = [h.strip() for h in rows[0].strip('|').split('|')]
    for row in rows[2:]:  # skip separator line
        values = [v.strip() for v in row.strip('|').split('|')]
        node = dict(zip(headers, values))
        if node.get('hostname') == hostname:
            return node
    return {}

_FUNC_RE = re.compile(r'(?:<tool_call>\s*)?<function=(\w+)>(.*?)</function>\s*(?:</tool_call>)?', re.DOTALL)
_PARAM_RE = re.compile(r'<parameter=(\w+)>\s*(.*?)\s*</parameter>', re.DOTALL)


def make_llm() -> ChatOpenAI:
    return ChatOpenAI(
        base_url=AGENT_URL,
        api_key='none',
        model=AGENT_MODEL,
        temperature=0,
    )


def parse_xml_tool_calls(content: str) -> tuple[list[dict], str]:
    """
    Fallback parser for qwen3's hermes-style XML tool calls.
    Returns (tool_calls, text_before_first_call).
    Used when the model emits XML instead of structured JSON tool_calls.
    """
    tool_calls = []
    first_match_start = len(content)
    for i, match in enumerate(_FUNC_RE.finditer(content)):
        if i == 0:
            first_match_start = match.start()
        name = match.group(1)
        args = {m.group(1): m.group(2).strip() for m in _PARAM_RE.finditer(match.group(2))}
        tool_calls.append({'name': name, 'args': args, 'id': f'xml_{name}_{i}'})
    preamble = content[:first_match_start].strip()
    return tool_calls, preamble


def print_prefixed(text: str, prefix: str, suffix: str = '') -> None:
    tag = f'[{prefix}{(":" + suffix) if suffix else ""}]'
    for line in str(text).splitlines():
        print(f'{tag} {line}')



def run(message: str, prefix: str, tools: list, tool_map: dict) -> None:
    llm = make_llm().bind_tools(tools)
    messages: list = [HumanMessage(content=message)]

    print(f'\n[{prefix}] thinking...\n', flush=True)

    for _ in range(MAX_ITERATIONS):
        response: AIMessage = llm.invoke(messages)
        messages.append(response)

        tool_calls = response.tool_calls
        preamble = ''
        if not tool_calls and '<function=' in str(response.content):
            tool_calls, preamble = parse_xml_tool_calls(str(response.content))

        if preamble:
            print_prefixed(preamble, prefix)

        if tool_calls:
            tool_messages = []
            for tc in tool_calls:
                args = ', '.join(f'{k}={v!r}' for k, v in tc['args'].items())
                print_prefixed(f'{tc["name"]}({args})', prefix, suffix='tool')
                result = tool_map[tc['name']].invoke(tc['args'])
                result_str = str(result)
                if len(result_str) > 6000:
                    result_str = result_str[:6000] + '\n...[truncated]'
                preview = result_str[:400] + '...' if len(result_str) > 400 else result_str
                print_prefixed(preview, prefix, suffix='result')
                tool_messages.append(ToolMessage(content=result_str, tool_call_id=tc['id'], name=tc['name']))
            messages.extend(tool_messages)
        else:
            if response.content:
                print_prefixed(str(response.content), prefix)
            break

    print(flush=True)


def run_peer(message: str, peer_node: str, prefix: str) -> str:
    node = _topology_node(peer_node)
    gateway = node.get('hermes_gateway', '').replace('—', '').strip()
    key_env = node.get('hermes_key_env', '').replace('—', '').strip()

    if not gateway:
        print(f'[{prefix}] error: no hermes_gateway entry for {peer_node!r} in topology.md', file=sys.stderr)
        sys.exit(1)

    api_key = _load_skills_env().get(key_env, '') if key_env else ''

    llm = ChatOpenAI(
        base_url=f'{gateway}/v1',
        api_key=api_key or 'none',
        model='hermes-agent',
        temperature=0,
    )

    print(f'\n[{prefix}] peer → {gateway}\n', flush=True)
    response = llm.invoke([HumanMessage(content=message)])
    output = str(response.content)

    for line in output.splitlines():
        print_prefixed(line, prefix)
    print(flush=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='ask-foreign-agent: remote LLM as agent')
    parser.add_argument('message', nargs='+', help='Message to send to the agent')
    parser.add_argument('--cwd', default='.', help='Local working directory for bridge mode tool execution')
    parser.add_argument('--thread', default='default', help='Thread ID for multi-turn conversation')
    parser.add_argument('--ssh-node', default='', help='Remote node hostname for bridge (SSH) mode')
    parser.add_argument('--ssh-cwd', default='', help='Working directory on the remote node for bridge (SSH) mode')
    parser.add_argument('--peer-node', default='', help='Remote node hostname for peer mode (Hermes gateway)')
    args = parser.parse_args()

    if args.peer_node:
        run_peer(' '.join(args.message), args.peer_node, args.peer_node)
        return
    elif args.ssh_node:
        _context.ssh_node = args.ssh_node
        _context.working_directory = args.ssh_cwd or '.'
        prefix = args.ssh_node
        active_tools = [bash]
        active_tool_map = {'bash': bash}
    else:
        _context.working_directory = os.path.abspath(args.cwd)
        prefix = 'remote-agent'
        active_tools = TOOLS
        active_tool_map = TOOL_MAP

    run(' '.join(args.message), prefix, active_tools, active_tool_map)


if __name__ == '__main__':
    main()
