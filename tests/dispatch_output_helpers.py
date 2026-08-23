"""Shared helpers for gateway dispatch-output tests.

Extracted from test_dispatch_output_package.py and
test_factory_hook_output.py to eliminate the 87% AST-similar
``test_no_delegate_outputs_full_package`` duplicate (INFRA-481).
"""

import argparse
import json


def assert_no_delegate_outputs_full_package(gw, tmp_path, capsys, package) -> None:
    """Assert the --no-delegate branch outputs the full package JSON verbatim.

    Builds a --no-delegate args namespace, runs ``gw._dispatch_output``,
    and asserts stdout parses back to exactly *package*.
    """
    args = argparse.Namespace(host="factory", event="session-start", no_delegate=True)

    gw._dispatch_output(args, package, "{}", {}, tmp_path, 0)

    captured = capsys.readouterr()
    output = json.loads(captured.out.strip())
    assert output == package
    assert "allowed_reads" in output
