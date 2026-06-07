from unittest.mock import patch, MagicMock

import pytest

from tools import _context


@pytest.fixture(autouse=True)
def reset_context():
    original_node = _context.ssh_node
    original_cwd = _context.working_directory
    yield
    _context.ssh_node = original_node
    _context.working_directory = original_cwd


def test_run_command_ssh_mode_constructs_ssh_call(monkeypatch):
    monkeypatch.setenv('AGENT_SSH_USER', 'agent')
    _context.ssh_node = 'gollum'
    _context.working_directory = '/tmp/myrepo'

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='ok', stderr='')
        result = _context.run_command('pytest')

    mock_run.assert_called_once()
    call_args = mock_run.call_args[0][0]
    assert call_args == ['ssh', 'agent@gollum', 'cd /tmp/myrepo && pytest']
    assert result == 'ok'


def test_run_command_ssh_mode_no_ssh_user(monkeypatch):
    monkeypatch.delenv('AGENT_SSH_USER', raising=False)
    _context.ssh_node = 'gollum'
    _context.working_directory = '/tmp/myrepo'

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='done', stderr='')
        _context.run_command('ls')

    call_args = mock_run.call_args[0][0]
    assert call_args == ['ssh', 'gollum', 'cd /tmp/myrepo && ls']


def test_run_command_local_mode_unchanged(monkeypatch):
    _context.ssh_node = ''
    _context.working_directory = '/tmp/local'

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout='local', stderr='')
        result = _context.run_command('echo hello')

    call_args = mock_run.call_args
    assert call_args[0][0] == 'echo hello'
    assert call_args[1]['cwd'] == '/tmp/local'
    assert result == 'local'


def test_run_command_ssh_mode_includes_stderr_on_failure(monkeypatch):
    monkeypatch.setenv('AGENT_SSH_USER', 'agent')
    _context.ssh_node = 'gollum'
    _context.working_directory = '/tmp/myrepo'

    with patch('subprocess.run') as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stdout='', stderr='command not found')
        result = _context.run_command('badcmd')

    assert 'STDERR' in result
    assert 'command not found' in result

