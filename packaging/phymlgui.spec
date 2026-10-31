# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for phymlGUI release packages (onedir), run by packaging/package.py
# from a temporary copy of the sources (SPECPATH = <copy>/packaging).
# Windows gets two executables sharing one _internal/: phymlgui.exe (windowed GUI)
# and phymlgui-cli.exe (console, for --file/--batch/--version). Linux gets one.
import os
import sys

src = os.path.dirname(SPECPATH)
windows = sys.platform == 'win32'
icon = os.path.join(src, 'icon.ico') if windows else None

a = Analysis(
    [os.path.join(src, 'phymlgui.py')],
    pathex=[src],
    datas=[(os.path.join(src, 'locales.json'), '.'), (os.path.join(src, 'icon.png'), '.')],
    hiddenimports=['openpyxl'],
    excludes=['tkinter', 'pytest'],
    noarchive=False,
)
pyz = PYZ(a.pure)

gui = EXE(pyz, a.scripts, [], exclude_binaries=True, name='phymlgui',
          console=not windows, icon=icon, upx=False)
targets = [gui]
if windows:
    cli = EXE(pyz, a.scripts, [], exclude_binaries=True, name='phymlgui-cli',
              console=True, icon=icon, upx=False)
    targets.append(cli)

coll = COLLECT(*targets, a.binaries, a.datas, strip=False, upx=False, name='phymlgui')
