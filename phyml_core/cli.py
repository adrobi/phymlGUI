"""Headless CLI: run the same pipeline without the GUI.

    python phymlgui.py --file input.fasta
    python phymlgui.py --batch folder/ --config preset.json
"""
import argparse
import json
import os
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(prog='phymlgui', description='phymlGUI headless pipeline')
    parser.add_argument('--file', help='single FASTA file')
    parser.add_argument('--batch', help='folder with FASTA files')
    parser.add_argument('--config', default='phyml_config.json',
                        help='config JSON (defaults to phyml_config.json)')
    args = parser.parse_args(argv)

    if not args.file and not args.batch:
        parser.error('specify --file or --batch')

    from phyml_core.i18n import _t
    from phyml_core.paths import AppPaths
    from phyml_core.runner import PipelineRunner

    config = {}
    if os.path.exists(args.config):
        with open(args.config, encoding='utf-8') as f:
            config = json.load(f)

    if args.batch:
        files = sorted(os.path.join(args.batch, f) for f in os.listdir(args.batch)
                       if f.lower().endswith(('.fasta', '.fas', '.fa'))
                       and not f.lower().endswith('_aligned.fasta'))
        if not files:
            print(_t("batch_empty"))
            return 2
    else:
        files = [args.file]

    runner = PipelineRunner(config, files, AppPaths.detect(),
                            on_log=lambda level, text: print(text))
    result = runner.run()  # synchronous, never raises
    trees = [f.tree for f in result.files if f.status == 'ok' and f.tree]

    print('OK' if result.success else 'FAILED')
    if trees:
        print('tree:', trees[-1])
    return 0 if result.success else 1


if __name__ == '__main__':
    sys.exit(main())
