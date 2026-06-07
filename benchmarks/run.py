#!/usr/bin/env python3
"""
Peer mode benchmarks — send coding tasks to pond-qwen-agent via Hermes gateway
and evaluate the responses.

Usage:
    python3 benchmarks/run.py [--peer-node <hostname>] [--verbose]

Defaults to pond. Each task is sent via run_peer(), the response is stripped
of <think> blocks, then checked against a simple pass criterion.
"""

import argparse
import re
import sys
import time
from dataclasses import dataclass
from io import StringIO
from typing import Callable

sys.path.insert(0, '.')
from agent import run_peer

_THINK_RE = re.compile(r'<think>.*?</think>', re.DOTALL)


def _clean(text: str) -> str:
    return _THINK_RE.sub('', text).strip()


@dataclass
class Task:
    name: str
    message: str
    check: Callable[[str], tuple[bool, str]]


TASKS = [
    Task(
        name='reverse_string',
        message=(
            'Write a Python function called reverse_string that reverses a string. '
            'Return only the code, no explanation.'
        ),
        check=lambda r: (
            'def reverse_string' in r and ('[::-1]' in r or 'reversed' in r),
            'expected def reverse_string with [::-1] or reversed()'
        ),
    ),
    Task(
        name='fizzbuzz',
        message=(
            'Write a Python function called fizzbuzz(n) that returns "Fizz" if n is '
            'divisible by 3, "Buzz" if divisible by 5, "FizzBuzz" if both, else the '
            'number as a string. Return only the code, no explanation.'
        ),
        check=lambda r: (
            'def fizzbuzz' in r and 'Fizz' in r and 'Buzz' in r,
            'expected def fizzbuzz with Fizz and Buzz'
        ),
    ),
    Task(
        name='is_prime',
        message=(
            'Write a Python function called is_prime(n) that returns True if n is prime, '
            'False otherwise. Return only the code, no explanation.'
        ),
        check=lambda r: (
            'def is_prime' in r and '%' in r,
            'expected def is_prime with modulo check'
        ),
    ),
    Task(
        name='fix_bug',
        message=(
            'Fix the bug in this Python function and return only the corrected code:\n\n'
            'def add(a, b):\n    return a - b'
        ),
        check=lambda r: (
            ('a + b' in r or 'a+b' in r),
            'expected return a + b'
        ),
    ),
    Task(
        name='even_numbers',
        message=(
            'Write a Python one-liner using list comprehension that produces a list of '
            'even numbers from 1 to 20. Assign it to a variable called evens. '
            'Return only the code, no explanation.'
        ),
        check=lambda r: (
            'evens' in r and '[' in r and 'for' in r and ('%' in r or '2' in r),
            'expected evens = [... for ... if ... % 2 ...]'
        ),
    ),
    Task(
        name='fibonacci',
        message=(
            'Write a Python function called fibonacci(n) that returns the nth Fibonacci '
            'number (0-indexed, so fibonacci(0)=0, fibonacci(1)=1). '
            'Return only the code, no explanation.'
        ),
        check=lambda r: (
            'def fibonacci' in r and ('fibonacci(n-1)' in r or 'fibonacci(n - 1)' in r
                                      or 'fib' in r.lower() or '[0' in r or 'a, b' in r),
            'expected def fibonacci with recursive or iterative implementation'
        ),
    ),
]


def run_benchmarks(peer_node: str, verbose: bool) -> None:
    print(f'Benchmarking peer mode → {peer_node}')
    print(f'Tasks: {len(TASKS)}\n')

    results = []
    for task in TASKS:
        print(f'  [{task.name}] running...', flush=True)
        start = time.time()
        try:
            # Suppress run_peer's stdout during capture; we still want the return value.
            old_stdout = sys.stdout
            sys.stdout = StringIO()
            try:
                output = run_peer(task.message, peer_node, peer_node)
            finally:
                sys.stdout = old_stdout

            elapsed = time.time() - start
            cleaned = _clean(output)
            passed, reason = task.check(cleaned)
            results.append((task.name, passed, elapsed, reason if not passed else '', output))
            status = 'PASS' if passed else 'FAIL'
            print(f'  [{task.name}] {status}  ({elapsed:.1f}s)')
        except Exception as e:
            elapsed = time.time() - start
            results.append((task.name, False, elapsed, str(e), ''))
            print(f'  [{task.name}] ERROR  ({elapsed:.1f}s)  {e}')

    passed_count = sum(1 for _, p, *_ in results if p)
    total = len(results)
    avg_time = sum(t for _, _, t, *_ in results) / total if total else 0

    print(f'\n{"─" * 55}')
    print(f'  {"Task":<22} {"Result":<8} {"Time":>6}  Note')
    print(f'{"─" * 55}')
    for name, passed, elapsed, note, _ in results:
        status = 'PASS' if passed else 'FAIL'
        print(f'  {name:<22} {status:<8} {elapsed:>5.1f}s  {note}')
    print(f'{"─" * 55}')
    print(f'  {passed_count}/{total} passed  (avg {avg_time:.1f}s per task)')

    if verbose:
        print(f'\n{"─" * 55}')
        print('Responses')
        print(f'{"─" * 55}')
        for name, passed, _, _, output in results:
            status = 'PASS' if passed else 'FAIL'
            print(f'\n[{name}] {status}')
            cleaned = _clean(output)
            print(cleaned[:600] + ('…' if len(cleaned) > 600 else ''))

    sys.exit(0 if passed_count == total else 1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Peer mode benchmarks')
    parser.add_argument('--peer-node', default='pond', help='Target node hostname')
    parser.add_argument('--verbose', '-v', action='store_true', help='Print responses')
    args = parser.parse_args()
    run_benchmarks(args.peer_node, args.verbose)
