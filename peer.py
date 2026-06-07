#!/usr/bin/env python3
"""
ask-foreign-agent: delegate tasks to a remote autonomous agent runtime.

Subcommands:
  run   Delegate a task to the remote agent.
  sync  Negotiate repo state and language versions with the remote agent.

Environment:
  SKILLS_HOME    Root directory for skills and topology (default: ~/.agents/skills)
  TOPOLOGY_PATH  Override path to topology.md
"""

import argparse
import json
import os
import re
import subprocess
import sys

import goose.acp
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)
_FENCE_RE = re.compile(r'^```(?:json)?\s*|\s*```$', re.MULTILINE)
_RUNTIMES = frozenset({'goose', 'hermes'})


def _all_topology_hostnames() -> set[str]:
    skills_home = os.environ.get('SKILLS_HOME', os.path.expanduser('~/.agents/skills'))
    topology_path = os.environ.get('TOPOLOGY_PATH', os.path.join(skills_home, 'topology.md'))
    try:
        with open(topology_path) as f:
            rows = [l.strip() for l in f if l.strip().startswith('|')]
    except FileNotFoundError:
        return set()
    if len(rows) < 3:
        return set()
    headers = [h.strip() for h in rows[0].strip('|').split('|')]
    hosts: set[str] = set()
    for row in rows[2:]:
        values = [v.strip() for v in row.strip('|').split('|')]
        node = dict(zip(headers, values))
        h = _clean(node.get('hostname', ''))
        if h and h != '—':
            hosts.add(h)
    return hosts


def _parse_node_spec(spec: str, known_hosts: set[str]) -> tuple[str, str | None, str | None]:
    """Parse '<hostname>[-<llm>[-<runtime>]]' into (hostname, llm, runtime).

    Handles compound hostnames (e.g. 'dawntreader-v') by matching against known_hosts.
    Runtime must be 'goose' or 'hermes' when present.
    """
    parts = spec.split('-')
    runtime: str | None = None
    if parts[-1] in _RUNTIMES:
        runtime = parts.pop()
    for i in range(len(parts), 0, -1):
        candidate = '-'.join(parts[:i])
        if candidate in known_hosts:
            llm = '-'.join(parts[i:]) or None
            return candidate, llm, runtime
    return '-'.join(parts), None, runtime


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


def _call_agent(message: str, node: dict, peer_node: str, runtime: str) -> str:
    """Route to the configured agent runtime and return the raw response."""
    goose_url = _clean(node.get('goose_acp_url', ''))
    hermes_gateway = _clean(node.get('hermes_gateway', ''))

    if runtime == 'goose':
        if not goose_url:
            print(f'[{peer_node}] error: no goose_acp_url for {peer_node!r} in topology.md', file=sys.stderr)
            sys.exit(1)
        return _run_goose(message, node, peer_node)
    elif runtime == 'hermes':
        if not hermes_gateway:
            print(f'[{peer_node}] error: no hermes_gateway for {peer_node!r} in topology.md', file=sys.stderr)
            sys.exit(1)
        return _run_hermes(message, node, peer_node)
    elif goose_url:
        try:
            return _run_goose(message, node, peer_node)
        except OSError as e:
            if hermes_gateway:
                print(f'[{peer_node}] goose unreachable ({e}), falling back to hermes\n', flush=True)
                return _run_hermes(message, node, peer_node)
            else:
                print(f'[{peer_node}] error: goose unreachable and no hermes fallback: {e}', file=sys.stderr)
                sys.exit(1)
    elif hermes_gateway:
        return _run_hermes(message, node, peer_node)
    else:
        print(f'[{peer_node}] error: no agent gateway configured for {peer_node!r} in topology.md', file=sys.stderr)
        sys.exit(1)


def run_peer(message: str, peer_node: str, prefix: str, runtime: str = 'auto') -> str:
    node = _topology_node(peer_node)
    output = _call_agent(message, node, peer_node, runtime)
    print_prefixed(output, prefix)
    print(flush=True)
    return output


# --- sync ---

