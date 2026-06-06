"""Shared mutable state and subprocess runner for all tools."""

import os
import subprocess

working_directory: str = "."
ssh_node: str = ""


def run_command(command: str, timeout: int = 30) -> str:
    if ssh_node:
        ssh_user = os.environ.get('SSH_USER', '')
        target = f'{ssh_user}@{ssh_node}' if ssh_user else ssh_node
        # Command runs on the remote node via SSH. The remote shell interprets the command.
        cmd = ['ssh', target, f'cd {working_directory} && {command}']
        cwd = None
    else:
        cmd = command
        cwd = working_directory

    try:
        result = subprocess.run(
            cmd,
            shell=isinstance(cmd, str),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        output = result.stdout
        if result.returncode != 0 and result.stderr:
            output += f"\nSTDERR: {result.stderr.strip()}"
        return output.strip() or "(no output)"
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout}s"
    except Exception as e:
        return f"Error: {e}"
