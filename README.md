# phymlGUI: Automated Pipeline for Phylogenetic Analysis / Автоматизированный пайплайн для филогенетического анализа 🧬

[English Version](#english) | [Русская версия](#russian)

---

<a name="english"></a>
## 🇺🇸 English Version

**phymlGUI** is a user-friendly graphical application for Windows designed to automate routine tasks in constructing phylogenetic trees. The program combines sequence alignment, format conversion, data cleaning, and complex Maximum Likelihood algorithms into a single click.

### 🌟 Key Features
* **Full Automation:** The pipeline automatically checks sequence lengths. If they are not aligned, the program runs **MUSCLE** and passes the result to **PhyML**.
* **Smart Conversion:** Automatic conversion from `FASTA` to `PHYLIP` format with support for long names (up to 100 characters).
* **Data Sanitization:** The program automatically finds and replaces invalid characters (dots, brackets, commas) in sequence names and alignments to prevent PhyML crashes.
* **Built-in Tree Viewer:** Upon completion, the program renders the final tree directly in the GUI (with zoom and save image capabilities).
* **Instant Auto-save:** All settings and file paths are saved automatically. The program "remembers" everything for your next session.
* **Isolated Processes:** The interface remains responsive during calculations. You can run multiple instances to analyze different files simultaneously.

### 🛠 Installation and Setup
The program is provided as a "Portable" folder and does not require Python or additional libraries.
1. Unpack the archive into a convenient folder (preferably without non-Latin characters or spaces in the path).
2. The pipeline requires external executables:
   * Download **PhyML** (`phyml.exe`).
   * Download **MUSCLE** (`muscle.exe`).
3. Place `phyml.exe` and `muscle.exe` in the same folder as `phymlGUI.exe` for convenience.
4. Run `phymlGUI.exe`.

### 🚀 Quick Start
1. **Set Paths:** Click "Browse..." in the top section to locate `phyml.exe` and `muscle.exe`.
2. **Select Data:** Click "Select FASTA" and choose your file containing nucleotide or amino acid sequences.
3. **Configure Parameters:** Select the evolutionary model (e.g., `GTR` or `HKY85`) and branch support method (`Bootstrap 100` for accuracy or `aLRT -1` for speed).
4. **Run:** Ensure "Show tree after completion" is checked and click the blue **"Start Analysis"** button.
5. **Result:** Monitor the "Execution Log." Once finished, a tree visualization window will appear!

---

<a name="russian"></a>
## 🇷🇺 Русская версия

**phymlGUI** — это удобное графическое приложение для Windows, предназначенное для автоматизации рутинных задач при построении филогенетических деревьев. Программа объединяет выравнивание последовательностей, конвертацию форматов, очистку данных и запуск сложных алгоритмов максимального правдоподобия (Maximum Likelihood) в один клик.

### 🌟 Основные возможности
* **Полная автоматизация:** Пайплайн автоматически проверяет длины последовательностей. Если они не выровнены, программа сама запускает **MUSCLE**, а затем передает результат в **PhyML**.
* **Умная конвертация:** Автоматический перевод из формата `FASTA` в `PHYLIP` с поддержкой длинных имен (до 100 символов).
* **Санитарная очистка данных:** Программа автоматически находит и заменяет недопустимые символы (точки, скобки, запятые) в названиях последовательностей и самих выравниваниях, предотвращая сбои PhyML.
* **Встроенный просмотрщик деревьев:** По завершении анализа программа автоматически отрисует итоговое дерево прямо в графическом окне (с возможностью масштабирования и сохранения картинки).
* **Мгновенное автосохранение:** Все ваши настройки и пути к файлам автоматически сохраняются при любом изменении.
* **Изолированные процессы:** Интерфейс никогда не зависает во время расчетов.

### 🛠 Установка и подготовка к работе
Программа является "портативной" (Portable) и не требует установки Python.
1. Распакуйте архив в папку (желательно, чтобы путь не содержал русских букв и пробелов).
2. Вам потребуются сторонние файлы:
   * Скачайте **PhyML** (`phyml.exe`).
   * Скачайте **MUSCLE** (`muscle.exe`).
3. Поместите их в папку с программой `phymlGUI.exe`.
4. Запустите `phymlGUI.exe`.

### 🚀 Быстрый старт
1. **Укажите пути:** Нажмите «Обзор...» и укажите пути к `phyml.exe` и `muscle.exe`.
2. **Выберите данные:** Нажмите «Выбрать FASTA» и укажите ваш файл с последовательностями.
3. **Настройте параметры:** Выберите модель эволюции и метод поддержки ветвей (рекомендуется `Bootstrap 100` или `aLRT -1`).
4. **Запуск:** Нажмите синюю кнопку **«Запуск анализа»**.
5. **Результат:** Следите за процессом в "Журнале выполнения". По завершении откроется окно визуализации!

---

## 📂 Files / Файлы

### Input / Входные данные:
* Format: `.fasta`, `.fas`, `.fa`.
* Requirement: More than one sequence / Более одной последовательности.

### Output / Выходные данные:
* `*_aligned.fasta` — Aligned sequences / Выровненные последовательности.
* `*.phy` — PHYLIP format / Формат PHYLIP.
* `*_phyml_stats.txt` — Statistics / Статистика расчетов.
* **`*_phyml_tree.txt`** — **Main ML Tree (Newick format) / Итоговое ML дерево.**
* `*_phyml_boot_trees.txt` — Intermediate bootstrap trees / Промежуточные деревья бутстрапа.

---

## ⚠️ FAQ / Решение проблем

* **Alignment doesn't start / Выравнивание не начинается:** Check the path to `muscle.exe` / Проверьте путь к `muscle.exe`.
* **Program hangs / Программа "зависла":** Bootstrap analysis on long sequences takes a lot of time. Try **aLRT (-1)** for faster results / Бутстрап на длинных данных требует много времени. Попробуйте **aLRT (-1)** для скорости.
* **Tree looks messy / Дерево выглядит странно:** For professional publication-ready figures, upload the `_phyml_tree.txt` to **iTOL** (itol.embl.de) / Для подготовки публикации загрузите файл дерева в **iTOL**.