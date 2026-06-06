#!/usr/bin/env python3
"""
ask-foreign-agent: run a remote LLM node as an interactive agent.

Bridge mode (default):
  The remote agent uses proxied tools to access the local filesystem.
  Tool calls execute on the orchestrating agent's machine.

  python3 agent.py --cwd /path/to/project "Your message"

Peer mode (--node):
  The remote agent clones the repo to its own machine and works against it directly.
  Tool calls execute on the remote node via SSH. The local working copy is untouched.

  python3 agent.py --node <hostname> --repo <url> "Your message"

Environment:
  FOREIGN_AGENT_URL    OpenAI-compatible base URL of the remote model
  FOREIGN_AGENT_MODEL  Model name to request
  SSH_USER             Username for SSH connections in peer mode (see load-topology-skill)
"""

import argparse
import os
import re
import subprocess
import sys

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI

from tools import TOOL_MAP, TOOLS
from tools import _context
from tools.bash import bash

AGENT_URL = os.environ.get('FOREIGN_AGENT_URL', 'http://localhost:9337/v1')
AGENT_MODEL = os.environ.get('FOREIGN_AGENT_MODEL', 'qwen3-coder-30b.gguf')
MAX_ITERATIONS = 400

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


def clone_or_update(node: str, repo: str, remote_path: str) -> None:
    ssh_user = os.environ.get('SSH_USER', '')
    target = f'{ssh_user}@{node}' if ssh_user else node
    command = (
        f'[ -d {remote_path}/.git ] '
        f'&& (cd {remote_path} && git pull) '
        f'|| git clone {repo} {remote_path}'
    )
    print(f'[peer] preparing {node}:{remote_path}')
    result = subprocess.run(['ssh', target, command], capture_output=True, text=True)
    if result.returncode != 0:
        print(f'[peer] failed: {result.stderr.strip()}', file=sys.stderr)
        sys.exit(1)
    print(f'[peer] ready')


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


def main() -> None:
    parser = argparse.ArgumentParser(description='ask-foreign-agent: remote LLM as agent')
    parser.add_argument('message', nargs='+', help='Message to send to the agent')
    parser.add_argument('--cwd', default='.', help='Working directory for bridge mode tool execution')
    parser.add_argument('--thread', default='default', help='Thread ID for multi-turn conversation')
    parser.add_argument('--node', default='', help='Topology node hostname for peer mode')
    parser.add_argument('--repo', default='', help='Git repo URL to clone on the remote node (peer mode)')
    parser.add_argument('--remote-path', default='', help='Path on remote node for the repo clone (peer mode)')
    args = parser.parse_args()

    if args.node:
        if not args.repo:
            print('Error: --repo is required in peer mode (--node)', file=sys.stderr)
            sys.exit(1)
        repo_name = args.repo.rstrip('/').split('/')[-1].replace('.git', '')
        remote_path = args.remote_path or f'/tmp/ask-foreign-agent/{repo_name}'
        clone_or_update(args.node, args.repo, remote_path)
        _context.ssh_node = args.node
        _context.working_directory = remote_path
        prefix = args.node
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
