from typing import Callable, Optional

from PySide6.QtWidgets import (QStatusBar, QLabel, QProgressBar, QSizePolicy,
                             QToolButton, QPushButton)
from PySide6.QtCore import QTimer, Signal

from phyml_core.i18n import _t
from phyml_core.utils import psutil


class AppStatusBar(QStatusBar):
    """Core counts, system CPU load, the CPU use of the running analysis, and the
    'open folder' / 'settings' buttons."""

    open_dir_clicked = Signal()
    settings_clicked = Signal()

    def __init__(self, phys_cores, logi_cores, parent=None):
        super().__init__(parent)
        self.setSizeGripEnabled(False)
        self.cores_label = QLabel(_t("cores_info").format(phys_cores, logi_cores))
        self.cpu_sys_label = QLabel(_t("cpu_sys").format(0))
        self.cpu_sys_bar = QProgressBar()
        self.cpu_sys_bar.setRange(0, 100)
        self.cpu_sys_bar.setTextVisible(True)
        self.cpu_sys_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.cpu_run_label = QLabel(_t("cpu_analysis_idle"))
        self.open_dir_btn = QToolButton()
        self.open_dir_btn.setText(_t("btn_open_dir"))
        self.open_dir_btn.setEnabled(False)
        self.open_dir_btn.clicked.connect(self.open_dir_clicked)
        self.settings_btn = QPushButton(_t("btn_settings"))
        self.settings_btn.clicked.connect(self.settings_clicked)
        self.addWidget(self.cores_label)
        self.addWidget(self.cpu_sys_label)
        self.addWidget(self.cpu_sys_bar, 1)  # stretch: fills all free space
        self.addPermanentWidget(self.cpu_run_label)
        self.addPermanentWidget(self.open_dir_btn)
        self.addPermanentWidget(self.settings_btn)  # far bottom-right corner

        self.samples = []        # CPU use (percent of one core) of the run, one per tick
        self._mon_procs = {}
        self._pid_provider: Optional[Callable[[], Optional[int]]] = None
        self.cpu_timer = QTimer(self)
        self.cpu_timer.setInterval(1000)
        self.cpu_timer.timeout.connect(self.update_cpu_status)
        if psutil is not None:
            self.cpu_timer.start()

    def set_open_dir_enabled(self, on: bool) -> None:
        self.open_dir_btn.setEnabled(on)

    def track(self, pid_provider: Callable[[], Optional[int]]) -> None:
        """Start collecting CPU samples of the process tree whose root pid the provider
        returns (None while nothing runs)."""
        self.samples = []
        self._mon_procs = {}
        self._pid_provider = pid_provider

    def stop_tracking(self) -> float:
        """Stop collecting, show the average of the samples and return it."""
        self._pid_provider = None
        avg = sum(self.samples) / len(self.samples) if self.samples else 0.0
        self.cpu_run_label.setText(_t("cpu_analysis_done").format(int(avg), round(avg / 100, 1)))
        return avg

    def update_cpu_status(self):
        if psutil is None:
            return
        sys_pct = psutil.cpu_percent(interval=None)
        self.cpu_sys_bar.setValue(int(sys_pct))
        self.cpu_sys_label.setText(_t("cpu_sys").format(int(sys_pct)))
        pid = self._pid_provider() if self._pid_provider is not None else None
        if pid is not None:
            try:
                root = psutil.Process(pid)
                pids = {pid} | {c.pid for c in root.children(recursive=True)}
            except psutil.Error:
                return
            # cpu_percent() keeps per-call state inside each Process object,
            # so objects must be reused across ticks to get non-zero values
            for k in list(self._mon_procs):
                if k not in pids:
                    del self._mon_procs[k]
            total = 0.0
            for p in pids:
                obj = self._mon_procs.get(p)
                if obj is None:
                    try:
                        obj = self._mon_procs[p] = psutil.Process(p)
                    except psutil.Error:
                        continue
                try:
                    total += obj.cpu_percent(interval=None)
                except psutil.Error:
                    pass
            self.samples.append(total)
            self.cpu_run_label.setText(_t("cpu_analysis").format(int(total), round(total / 100, 1)))
