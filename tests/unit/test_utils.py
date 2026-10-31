import os
import sys

from conftest import ROOT

from phyml_core.utils import resource_path


def test_resource_path_does_not_depend_on_the_cwd(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, '_MEIPASS', raising=False)
    monkeypatch.chdir(tmp_path)
    for name in ('icon.png', 'locales.json'):
        assert os.path.samefile(resource_path(name), ROOT / name)


def test_resource_path_uses_the_bundle_folder_when_frozen(tmp_path, monkeypatch):
    monkeypatch.setattr(sys, '_MEIPASS', str(tmp_path), raising=False)
    assert resource_path('icon.png') == str(tmp_path / 'icon.png')
