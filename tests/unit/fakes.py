"""Test doubles for PipelineRunner: an engine and a MUSCLE that run fake_tool.py."""
import os
import sys
from typing import Dict, List, Tuple

from phyml_core.engines.base import Engine, EngineOutputs, Issue
from phyml_core.launchers import Native

FAKE_TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fake_tool.py')

# the same suffixes as TREE_SUFFIX / STATS_SUFFIX in fake_tool.py
_TREE_SUFFIX = '_fake_tree.txt'
_STATS_SUFFIX = '_fake_stats.txt'


class FakeEngine(Engine):
    """An engine whose program is fake_tool.py.

    params['fake_mode']: 'ok' (default), 'exit3', 'notree', 'hang' or 'raise' (command()
    raises RuntimeError('boom')); a dict picks the mode per input by the PHYLIP file's stem.
    params['fake_issues'] is what validate() returns, params['fake_notes'] the notes of
    normalize().
    """
    key = 'fake'
    name = 'Fake'
    label_key = 'engine_fake'

    def models(self, datatype: str) -> List[str]:
        return ['FAKE']

    def validate(self, params: dict, paths) -> List[Issue]:
        return list(params.get('fake_issues', []))

    def normalize(self, params: dict) -> Tuple[dict, List[Issue]]:
        return dict(params), list(params.get('fake_notes', []))

    def executable(self, params: dict, paths) -> str:
        return sys.executable

    def command(self, exe: str, phylip: str, params: dict) -> List[str]:
        mode = params.get('fake_mode', 'ok')
        if isinstance(mode, dict):
            mode = mode.get(os.path.splitext(os.path.basename(phylip))[0], 'ok')
        if mode == 'raise':
            raise RuntimeError('boom')
        return [sys.executable, FAKE_TOOL, mode, phylip]

    def outputs(self, phylip: str) -> EngineOutputs:
        return EngineOutputs(tree=phylip + _TREE_SUFFIX, stats=phylip + _STATS_SUFFIX,
                             boot_trees=None, log=None)

    def parse_stats(self, outputs: EngineOutputs) -> Dict[str, str]:
        try:
            with open(outputs.stats, encoding='utf-8') as handle:
                lines = handle.read().splitlines()
        except OSError:
            return {}
        return dict(line.split('=', 1) for line in lines if '=' in line)

    def launcher(self, params: dict) -> Native:
        return Native()


def fake_muscle(tmp_path, mode: str) -> str:
    """A muscle-<mode>.cmd in tmp_path that runs fake_tool.py in that MUSCLE mode."""
    if os.name != 'nt':   # a POSIX shell script on Linux
        script = os.path.join(str(tmp_path), f'muscle-{mode}')
        with open(script, 'w', encoding='utf-8', newline='\n') as handle:
            handle.write('#!/bin/sh\n')
            handle.write(f'exec "{sys.executable}" "{FAKE_TOOL}" {mode} "$@"\n')
        os.chmod(script, 0o755)
        return script
    script = os.path.join(str(tmp_path), f'muscle-{mode}.cmd')
    with open(script, 'w', encoding='oem', newline='\r\n') as handle:
        handle.write('@echo off\n')
        handle.write(f'"{sys.executable}" "{FAKE_TOOL}" {mode} %*\n')
        handle.write('exit /b %errorlevel%\n')
    return script
