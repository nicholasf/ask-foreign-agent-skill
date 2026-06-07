#!/usr/bin/env python3
"""
ask-foreign-agent: delegate tasks to a remote autonomous agent runtime.

Peer mode:
  The remote node runs an agent runtime (Hermes or Goose). The orchestrating
  agent sends a task and receives an autonomous result. The runtime is selected
  automatically based on which gateway is configured in topology.md.

  python3 peer.py --peer-node <hostname> "Your task"

Environment:
  SKILLS_HOME    Root directory for skills and topology (default: ~/.agents/skills)
  TOPOLOGY_PATH  Override path to topology.md
"""

import argparse
import os
import sys

import goose.acp
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI


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
    for row in rows[2:]:
        values = [v.strip() for v in row.strip('|').split('|')]
        node = dict(zip(headers, values))
        if node.get('hostname') == hostname:
            return node
    return {}


def _clean(val: str) -> str:
    return val.replace('—', '').strip()


def print_prefixed(text: str, prefix: str) -> None:
    for line in str(text).splitlines():
        print(f'[{prefix}] {line}')


def _run_hermes(message: str, node: dict, prefix: str) -> str:
    gateway = _clean(node.get('hermes_gateway', ''))
    key_env = _clean(node.get('hermes_key_env', ''))
    api_key = _load_skills_env().get(key_env, '') if key_env else ''

    llm = ChatOpenAI(
        base_url=f'{gateway}/v1',
        api_key=api_key or 'none',
        model='hermes-agent',
        temperature=0,
    )
    print(f'\n[{prefix}] peer → {gateway}\n', flush=True)
    return str(llm.invoke([HumanMessage(content=message)]).content)


def _run_goose(message: str, node: dict, prefix: str) -> str:
    acp_url = _clean(node.get('goose_acp_url', ''))
    print(f'\n[{prefix}] peer → {acp_url}\n', flush=True)
    return goose.acp.prompt(acp_url, message)


def run_peer(message: str, peer_node: str, prefix: str, runtime: str = 'auto') -> str:
    node = _topology_node(peer_node)

    goose_url = _clean(node.get('goose_acp_url', ''))
    hermes_gateway = _clean(node.get('hermes_gateway', ''))

    if runtime == 'goose':
        if not goose_url:
            print(f'[{prefix}] error: no goose_acp_url for {peer_node!r} in topology.md', file=sys.stderr)
            sys.exit(1)
        output = _run_goose(message, node, prefix)
    elif runtime == 'hermes':
        if not hermes_gateway:
            print(f'[{prefix}] error: no hermes_gateway for {peer_node!r} in topology.md', file=sys.stderr)
            sys.exit(1)
        output = _run_hermes(message, node, prefix)
    elif goose_url:
        try:
            output = _run_goose(message, node, prefix)
        except OSError as e:
            if hermes_gateway:
                print(f'[{prefix}] goose unreachable ({e}), falling back to hermes\n', flush=True)
                output = _run_hermes(message, node, prefix)
            else:
                print(f'[{prefix}] error: goose unreachable and no hermes fallback: {e}', file=sys.stderr)
                sys.exit(1)
    elif hermes_gateway:
        output = _run_hermes(message, node, prefix)
    else:
        print(f'[{prefix}] error: no agent gateway configured for {peer_node!r} in topology.md', file=sys.stderr)
        sys.exit(1)

    print_prefixed(output, prefix)
    print(flush=True)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description='ask-foreign-agent: delegate to a remote agent runtime')
    parser.add_argument('message', nargs='+', help='Task to send to the remote agent')
    parser.add_argument('--peer-node', required=True, help='Remote node hostname (must have Hermes or Goose running)')
    parser.add_argument('--runtime', default='auto', choices=['auto', 'goose', 'hermes'],
                        help='Force a specific runtime (default: auto, prefers goose with hermes fallback)')
    args = parser.parse_args()

    run_peer(' '.join(args.message), args.peer_node, args.peer_node, runtime=args.runtime)


if __name__ == '__main__':
    main()
