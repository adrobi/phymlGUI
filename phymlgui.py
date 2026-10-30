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
    app = QApplication(sys.argv)
    window = PhyMLApp()
    window.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
