import os

import pytest

from phyml_core.utils import psutil
from phyml_ui.status_bar import AppStatusBar

pytestmark = pytest.mark.skipif(psutil is None, reason='psutil not installed')


def test_track_samples_the_process_and_stop_tracking_averages(qtbot):
    bar = AppStatusBar(2, 4)
    qtbot.addWidget(bar)
    bar.track(lambda: os.getpid())
    bar.update_cpu_status()
    bar.update_cpu_status()
    assert len(bar.samples) == 2
    bar.samples = [100.0, 50.0]
    assert bar.stop_tracking() == 75.0
    bar.update_cpu_status()          # tracking stopped: no more samples
    assert bar.samples == [100.0, 50.0]


def test_stop_tracking_without_samples_is_zero(qtbot):
    bar = AppStatusBar(2, 4)
    qtbot.addWidget(bar)
    assert bar.stop_tracking() == 0.0


def test_buttons_emit_signals(qtbot):
    bar = AppStatusBar(2, 4)
    qtbot.addWidget(bar)
    assert not bar.open_dir_btn.isEnabled()
    bar.set_open_dir_enabled(True)
    with qtbot.waitSignal(bar.open_dir_clicked):
        bar.open_dir_btn.click()
    with qtbot.waitSignal(bar.settings_clicked):
        bar.settings_btn.click()
