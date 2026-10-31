"""phymlGUI entry point. Application code lives in phyml_core/ and phyml_ui/.

With arguments it runs the headless CLI and never imports PySide6; the GUI is imported
only when started without arguments.
"""
import sys


def main():
    if len(sys.argv) > 1:
        from phyml_core.cli import main as cli_main
        sys.exit(cli_main())
    from PySide6.QtWidgets import QApplication
    from phyml_ui.main_window import PhyMLApp
    from PySide6.QtWidgets import QMessageBox
    app = QApplication(sys.argv)
    try:
        window = PhyMLApp()
    except OSError as e:   # e.g. the data folder cannot be created
        QMessageBox.critical(None, 'phymlGUI', str(e))
        sys.exit(1)
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
