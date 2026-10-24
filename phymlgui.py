"""phymlGUI entry point. Application code lives in phyml_core/ and phyml_ui/."""
import sys

from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: F401  (re-exported for compatibility)

from phyml_core import __version__  # noqa: F401
from phyml_core.i18n import _t, LANG, STRINGS  # noqa: F401
from phyml_core.pipeline import PipelineWorker  # noqa: F401
from phyml_core.utils import psutil, detect_cores, is_mpi_binary, resource_path  # noqa: F401
from phyml_ui.main_window import PhyMLApp  # noqa: F401
from phyml_ui.tree_viewer import TreeViewerDialog  # noqa: F401


def main():
    if len(sys.argv) > 1:
        from phyml_core.cli import main as cli_main
        sys.exit(cli_main())
    app = QApplication(sys.argv)
    window = PhyMLApp()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
