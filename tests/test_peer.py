import json
import subprocess

import pytest
from unittest.mock import MagicMock, patch

import peer

TOPOLOGY = """\
# Topology

| name | hostname | hermes_gateway | hermes_key_env | goose_acp_url |
|---|---|---|---|---|
| — | hermes-node | http://hermes-node:8642 | HERMES_NODE_KEY | — |
| — | goose-node | — | — | ws://goose-node:3284 |
| — | both-node | http://both-node:8642 | BOTH_NODE_KEY | ws://both-node:3284 |
| — | bare-node | — | — | — |
"""


@pytest.fixture
def tmp_skills(tmp_path, monkeypatch):
    monkeypatch.setenv('SKILLS_HOME', str(tmp_path))
    monkeypatch.setenv('TOPOLOGY_PATH', str(tmp_path / 'topology.md'))
    (tmp_path / 'topology.md').write_text(TOPOLOGY)
    return tmp_path


# --- _parse_node_spec ---

HOSTS = {'pond', 'gollum', 'hut', 'dawntreader-v'}


def test_parse_hostname_only():
    assert peer._parse_node_spec('pond', HOSTS) == ('pond', None, None)


def test_parse_hostname_and_runtime():
    assert peer._parse_node_spec('pond-hermes', HOSTS) == ('pond', None, 'hermes')
    assert peer._parse_node_spec('pond-goose', HOSTS) == ('pond', None, 'goose')


def test_parse_hostname_llm_runtime():
    assert peer._parse_node_spec('pond-qwen-hermes', HOSTS) == ('pond', 'qwen', 'hermes')
    assert peer._parse_node_spec('gollum-mistral-goose', HOSTS) == ('gollum', 'mistral', 'goose')


def test_parse_compound_hostname():
    assert peer._parse_node_spec('dawntreader-v', HOSTS) == ('dawntreader-v', None, None)
    assert peer._parse_node_spec('dawntreader-v-qwen-hermes', HOSTS) == ('dawntreader-v', 'qwen', 'hermes')


def test_parse_unknown_host_falls_back():
    hostname, llm, runtime = peer._parse_node_spec('unknown-node', set())
    assert hostname == 'unknown-node'
    assert runtime is None


# --- _all_topology_hostnames ---

def test_all_topology_hostnames(tmp_skills):
    hosts = peer._all_topology_hostnames()
    assert 'hermes-node' in hosts
    assert 'goose-node' in hosts
    assert 'both-node' in hosts


# --- _load_skills_env ---

def test_load_skills_env_reads_key_value_pairs(tmp_skills):
    (tmp_skills / '.env').write_text('FOO=bar\nBAZ=qux\n')
    env = peer._load_skills_env()
    assert env['FOO'] == 'bar'
    assert env['BAZ'] == 'qux'


def test_load_skills_env_ignores_comments(tmp_skills):
    (tmp_skills / '.env').write_text('# this is a comment\nKEY=val\n')
    env = peer._load_skills_env()
    assert list(env.keys()) == ['KEY']


def test_load_skills_env_missing_file_returns_empty(tmp_skills):
    assert peer._load_skills_env() == {}


# --- _topology_node ---

def test_topology_node_found(tmp_skills):
    node = peer._topology_node('hermes-node')
    assert node['hermes_gateway'] == 'http://hermes-node:8642'
    assert node['hermes_key_env'] == 'HERMES_NODE_KEY'


def test_topology_node_not_found_returns_empty(tmp_skills):
    assert peer._topology_node('unknown') == {}


def test_topology_node_missing_file_returns_empty(tmp_skills):
    (tmp_skills / 'topology.md').unlink()
    assert peer._topology_node('hermes-node') == {}


# --- run_peer routing ---

def test_run_peer_routes_to_hermes(tmp_skills):
    (tmp_skills / '.env').write_text('HERMES_NODE_KEY=testkey\n')
    mock_response = MagicMock()
    mock_response.content = 'hello from hermes'

    with patch('peer.ChatOpenAI') as mock_cls:
        mock_cls.return_value.invoke.return_value = mock_response
        result = peer.run_peer('test task', 'hermes-node', 'hermes-node')

    assert result == 'hello from hermes'
    kwargs = mock_cls.call_args.kwargs
    assert 'hermes-node:8642' in kwargs['base_url']
    assert kwargs['api_key'] == 'testkey'


def test_run_peer_routes_to_goose(tmp_skills):
    with patch('goose.acp.prompt', return_value='hello from goose') as mock_prompt:
        result = peer.run_peer('test task', 'goose-node', 'goose-node')

    assert result == 'hello from goose'
    mock_prompt.assert_called_once_with('ws://goose-node:3284', 'test task')


def test_run_peer_prefers_goose_when_both_configured(tmp_skills):
    with patch('goose.acp.prompt', return_value='goose wins') as mock_prompt:
        result = peer.run_peer('test task', 'both-node', 'both-node')

    assert result == 'goose wins'
    mock_prompt.assert_called_once()


def test_run_peer_exits_when_no_gateway(tmp_skills):
    with pytest.raises(SystemExit):
        peer.run_peer('test task', 'bare-node', 'bare-node')


def test_run_peer_exits_when_node_not_in_topology(tmp_skills):
    with pytest.raises(SystemExit):
        peer.run_peer('test task', 'nonexistent', 'nonexistent')