def _git_info(repo_path: str) -> dict[str, str]:
    def git(*args) -> str:
        try:
            r = subprocess.run(['git', *args], cwd=repo_path, capture_output=True, text=True)
            return r.stdout.strip() if r.returncode == 0 else ''
        except OSError:
            return ''

    return {
        'sha1': git('rev-parse', 'HEAD'),
        'branch': git('branch', '--show-current'),
        'remote_url': git('remote', 'get-url', 'origin'),
    }


def _sync_prompt(repo_name: str, remote_url: str, branch: str, sha1: str, langs: dict[str, str]) -> str:
    header = (
        f'Sync check. Respond with a JSON object only — no explanation, no markdown fences.\n\n'
        f'Local agent state:\n'
        f'  repo: {repo_name}\n'
        f'  remote_url: {remote_url}\n'
        f'  branch: {branch}\n'
        f'  sha1: {sha1}\n'
        f'  languages: {json.dumps(langs)}\n\n'
        f'Tasks:\n'
        f'1. Locate the repository on this machine (search ~/, ~/code/, /home/*/code/, /tmp/).\n'
        f'2. Check if commit {sha1} is present: git cat-file -e {sha1}^{{commit}}\n'
        f'3. If the commit is not present, provide the git commands needed to fetch and check out branch {branch!r}.\n'
        f'4. For each language in the languages list, check the installed version.\n\n'
        f'Respond with exactly this JSON structure:\n'
    )
    template = (
        '{\n'
        '  "repo_path": "<absolute path or null>",\n'
        '  "sha1_present": true or false,\n'
        '  "remote_sha1": "<current HEAD sha1 at repo_path, or null>",\n'
        '  "git_commands": ["<cmd>", ...],\n'
        '  "languages": {\n'
        '    "<name>": {"requested": "<version>", "found": "<version or null>", "match": true or false}\n'
        '  }\n'
        '}'
    )
    return header + template


def run_sync(peer_node: str, repo_path: str, langs: dict[str, str], runtime: str = 'auto') -> dict:
    node = _topology_node(peer_node)
    git = _git_info(repo_path)
    repo_name = os.path.basename(repo_path.rstrip('/'))

    prompt = _sync_prompt(
        repo_name=repo_name,
        remote_url=git.get('remote_url', ''),
        branch=git.get('branch', ''),
        sha1=git.get('sha1', ''),
        langs=langs,
    )

    raw = _call_agent(prompt, node, peer_node, runtime)
    raw = _THINK_RE.sub('', raw).strip()
    raw = _FENCE_RE.sub('', raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {'error': 'could not parse agent response as JSON', 'raw': raw}


# --- CLI ---

def main() -> None:
    parser = argparse.ArgumentParser(description='ask-foreign-agent: delegate to a remote agent runtime')
    subparsers = parser.add_subparsers(dest='command', required=True)

    run_p = subparsers.add_parser('run', help='Delegate a task to the remote agent')
    run_p.add_argument('node', help='Remote node hostname (from topology)')
    run_p.add_argument('message', nargs='+', help='Task to send to the remote agent')
    run_p.add_argument('--runtime', default='auto', choices=['auto', 'goose', 'hermes'],
                       help='Force a specific runtime (default: auto)')

    sync_p = subparsers.add_parser('sync', help='Negotiate repo state and language versions with remote agent')
    sync_p.add_argument('node', help='Remote node hostname (from topology)')
    sync_p.add_argument('--repo', required=True, help='Local path to the git repository')
    sync_p.add_argument('--lang', action='append', dest='langs', metavar='NAME=VERSION',
                        help='Language version to check, e.g. python=3.11 (repeatable)')
    sync_p.add_argument('--runtime', default='auto', choices=['auto', 'goose', 'hermes'],
                        help='Force a specific runtime (default: auto)')

    args = parser.parse_args()

    known_hosts = _all_topology_hostnames()
    hostname, _llm, runtime_from_name = _parse_node_spec(args.node, known_hosts)
    runtime = args.runtime if args.runtime != 'auto' else (runtime_from_name or 'auto')

    if args.command == 'run':
        run_peer(' '.join(args.message), hostname, args.node, runtime=runtime)
    elif args.command == 'sync':
        langs = {}
        for item in (args.langs or []):
            k, _, v = item.partition('=')
            langs[k.strip()] = v.strip()
        result = run_sync(hostname, args.repo, langs, runtime=runtime)
        print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
