# phymlGUI: Automated Pipeline for Phylogenetic Analysis

[English Version](#english) | [Русская версия](#russian)

---

<a name="english"></a>
## 🇺🇸 English Version

**phymlGUI** is a graphical interface for Windows that automates the construction of phylogenetic trees using the Maximum Likelihood method.

### 🛠 Core Capabilities
* **Two Engines:** **PhyML** (serial or MPI) and **IQ-TREE** (automatic model selection with ModelFinder, ultrafast bootstrap) — switchable in Settings.
* **Integrated Pipeline:** Automatically detects unaligned sequences and runs **MUSCLE** before passing data to the engine.
* **Parallel Computing (MPI):** Supports execution via `mpirun`/`mpiexec` for multi-core processing; MPI binaries are detected automatically and misconfigured bootstrap runs are blocked with an explanation.
* **Batch Mode:** Process a whole folder of FASTA files in one run — a live per-file queue with statuses, retry of failed files, an N/M summary and automatic `phymlgui_summary.csv` / `.xlsx` reports.
* **Hardware Awareness:** Physical/logical core detection (the `np` field is pre-filled), plus a live CPU status bar showing both system load and the utilization of the analysis process tree.
* **Tree Viewer:** Rectangular / slanted / circular layouts, support-value threshold highlighting, clade collapsing, outgroup rerooting, majority-rule consensus from bootstrap trees, Robinson–Foulds topology comparison and PNG/SVG/PDF export.
* **Run History and Presets:** every run is recorded (double-click reloads its tree); built-in and user parameter presets.
* **Headless CLI:** `python phymlgui.py --file data.fasta` / `--batch folder/` runs the same pipeline without the GUI. Settings come from the data folder (not from a `phyml_config.json` in the current directory); `--config preset.json` is a JSON object laid over them. Exit codes: 0 success, 1 a file failed or the run was cancelled, 2 usage or input problem.
* **Data Sanitization / Conversion:** cleans sequence IDs, converts `FASTA` to `PHYLIP-relaxed`.
* **Themes:** light/dark (can follow the Windows system theme) with a selectable accent color.

### ⚙️ Requirements
* **Executables:** `phyml.exe` (or MPI version) and `muscle.exe`.
* **Python packages:** Python 3.11+ with `PySide6`, `matplotlib`, `biopython` and `psutil` (`pip install -r requirements.txt`).
* **MPI Environment:** For parallel mode, **Microsoft MPI** is required (install `msmpisetup.exe` from the official Microsoft GitHub).
* **Settings and history:** stored next to the exe when that folder is writable, otherwise in `%APPDATA%\phymlGUI`. Set `PHYMLGUI_DATA_DIR` to use another folder.

### 🧪 Tests
```
pip install -r requirements.txt -r requirements-dev.txt
python scripts/fetch_third_party.py --dest bin   # pinned IQ-TREE and MUSCLE (SHA256-verified)
python -m pytest
```
Analysis binaries are looked up in `bin/` and in the variables `PHYMLGUI_PHYML`, `PHYMLGUI_MPIEXEC`, `PHYMLGUI_IQTREE`, `PHYMLGUI_MUSCLE`, `PHYMLGUI_RAXML` (full path to the executable). Tests that need a missing binary are skipped. Markers: `needs_phyml`, `needs_mpi`, `needs_iqtree`, `needs_muscle`, `slow`; CI runs plain `python -m pytest -q -rs`; the tests whose binaries are not installed there are skipped. Tests never touch your real settings: they use an isolated data folder.

---

<a name="russian"></a>
## 🇷🇺 Русская версия

**phymlGUI** — графический интерфейс для Windows, автоматизирующий построение филогенетических деревьев методом максимального правдоподобия.

### 🛠 Основные возможности
* **Два движка:** **PhyML** (последовательно или MPI) и **IQ-TREE** (автоподбор модели ModelFinder, ультрабыстрый бутстреп) — переключение в настройках.
* **Интегрированный пайплайн:** Автоматическое определение невыровненных последовательностей и запуск **MUSCLE** перед анализом.
* **Параллельные вычисления (MPI):** Запуск через `mpirun`/`mpiexec`; MPI-бинарники определяются автоматически, некорректная конфигурация бутстрепа блокируется с пояснением.
* **Пакетный режим:** Обработка папки FASTA-файлов — живая очередь со статусами, повтор неудавшихся, сводка N/M и автоматические отчёты `phymlgui_summary.csv` / `.xlsx`.
* **Аппаратная осведомлённость:** Определение физических/логических ядер и живая строка состояния с загрузкой CPU — системы и дерева процессов анализа.
* **Просмотрщик деревьев:** Прямоугольная/сланцевая/круговая раскладки, подсветка поддержек по порогу, сворачивание клад, рерутинг по outgroup, консенсус большинства из бутстреп-деревьев, сравнение топологий по Робинсону–Фаулдсу, экспорт PNG/SVG/PDF.
* **История и пресеты:** каждый запуск записывается (двойной клик загружает его дерево); встроенные и пользовательские пресеты параметров.
* **Консольный режим:** `python phymlgui.py --file data.fasta` / `--batch папка/` — тот же пайплайн без GUI. Настройки берутся из папки данных (а не из `phyml_config.json` в текущей папке); `--config preset.json` — JSON-объект, накладываемый поверх них. Коды выхода: 0 — успех, 1 — файл не обработан или запуск отменён, 2 — ошибка аргументов или входных данных.
* **Очистка и конвертация:** санитарная очистка ID, перевод `FASTA` → `PHYLIP-relaxed`.
* **Темы:** светлая/тёмная (могут следовать системной Windows) с выбором акцентного цвета.

### ⚙️ Требования
* **Программные файлы:** `phyml.exe` (или MPI-версия) и `muscle.exe`.
* **Python-зависимости:** Python 3.11+ с пакетами `PySide6`, `matplotlib`, `biopython` и `psutil` (`pip install -r requirements.txt`).
* **Среда MPI:** Для работы в параллельном режиме требуется установленный **Microsoft MPI** (инсталлятор `msmpisetup.exe` можно найти на официальном GitHub Microsoft).
* **Настройки и история:** хранятся рядом с exe, если папка доступна для записи, иначе в `%APPDATA%\phymlGUI`. Другую папку можно задать переменной `PHYMLGUI_DATA_DIR`.

### 🧪 Тесты
```
pip install -r requirements.txt -r requirements-dev.txt
python scripts/fetch_third_party.py --dest bin   # закреплённые IQ-TREE и MUSCLE (проверка SHA256)
python -m pytest
```
Бинарники анализа ищутся в `bin/` и в переменных `PHYMLGUI_PHYML`, `PHYMLGUI_MPIEXEC`, `PHYMLGUI_IQTREE`, `PHYMLGUI_MUSCLE`, `PHYMLGUI_RAXML` (полный путь к exe). Тесты, которым нужен отсутствующий бинарник, пропускаются. Маркеры: `needs_phyml`, `needs_mpi`, `needs_iqtree`, `needs_muscle`, `slow`; CI запускает просто `python -m pytest -q -rs`; тесты, для которых на CI нет бинарников, пропускаются. Тесты не трогают ваши настройки: они работают в изолированной папке данных.

---

## 📂 Output Files / Выходные файлы

* `*_aligned.fasta` — Aligned sequences / Выровненные последовательности.
* `*.phy` — Prepared PHYLIP format / Подготовленный формат PHYLIP.
* `*_phyml_tree.txt` — Resulting ML Tree (Newick) / Итоговое дерево (Newick).
* `*_phyml_stats.txt` — Analysis statistics / Статистика анализа.
* `phymlgui_summary.csv` — Per-file run summary (batch-friendly) / Сводка результатов по файлам.

## Credits & Acknowledgments / Авторы и благодарности

* **PhyML:** The core phylogenetic analysis is powered by [PhyML](https://github.com/stephaneguindon/phyml), developed by Stephane Guindon and his team.
  * *Citation:* Guindon S, et al. "New Algorithms and Methods to Estimate Maximum-Likelihood Phylogenies: Assessing the Performance of PhyML 3.0." Systematic Biology, 2010.
* **phymlGUI:** This wrapper/GUI was developed by Aleksey Drobin.

### License
This project is licensed under the MIT License, but the included binaries (`phyml-mpi.exe`) are subject to their own respective licenses (GPL).