# --- --runtime flag ---

def test_runtime_hermes_explicit(tmp_skills):
    (tmp_skills / '.env').write_text('BOTH_NODE_KEY=k\n')
    mock_response = MagicMock()
    mock_response.content = 'hermes forced'

    with patch('peer.ChatOpenAI') as mock_cls:
        mock_cls.return_value.invoke.return_value = mock_response
        result = peer.run_peer('task', 'both-node', 'both-node', runtime='hermes')

    assert result == 'hermes forced'
    mock_cls.assert_called_once()


def test_runtime_goose_explicit(tmp_skills):
    with patch('goose.acp.prompt', return_value='goose forced') as mock_prompt:
        result = peer.run_peer('task', 'both-node', 'both-node', runtime='goose')

    assert result == 'goose forced'
    mock_prompt.assert_called_once()


def test_runtime_hermes_explicit_exits_when_not_configured(tmp_skills):
    with pytest.raises(SystemExit):
        peer.run_peer('task', 'goose-node', 'goose-node', runtime='hermes')


def test_runtime_goose_explicit_exits_when_not_configured(tmp_skills):
    with pytest.raises(SystemExit):
        peer.run_peer('task', 'hermes-node', 'hermes-node', runtime='goose')


# --- fallback ---

def test_auto_falls_back_to_hermes_when_goose_unreachable(tmp_skills):
    (tmp_skills / '.env').write_text('BOTH_NODE_KEY=k\n')
    mock_response = MagicMock()
    mock_response.content = 'hermes fallback'

    with patch('goose.acp.prompt', side_effect=OSError('Connection refused')):
        with patch('peer.ChatOpenAI') as mock_cls:
            mock_cls.return_value.invoke.return_value = mock_response
            result = peer.run_peer('task', 'both-node', 'both-node', runtime='auto')

    assert result == 'hermes fallback'
    mock_cls.assert_called_once()


def test_auto_exits_when_goose_unreachable_and_no_hermes(tmp_skills):
    with patch('goose.acp.prompt', side_effect=OSError('Connection refused')):
        with pytest.raises(SystemExit):
            peer.run_peer('task', 'goose-node', 'goose-node', runtime='auto')


# --- sync: _git_info ---

@pytest.fixture
def git_repo(tmp_path):
    subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', 'remote', 'add', 'origin', 'https://github.com/test/repo.git'], cwd=tmp_path, capture_output=True)
    (tmp_path / 'README.md').write_text('hello')
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', '-c', 'commit.gpgsign=false', 'commit', '-m', 'init'], cwd=tmp_path, capture_output=True)
    return tmp_path


def test_git_info_returns_sha1_branch_remote(git_repo):
    info = peer._git_info(str(git_repo))
    assert len(info['sha1']) == 40
    assert info['branch'] in ('main', 'master')
    assert info['remote_url'] == 'https://github.com/test/repo.git'


def test_git_info_empty_on_bad_path():
    info = peer._git_info('/nonexistent/path')
    assert info['sha1'] == ''
    assert info['branch'] == ''


# --- sync: _sync_prompt ---

def test_sync_prompt_contains_key_fields():
    prompt = peer._sync_prompt('my-repo', 'https://github.com/x/my-repo', 'main', 'abc123def', {'python': '3.11'})
    assert 'abc123def' in prompt
    assert 'main' in prompt
    assert '"python": "3.11"' in prompt
    assert 'repo_path' in prompt
    assert 'sha1_present' in prompt
    assert 'git_commands' in prompt
    assert 'languages' in prompt


# --- sync: run_sync ---

SYNC_RESPONSE = json.dumps({
    'repo_path': '/home/x/repo',
    'sha1_present': True,
    'remote_sha1': 'abc123def',
    'git_commands': [],
    'languages': {
        'python': {'requested': '3.11', 'found': '3.12.0', 'match': False}
    },
})


def test_run_sync_returns_parsed_json(tmp_skills, git_repo):
    with patch('goose.acp.prompt', return_value=SYNC_RESPONSE):
        result = peer.run_sync('goose-node', str(git_repo), {'python': '3.11'})

    assert result['sha1_present'] is True
    assert result['languages']['python']['match'] is False
    assert result['repo_path'] == '/home/x/repo'


def test_run_sync_strips_think_blocks(tmp_skills, git_repo):
    wrapped = f'<think>internal reasoning</think>{SYNC_RESPONSE}'
    with patch('goose.acp.prompt', return_value=wrapped):
        result = peer.run_sync('goose-node', str(git_repo), {})

    assert 'error' not in result
    assert 'sha1_present' in result


def test_run_sync_strips_markdown_fences(tmp_skills, git_repo):
    wrapped = f'```json\n{SYNC_RESPONSE}\n```'
    with patch('goose.acp.prompt', return_value=wrapped):
        result = peer.run_sync('goose-node', str(git_repo), {})

    assert 'error' not in result
    assert 'sha1_present' in result


def test_run_sync_returns_error_on_invalid_json(tmp_skills, git_repo):
    with patch('goose.acp.prompt', return_value='not valid json at all'):
        result = peer.run_sync('goose-node', str(git_repo), {})

    assert 'error' in result
    assert 'raw' in result
