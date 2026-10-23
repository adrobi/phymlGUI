# phymlGUI: Automated Pipeline for Phylogenetic Analysis

[English Version](#english) | [Русская версия](#russian)

---

<a name="english"></a>
## 🇺🇸 English Version

**phymlGUI** is a graphical interface for Windows that automates the construction of phylogenetic trees using the Maximum Likelihood method.

### 🛠 Core Capabilities
* **Integrated Pipeline:** Automatically detects unaligned sequences and runs **MUSCLE** before passing data to **PhyML**.
* **Parallel Computing (MPI):** Supports execution via `mpirun`/`mpiexec` for multi-core processing.
* **Data Sanitization:** Automatically cleans sequence IDs and alignments from characters that cause PhyML to crash (dots, colons, brackets, spaces).
* **Format Conversion:** Converts `FASTA` to `PHYLIP-relaxed` format, supporting long sequence names.
* **Visualization:** Built-in viewer for Newick trees with support for branch labels and image export.
* **Configuration Persistence:** Automatic saving and loading of all parameters and file paths via `phyml_config.json`.

### ⚙️ Requirements
* **Executables:** `phyml.exe` (or MPI version) and `muscle.exe`.
* **Python packages:** Python 3.9+ with `PySide6`, `matplotlib` and `biopython` (`pip install -r requirements.txt`).
* **MPI Environment:** For parallel mode, **Microsoft MPI** is required (install `msmpisetup.exe` from the official Microsoft GitHub).

---

<a name="russian"></a>
## 🇷🇺 Русская версия

**phymlGUI** — графический интерфейс для Windows, автоматизирующий построение филогенетических деревьев методом максимального правдоподобия.

### 🛠 Основные возможности
* **Интегрированный пайплайн:** Автоматическое определение невыровненных последовательностей и запуск **MUSCLE** перед началом работы **PhyML**.
* **Параллельные вычисления (MPI):** Поддержка запуска через `mpirun`/`mpiexec` для распределения нагрузки на несколько ядер процессора.
* **Санитарная очистка данных:** Автоматическая замена символов в ID и последовательностях, вызывающих ошибки в PhyML (точки, двоеточия, скобки, пробелы).
* **Конвертация форматов:** Перевод из `FASTA` в `PHYLIP-relaxed` с поддержкой длинных названий последовательностей.
* **Визуализация:** Встроенный просмотрщик деревьев в формате Newick с отображением поддержек ветвей и возможностью сохранения графики.
* **Сохранение состояния:** Автоматическое сохранение всех настроек и путей в файл `phyml_config.json`.

### ⚙️ Требования
* **Программные файлы:** `phyml.exe` (или MPI-версия) и `muscle.exe`.
* **Python-зависимости:** Python 3.9+ с пакетами `PySide6`, `matplotlib` и `biopython` (`pip install -r requirements.txt`).
* **Среда MPI:** Для работы в параллельном режиме требуется установленный **Microsoft MPI** (инсталлятор `msmpisetup.exe` можно найти на официальном GitHub Microsoft).

---

## 📂 Output Files / Выходные файлы

* `*_aligned.fasta` — Aligned sequences / Выровненные последовательности.
* `*.phy` — Prepared PHYLIP format / Подготовленный формат PHYLIP.
* `*_phyml_tree.txt` — Resulting ML Tree (Newick) / Итоговое дерево (Newick).
* `*_phyml_stats.txt` — Analysis statistics / Статистика анализа.

## Credits & Acknowledgments / Авторы и благодарности

* **PhyML:** The core phylogenetic analysis is powered by [PhyML](https://github.com/stephaneguindon/phyml), developed by Stephane Guindon and his team.
  * *Citation:* Guindon S, et al. "New Algorithms and Methods to Estimate Maximum-Likelihood Phylogenies: Assessing the Performance of PhyML 3.0." Systematic Biology, 2010.
* **phymlGUI:** This wrapper/GUI was developed by Aleksey Drobin.

### License
This project is licensed under the MIT License, but the included binaries (`phyml-mpi.exe`) are subject to their own respective licenses (GPL).