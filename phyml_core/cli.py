"""Headless CLI: run the same pipeline without the GUI (and without Qt).

    python phymlgui.py --file input.fasta
    python phymlgui.py --batch folder/ --config preset.json

Settings come from the config file in the data folder (as in the window; the working
folder is not consulted); --config is a JSON object laid over them. A damaged config file
is reported on stderr and the defaults are used, as in the window. Log lines go to stdout, except level 'error' lines, which go to stderr.
Exit codes: 0 - every file succeeded; 1 - a file failed or the run was cancelled;
2 - usage or input problem (no --file/--batch, missing path, empty folder, no usable
data folder, unreadable settings, unreadable or invalid --config).
"""
import argparse
import json
import os
import sys

from . import settings
from .i18n import _t
from . import __version__
from .paths import AppPaths
from .runner import PipelineRunner

FASTA_EXTENSIONS = ('.fasta', '.fas', '.fa')


class _Usage(Exception):
    """Ends the run with exit code 2; the argument is the message for stderr."""


def _emit(stream, text):
    """Print a line without ever failing on a console code page that lacks a character."""
    try:
        print(text, file=stream, flush=True)
    except UnicodeEncodeError:
        encoding = getattr(stream, 'encoding', None) or 'ascii'
        print(text.encode(encoding, 'replace').decode(encoding), file=stream, flush=True)
    except (OSError, ValueError):   # closed or broken pipe: nothing useful left to do
        pass


def _make_tolerant(stream):
    reconfigure = getattr(stream, 'reconfigure', None)
    if reconfigure is not None:
        try:
            reconfigure(errors='replace')
        except (OSError, ValueError):
            pass


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise _Usage(self.format_usage().rstrip() + '\n' + message)


def _collect_files(args):
    if args.batch:
        if not os.path.isdir(args.batch):
            raise _Usage(_t('err_box_msg'))
        # the same rule as the window: *_aligned.fasta are this app's own MUSCLE outputs
        files = sorted(os.path.join(args.batch, f) for f in os.listdir(args.batch)
                       if f.lower().endswith(FASTA_EXTENSIONS)
                       and not f.lower().endswith('_aligned.fasta'))
        if not files:
            raise _Usage(_t('batch_empty'))
        return files
    if not os.path.isfile(args.file):
        raise _Usage(_t('err_box_msg'))
    return [args.file]


def _load_params(paths, config_arg):
    try:
        raw = settings.load(paths.config_file,
                            on_error=lambda message: _emit(sys.stderr, message))
        params = settings.resolve_cores(settings.from_disk(raw, paths))
    except OSError as e:
        raise _Usage(f'{paths.config_file}: {e}') from e
    if config_arg:
        try:
            with open(config_arg, encoding='utf-8-sig') as f:
                overlay = json.load(f)
        except (OSError, ValueError) as e:   # includes JSONDecodeError and UnicodeDecodeError
            raise _Usage(f'{config_arg}: {e}') from e
        if not isinstance(overlay, dict):
            raise _Usage(f'{config_arg}: not a JSON object')
        params.update(overlay)
    return params


def main(argv=None) -> int:
    _make_tolerant(sys.stdout)
    _make_tolerant(sys.stderr)
    parser = _Parser(prog='phymlgui', description='phymlGUI headless pipeline')
    parser.add_argument('--file', help='single FASTA file')
    parser.add_argument('--batch', help='folder with FASTA files')
    parser.add_argument('--config', help='JSON object laid over the saved settings')
    parser.add_argument('--version', action='version', version=f'phymlGUI {__version__}')
    try:
        args = parser.parse_args(argv)
        if not args.file and not args.batch:
            parser.error('specify --file or --batch')
        files = _collect_files(args)
        try:
            paths = AppPaths.detect()
        except OSError as e:
            raise _Usage(str(e)) from e
        params = _load_params(paths, args.config)
    except _Usage as e:
        _emit(sys.stderr, str(e))
        return 2
    except SystemExit as e:   # --help (0)
        return e.code if isinstance(e.code, int) else 0

    def on_log(level, text):
        _emit(sys.stderr if level == 'error' else sys.stdout, text.rstrip('\r\n'))

    result = PipelineRunner(params, files, paths, on_log=on_log).run()  # never raises
    trees = [f.tree for f in result.files if f.status == 'ok' and f.tree]
    _emit(sys.stdout, 'OK' if result.success else 'FAILED')
    if trees:
        _emit(sys.stdout, 'tree: ' + trees[-1])
    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(main())
