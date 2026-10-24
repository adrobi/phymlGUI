"""Headless CLI: run the same pipeline without the GUI.

    python phymlgui.py --file input.fasta
    python phymlgui.py --batch folder/ --config preset.json
"""
import argparse
import json
import os
import sys

from PySide6.QtCore import QCoreApplication


def main(argv=None):
    parser = argparse.ArgumentParser(prog='phymlgui', description='phymlGUI headless pipeline')
    parser.add_argument('--file', help='single FASTA file')
    parser.add_argument('--batch', help='folder with FASTA files')
    parser.add_argument('--config', default='phyml_config.json',
                        help='config JSON (defaults to phyml_config.json)')
    args = parser.parse_args(argv)

    if not args.file and not args.batch:
        parser.error('specify --file or --batch')

    from phyml_core.pipeline import PipelineWorker
    from phyml_core.i18n import _t

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

    app = QCoreApplication.instance() or QCoreApplication([])
    worker = PipelineWorker(config, files)
    worker.log_signal.connect(print)
    result = {}
    worker.finished_signal.connect(lambda ok, tree: result.update(ok=ok, tree=tree))
    worker.run()  # synchronous, no event loop needed

    print('OK' if result.get('ok') else 'FAILED')
    if result.get('tree'):
        print('tree:', result['tree'])
    return 0 if result.get('ok') else 1


if __name__ == '__main__':
    sys.exit(main())
