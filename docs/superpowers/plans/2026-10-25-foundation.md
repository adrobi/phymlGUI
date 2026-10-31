# Фундамент — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** вынести логику phymlGUI в ядро без Qt (пути, настройки, история, пресеты, выравнивание, движки, запуск), оставить в `phyml_ui` тонкую оболочку, перевести тесты на pytest и запустить их в CI.

**Architecture:** `phyml_core` — чистый Python, общается с интерфейсом через колбэки и dataclass-результаты; `phyml_ui` собирает окно из небольших модулей и оборачивает `PipelineRunner` в `QThread`. Переход идёт мелкими шагами: после каждой задачи приложение работает, а `python -m pytest` зелёный.

**Tech Stack:** Python ≥ 3.11, PySide6 ≥ 6.5, Biopython, psutil, openpyxl, matplotlib; pytest ≥ 8, pytest-qt ≥ 4.4; GitHub Actions `windows-latest`.

**Spec:** [docs/superpowers/specs/2026-10-25-foundation-design.md](../specs/2026-10-25-foundation-design.md)

## Global Constraints

- `phyml_core` не импортирует PySide6 — ни напрямую, ни транзитивно.
- Python ≥ 3.11; матрица CI — 3.11 и 3.13.
- Параметры прогона — плоский словарь с ключами нынешнего `phyml_config.json`; существующие конфиги и пресеты продолжают загружаться.
- Все видимые пользователю строки — через `_t(key)`; каждый новый ключ есть и в `en`, и в `ru` файла `locales.json` (тексты — в разделе «Новые строки локализации»).
- Файлы данных — `phyml_config.json` и `phyml_history.json` в `AppPaths.data_dir`; переопределение — переменная окружения `PHYMLGUI_DATA_DIR`.
- Тесты не читают и не пишут настоящие `phyml_config.json` / `phyml_history.json` пользователя.
- Внешний вид и раскладка окна не меняются.
- Работа идёт в ветке `foundation`; сообщения коммитов — английское предложение в стиле истории репозитория, в конце `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Команда тестов: `python -m pytest` из корня репозитория.

## Review Focus

1. **Кириллица и пробелы в путях** (папка данных, FASTA, исполняемые файлы, например `D:\Мои данные\проект 1\`) — всё работает. Тесты: Task 3 (`test_to_stored_roundtrip_cyrillic`), Task 9 (`test_run_in_cyrillic_dir_with_spaces`).
2. **Старый или испорченный конфиг** (нет части ключей, числа вместо строк, `"recent": null`, неизвестные ключи) — загружается с умолчаниями и приведением типов, окно открывается. Тест: Task 3 (`test_load_fills_missing_keys_and_coerces_types`).
3. **Папка приложения недоступна для записи / текущая папка = папка данных** — откат в `%APPDATA%\phymlGUI`, миграция не копирует файл сам в себя. Тесты: Task 3 (`test_detect_falls_back_to_appdata`, `test_migrate_legacy_noop_when_cwd_is_data_dir`).
4. **Отмена во время MUSCLE и посреди пакета** — дерево процессов текущего шага завершено, остальные файлы получают `cancelled`, исключений нет. Тест: Task 9 (`test_cancel_during_alignment_marks_rest_cancelled`).
5. **FASTA с UTF-8 BOM / CRLF и полностью одинаковыми ID** — BOM и CRLF допускаются, дубликаты сообщаются как коллизия. Тесты: Task 8 (`test_read_fasta_tolerates_bom_and_crlf`, `test_find_collisions_reports_exact_duplicates`).

---

## Файловая структура

| Файл | Действие | Ответственность |
|---|---|---|
| `pytest.ini`, `requirements-dev.txt` | создать | настройки pytest, маркеры, dev-зависимости |
| `tests/conftest.py` | создать | offscreen-Qt, изоляция данных, поиск бинарников, маркеры |
| `tests/data/*` | создать | маленькие фикстуры: деревья CytB, файлы статистики |
| `tests/unit/`, `tests/gui/`, `tests/e2e/` | создать | новые наборы тестов |
| `tests/*.py` (старые скрипты) | удалить | заменены pytest-наборами |
| `phyml_core/paths.py` | создать | `AppPaths` |
| `phyml_core/settings.py` | создать | схема конфига, load/save, миграция |
| `phyml_core/history.py` | создать | `HistoryStore`, формат записи |
| `phyml_core/presets.py` | создать | встроенные и пользовательские пресеты |
| `phyml_core/alignment.py` | создать | FASTA, выравненность, очистка ID, PHYLIP, сводка |
| `phyml_core/launchers.py` | создать | `Native`, `Mpi` |
| `phyml_core/engines/{__init__,base,phyml,iqtree}.py` | создать | интерфейс движка, PhyML, IQ-TREE, реестр |
| `phyml_core/runner.py` | создать | `PipelineRunner`, `FileResult`, `RunResult`, `kill_process_tree` |
| `phyml_core/report.py` | создать | сводка CSV/XLSX (сейчас в окне) |
| `phyml_core/pipeline.py` | удалить (Task 11) | заменён `runner.py` |
| `phyml_core/cli.py` | переписать (Task 12) | CLI поверх runner, без Qt |
| `phyml_ui/worker.py` | создать | `RunWorker(QThread)` |
| `phyml_ui/log_console.py`, `settings_dialog.py`, `status_bar.py`, `params_panel.py`, `nav_panel.py` | создать | части окна |
| `phyml_ui/main_window.py` | сократить до ≤ ~350 строк | сборка окна и связи |
| `phymlgui.py` | упростить | только точка входа, Qt импортируется лениво |
| `packaging/third_party.json`, `scripts/fetch_third_party.py` | создать | закреплённые IQ-TREE/MUSCLE для CI |
| `.github/workflows/tests.yml`, `README.md`, `.gitignore` | изменить | CI, документация, `/bin/` |

## Новые строки локализации

Добавляются в задачах, которые их используют (указано в скобках); тексты зафиксированы здесь.

| Ключ | en | ru |
|---|---|---|
| `settings_migrated` (T5) | `[System] Settings copied from {} to {}.` | `[Система] Настройки скопированы из {} в {}.` |
| `err_settings_broken` (T3) | `[ERROR] Settings file is damaged; defaults loaded, a copy is saved as {}.` | `[ОШИБКА] Файл настроек повреждён: загружены настройки по умолчанию, копия сохранена как {}.` |
| `err_settings_save` (T5) | `[ERROR] Cannot save settings: {}` | `[ОШИБКА] Не удалось сохранить настройки: {}` |
| `err_history_broken` (T4) | `[ERROR] Run history file is damaged and was ignored: {}` | `[ОШИБКА] Файл истории запусков повреждён и пропущен: {}` |
| `val_not_number` (T6) | `Parameter "{}" must be a positive number, got "{}".` | `Параметр «{}» должен быть положительным числом, получено «{}».` |
| `val_no_exe` (T6) | `{} executable not found: {}` | `Не найден исполняемый файл {}: {}` |
| `val_no_mpiexec` (T6) | `MPI is enabled but mpiexec was not found: {}` | `MPI включён, но mpiexec не найден: {}` |
| `err_engine_exit` (T9) | `[CRITICAL ERROR] {} exited with code {}.` | `[КРИТИЧЕСКАЯ ОШИБКА] {} завершил работу с кодом {}.` |
| `err_no_tree` (T9) | `[ERROR] {} finished but the tree file is missing: {}` | `[ОШИБКА] {} завершился, но файл дерева не найден: {}` |
| `err_id_collision` (T8) | `[ERROR] Sequence IDs collide after cleaning: {}` | `[ОШИБКА] После очистки совпали ID последовательностей: {}` |

---

### Task 1: pytest-инфраструктура и перенос проверок без бинарников

**Files:**
- Create: `pytest.ini`, `requirements-dev.txt`, `tests/conftest.py`
- Create: `tests/data/cytb_tree.nwk`, `tests/data/cytb_boot_trees.nwk`, `tests/data/x_phyml_stats.txt`, `tests/data/x.iqtree`
- Create: `tests/unit/test_i18n.py`, `tests/unit/test_stats_parsers.py`, `tests/unit/test_rf.py`, `tests/unit/test_pipeline_regressions.py`
- Create: `tests/gui/test_themes.py`, `tests/gui/test_log_console.py`, `tests/gui/test_tree_viewer.py`, `tests/gui/test_main_window_smoke.py`
- Delete: `tests/test_smoke.py`, `tests/test_tree_viewer.py`

**Interfaces:**
- Produces (`tests/conftest.py`): `ROOT: Path`, `DATA: Path` (= `ROOT/'tests'/'data'`); `find_binary(kind: str) -> str | None` для `kind in ('phyml', 'mpiexec', 'iqtree', 'muscle', 'raxml')`: сначала переменные `PHYMLGUI_PHYML` / `PHYMLGUI_MPIEXEC` / `PHYMLGUI_IQTREE` / `PHYMLGUI_MUSCLE` / `PHYMLGUI_RAXML`, затем `ROOT/'bin'/{phyml-mpi.exe, mpiexec.exe, iqtree2.exe, muscle.exe, raxml-ng.exe}`, затем нынешние локальные пути (для `raxml` локального пути нет — он понадобится в «Науке») (`ROOT/'phymlgui v1.1'/'phyml-mpi.exe'`, `C:\Program Files\Microsoft MPI\Bin\mpiexec.exe`, `ROOT/'tools'/'iqtree2'/'iqtree2.exe'`, `ROOT/'tools'/'muscle.exe'`); фикстура `binaries -> dict[str, str | None]`; фикстура `isolated_config(tmp_path, monkeypatch)` — подменяет `phyml_ui.main_window.CONFIG_FILE` и `HISTORY_FILE` путями в `tmp_path` (временная мера, Task 5 заменит её на `data_dir`); session-autouse фикстура `guard_user_files` — SHA256 `ROOT/phyml_config.json` и `ROOT/phyml_history.json` (если есть) до сессии и `assert` равенства после.
- Produces (`pytest.ini`): маркеры `needs_phyml`, `needs_mpi`, `needs_iqtree`, `needs_muscle`, `slow`; `pytest_runtest_setup` пропускает тест с маркером `needs_X`, если `find_binary(X)` вернул `None`, с причиной `"<kind> not found (set PHYMLGUI_<KIND>)"`.

- [ ] **Step 1: Создать `requirements-dev.txt` (`pytest>=8`, `pytest-qt>=4.4`) и `pytest.ini`**

```ini
[pytest]
testpaths = tests
qt_api = pyside6
markers =
    needs_phyml: requires a PhyML (MPI) executable
    needs_mpi: requires MS-MPI mpiexec
    needs_iqtree: requires an IQ-TREE executable
    needs_muscle: requires a MUSCLE executable
    slow: long-running end-to-end test
```

- [ ] **Step 2: Написать `tests/conftest.py`**

Первая строка модуля — `os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')`, до любого импорта Qt; `sys.path.insert(0, str(ROOT))`. Остальное — по блоку Interfaces.

- [ ] **Step 3: Положить фикстуры данных**

```bash
mkdir -p tests/data
cp testrun/t9_real_ncbi/cytb_mammals_aligned.phy_phyml_tree.txt tests/data/cytb_tree.nwk
cp testrun/t9_real_ncbi/cytb_mammals_aligned.phy_phyml_boot_trees.txt tests/data/cytb_boot_trees.nwk
```

`x_phyml_stats.txt` и `x.iqtree` — ровно те строки, что сейчас пишет `tests/test_smoke.py` в разделе 3.

- [ ] **Step 4: Перенести проверки один к одному**

Логика проверок не меняется; меняется только источник данных (просмотрщик читает `tests/data/`, а не `testrun/`, поэтому больше не пропускается).

| Было (PASS-строка) | Стало |
|---|---|
| smoke 1 imports and i18n | `unit/test_i18n.py::test_locales_have_same_keys` |
| smoke 2 themes | `gui/test_themes.py::test_resolve_qss_and_role_colors` |
| smoke 3 stats parsers | `unit/test_stats_parsers.py::test_parse_phyml_stats`, `::test_parse_iqtree_stats` |
| smoke 4 rf | `unit/test_rf.py::test_rf_identical_and_quartet_swap`, `::test_tree_splits_count` |
| smoke 5 log console | `gui/test_log_console.py::test_roles_and_plain_text` |
| smoke 6 main window | `gui/test_main_window_smoke.py::test_window_builds(isolated_config)` |
| smoke 7 empty fasta | `unit/test_pipeline_regressions.py::test_empty_fasta_fails_cleanly` |
| smoke 8 ufboot | `unit/test_pipeline_regressions.py::test_ufboot_replicates_raised_to_1000` |
| viewer 1b circle polytomy | `gui/test_tree_viewer.py::test_circle_polytomy_centered` |
| viewer 2 layouts | `::test_layouts_render` |
| viewer 2b grid | `::test_grid_drawn_and_toggleable` |
| viewer 2c theme colors | `::test_theme_colors` |
| viewer 3 options | `::test_threshold_grid_supports_options` |
| viewer 4 collapse | `::test_collapse_and_expand` |
| viewer 5 outgroup | `::test_outgroup_reroot_and_reset` |
| viewer 6 consensus | `::test_majority_consensus_from_boot_trees` (8 листьев, 20 деревьев из `cytb_boot_trees.nwk`) |

Тесты окна используют фикстуру `qtbot` из pytest-qt вместо ручного `QApplication([])`.

- [ ] **Step 5: Запустить и сверить**

Run: `python -m pytest tests/unit tests/gui -q`
Expected: `18 passed` (16 строк таблицы; строки smoke 3 и smoke 4 дают по два теста), без skip; `guard_user_files` не падает.

- [ ] **Step 6: Удалить `tests/test_smoke.py`, `tests/test_tree_viewer.py`; временно поменять шаг CI на `python -m pytest tests/unit tests/gui` с установкой `requirements-dev.txt`; коммит**

```bash
git add pytest.ini requirements-dev.txt tests .github/workflows/tests.yml
git commit -m "Move binary-free test checks to pytest with fixtures in tests/data"
```

---

### Task 2: перенос e2e- и GUI-проверок, которым нужны бинарники

**Files:**
- Create: `tests/e2e/datasets.py`, `tests/e2e/fetch_real_data.py` (перенос `tests/fetch_real_data.py` без изменения логики; кэш остаётся в `testrun/real`)
- Create: `tests/e2e/test_phyml_pipeline.py`, `tests/e2e/test_batch.py`, `tests/e2e/test_iqtree.py`, `tests/e2e/test_cpu_monitor.py`, `tests/gui/test_main_window.py`
- Delete: `tests/run_tests.py`, `tests/test_gui_logic.py`, `tests/test_batch.py`, `tests/test_iqtree.py`, `tests/fetch_real_data.py`
- Modify: `tests/README.md`

**Interfaces:**
- Consumes: фикстуры и маркеры Task 1.
- Produces (`tests/e2e/datasets.py`): `make_dataset() -> tuple[list[str], list[str], list[str]]` (имена, выровненные, невыровненные; `random.Random(42)`, как сейчас), `write_fasta(path, names, seqs) -> None`, фикстура `synthetic(tmp_path) -> dict[str, Path]` с ключами `'aligned'`, `'unaligned'`.

- [ ] **Step 1: Перенести проверки; рабочие папки — `tmp_path`, не `testrun/`**

| Было | Стало | Маркеры |
|---|---|---|
| run_tests t1–t4 | `e2e/test_phyml_pipeline.py::test_scenarios[t1..t4]` (параметризация) | `needs_phyml`, `needs_muscle`, `needs_mpi` для t2/t4 |
| run_tests t5 | `::test_serial_bootstrap_on_mpi_build_fails_gracefully` | `needs_phyml`, `needs_muscle` |
| run_tests t9 | `::test_real_cytb_tree` (пропуск, если данных нет и сеть недоступна) | `needs_phyml`, `needs_mpi`, `needs_muscle`, `slow` |
| gui_logic 2 defaults | `gui/test_main_window.py::test_defaults_match_detected_cores` — **сравнение с `detect_cores()`**, без 8/16 | — |
| gui_logic 3 mpi autodetect | `::test_mpi_binary_autodetect` | — |
| gui_logic 4 validation | `::test_serial_bootstrap_on_mpi_build_blocked` | — |
| gui_logic 5 cpu monitor | `e2e/test_cpu_monitor.py::test_cpu_samples_during_mpi_run` | `needs_phyml`, `needs_mpi`, `needs_muscle` |
| gui_logic 6 new UI | `gui/test_main_window.py::test_theme_tabs_presets_log_filter_recent` | — |
| batch 1 status bar | `gui/test_main_window.py::test_cpu_bar_expands` | — |
| batch 2 empty folder | `gui/test_main_window.py::test_empty_folder_blocked` | — |
| batch 3 two files | `e2e/test_batch.py::test_two_file_batch` | `needs_phyml`, `needs_mpi`, `needs_muscle` |
| batch 4 csv via GUI | `e2e/test_batch.py::test_gui_batch_writes_summary_csv` | то же |
| batch 5 stage3 | `e2e/test_batch.py::test_queue_history_open_folder` | то же |
| iqtree 1 engine | `e2e/test_iqtree.py::test_mfp_ufboot_run` | `needs_iqtree` |
| iqtree 1b 100 reps | `::test_100_replicates_raised_to_1000` | `needs_iqtree` |
| iqtree 2 GUI | `::test_gui_validation_and_run_with_xlsx` | `needs_iqtree` |
| iqtree 3 models | `::test_every_listed_model_accepted` | `needs_iqtree` |

Все GUI-тесты берут фикстуру `isolated_config`.

- [ ] **Step 2: Прогнать всё локально**

Run: `python -m pytest -q -rs`
Expected: `38 passed` (18 из Task 1 + 20 из таблицы: строка t1–t4 даёт четыре теста, остальные 16 строк — по одному), `0 skipped` на этой машине; `guard_user_files` проходит.

- [ ] **Step 3: Удалить старые скрипты, обновить `tests/README.md` (как запускать, переменные `PHYMLGUI_*`, маркеры); коммит**

```bash
git add tests
git commit -m "Move end-to-end and GUI suites to pytest with binary markers"
```

---

### Task 3: `AppPaths` и `settings`

**Files:**
- Create: `phyml_core/paths.py`, `phyml_core/settings.py`
- Test: `tests/unit/test_paths.py`, `tests/unit/test_settings.py`
- Modify: `locales.json` (`err_settings_broken`)

**Interfaces:**
- Produces (`phyml_core/paths.py`):
  - `CONFIG_NAME = 'phyml_config.json'`, `HISTORY_NAME = 'phyml_history.json'`
  - `default_app_dir() -> str` — `dirname(sys.executable)` при `sys.frozen`, иначе корень репозитория (родитель пакета `phyml_core`)
  - `@dataclass(frozen=True) class AppPaths: app_dir: str; data_dir: str`
    - свойства `bin_dir -> str` (`app_dir/bin`), `config_file -> str`, `history_file -> str`
    - `resource(name: str) -> str` — `sys._MEIPASS/name`, если существует, иначе `app_dir/name`
    - `to_stored(path: str) -> str` — относительный путь, если `path` внутри `app_dir`, иначе абсолютный; `''` → `''`
    - `from_stored(stored: str) -> str` — относительный → `join(app_dir, stored)`; абсолютный и `''` без изменений
    - `find_tool(stored: str, names: tuple[str, ...]) -> str` — `from_stored(stored)`, если файл существует; иначе первый существующий `bin_dir/name`; иначе `from_stored(stored)` (чтобы сообщение об ошибке показало настроенный путь)
    - `@classmethod detect(cls, env: Mapping[str, str] | None = None, is_writable: Callable[[str], bool] | None = None, app_dir: str | None = None) -> AppPaths` — порядок: `env['PHYMLGUI_DATA_DIR']` → `app_dir`, если `is_writable(app_dir)` → `env['APPDATA']/phymlGUI`; выбранная папка создаётся; `is_writable` по умолчанию — создание и удаление временного файла.
- Produces (`phyml_core/settings.py`):
  - `SCHEMA_VERSION = 2`
  - `DEFAULTS: dict` — `engine 'phyml'`, `iqtree_path ''`, `phyml_path ''`, `mpirun_path 'mpiexec'`, `muscle_path ''`, `datatype 'nt'`, `model 'HKY85'`, `support_method 'bootstrap'`, `bootstrap_replicates '100'`, `use_mpi False`, `mpi_np ''`, `freq 'default'`, `tstv 'e'`, `pinv '0.0'`, `classes '4'`, `gamma 'e'`, `search 'NNI'`, `optimize 'tlr'`, `parsimony False`, `show_tree True`, `theme 'system'`, `accent 'green'`, `recent []`, `presets {}`, `window {}`, `schema_version 2`
  - `PATH_KEYS = ('phyml_path', 'iqtree_path', 'muscle_path', 'mpirun_path')`
  - `load(path: str, on_error: Callable[[str], None] | None = None) -> dict` — нет файла → копия `DEFAULTS`; битый JSON → копия `DEFAULTS`, исходный текст сохраняется в `path + '.broken'`, `on_error(_t('err_settings_broken').format(path + '.broken'))`; иначе умолчания ← файл с приведением типов к типу умолчания (`str` ← число через `str()`; `bool` ← только `bool`, иначе умолчание; `list`/`dict` ← только того же типа, иначе умолчание); неизвестные ключи сохраняются; `schema_version` = 2
  - `save(path: str, cfg: dict) -> None` — JSON `indent=4, ensure_ascii=False`, UTF-8, временный файл в той же папке + `os.replace`; `OSError` пробрасывается
  - `to_disk(cfg: dict, paths: AppPaths) -> dict` / `from_disk(cfg: dict, paths: AppPaths) -> dict` — `to_stored`/`from_stored` для `PATH_KEYS` и элементов `recent`
  - `migrate_legacy(paths: AppPaths, cwd: str) -> list[str]` — если `realpath(cwd) != realpath(data_dir)`, в `data_dir` нет `CONFIG_NAME`, а в `cwd` есть `CONFIG_NAME` и/или `HISTORY_NAME` — копирует найденные (`shutil.copy2`), возвращает их имена; иначе `[]`

- [ ] **Step 1: Написать падающие тесты**

```python
# tests/unit/test_paths.py
def test_detect_uses_env_override(tmp_path):
    p = AppPaths.detect(env={'PHYMLGUI_DATA_DIR': str(tmp_path / 'd')}, app_dir=str(tmp_path))
    assert p.data_dir == str(tmp_path / 'd') and os.path.isdir(p.data_dir)

def test_detect_prefers_writable_app_dir(tmp_path):
    p = AppPaths.detect(env={}, is_writable=lambda d: True, app_dir=str(tmp_path))
    assert p.data_dir == str(tmp_path)

def test_detect_falls_back_to_appdata(tmp_path):
    p = AppPaths.detect(env={'APPDATA': str(tmp_path / 'ad')}, is_writable=lambda d: False,
                        app_dir=str(tmp_path / 'app'))
    assert p.data_dir == str(tmp_path / 'ad' / 'phymlGUI') and os.path.isdir(p.data_dir)

def test_to_stored_roundtrip_cyrillic(tmp_path):
    app = tmp_path / 'Мои программы' / 'phymlGUI'
    p = AppPaths(app_dir=str(app), data_dir=str(app))
    inside = str(app / 'bin' / 'muscle.exe')
    assert p.to_stored(inside) == os.path.join('bin', 'muscle.exe')
    assert p.from_stored(p.to_stored(inside)) == inside
    outside = str(tmp_path / 'данные' / 'a.fasta')
    assert p.to_stored(outside) == outside and p.to_stored('') == ''

def test_find_tool_prefers_stored_then_bin(tmp_path)
    # stored существует → он; stored не существует, bin/muscle.exe есть → bin; ничего нет → from_stored(stored)

def test_resource_prefers_meipass(tmp_path, monkeypatch)
    # sys._MEIPASS с locales.json → путь внутри _MEIPASS; без _MEIPASS → app_dir/locales.json
```

```python
# tests/unit/test_settings.py
def test_load_missing_file_returns_defaults(tmp_path)          # == DEFAULTS, не тот же объект
def test_load_fills_missing_keys_and_coerces_types(tmp_path):
    path = tmp_path / 'c.json'
    path.write_text(json.dumps({'mpi_np': 8, 'recent': None, 'use_mpi': 'yes', 'custom_key': 1}), 'utf-8')
    cfg = settings.load(str(path))
    assert cfg['mpi_np'] == '8' and cfg['recent'] == [] and cfg['use_mpi'] is False
    assert cfg['custom_key'] == 1 and cfg['model'] == 'HKY85' and cfg['schema_version'] == 2
def test_load_broken_json_keeps_copy_and_reports(tmp_path)     # '{oops' → DEFAULTS, on_error вызван 1 раз, текст содержит '.broken', файл .broken == '{oops'
def test_save_is_atomic_and_roundtrips(tmp_path)               # save → load равны; в папке только c.json
def test_save_raises_oserror_for_directory_target(tmp_path)    # path — папка → pytest.raises(OSError)
def test_to_disk_from_disk_roundtrip(tmp_path)                 # phyml_path внутри app_dir → относительный на диске, абсолютный после from_disk
def test_migrate_legacy_copies_once(tmp_path)                  # оба файла скопированы, оригиналы на месте; второй вызов → []
def test_migrate_legacy_noop_when_cwd_is_data_dir(tmp_path)    # → [] и файл не тронут
```

- [ ] **Step 2: Run `python -m pytest tests/unit/test_paths.py tests/unit/test_settings.py -q`** — Expected: FAIL (`ModuleNotFoundError: phyml_core.paths`)
- [ ] **Step 3: Реализовать `phyml_core/paths.py` и `phyml_core/settings.py` по Interfaces; добавить ключ `err_settings_broken`**
- [ ] **Step 4: Run тот же набор и `python -m pytest -q`** — Expected: PASS, остальные тесты не изменились
- [ ] **Step 5: Коммит** — `git commit -m "Add AppPaths and settings with atomic save, type coercion and legacy migration"`

---

### Task 4: `HistoryStore` и пресеты

**Files:**
- Create: `phyml_core/history.py`, `phyml_core/presets.py`
- Test: `tests/unit/test_history.py`, `tests/unit/test_presets.py`
- Modify: `locales.json` (`err_history_broken`)

**Interfaces:**
- Produces (`phyml_core/history.py`):
  - `class HistoryStore: __init__(self, path: str, limit: int = 200)`; `load(self, on_error=None) -> list[dict]` (нет файла → `[]`; битый → `[]` и `on_error(_t('err_history_broken').format(path))`); `append(self, record: dict) -> None` (новые сверху, обрезка до `limit`, атомарная запись как в `settings.save`, `OSError` пробрасывается); `get(self, index: int) -> dict | None`
  - `new_record(*, inputs: list[str], engine: str, params: dict, files: list[dict], duration_s: float, ts: datetime | None = None) -> dict` — ключи `ts` (`'%Y-%m-%d %H:%M'`), `inputs`, `engine`, `params`, `files` (элементы `{'file', 'status', 'tree', 'stats', 'error'}`), `ok` (число `status == 'ok'`), `n` (`len(files)`), `duration_s`
  - `display_input(rec: dict) -> str` — новая запись: basename `inputs[0]` (+ `'/'` для папки; при нескольких файлах — basename их общей папки + `'/'`); старая: `rec.get('input', '')`
  - `best_tree(rec: dict) -> str` — новая: дерево последнего файла со статусом `ok`; старая: `rec.get('tree', '')`
- Produces (`phyml_core/presets.py`):
  - `PRESET_KEYS` — нынешние 12 ключей `_PRESET_KEYS` + `'engine'`
  - `BUILTIN: dict[str, dict]` — `'preset_builtin_screen'` и `'preset_builtin_pub'` с нынешними значениями `_BUILTIN_PRESETS` + `'engine': 'phyml'`
  - `extract(params: dict) -> dict` — только `PRESET_KEYS`
  - `apply(preset: dict, params: dict) -> dict` — новый словарь: `params`, обновлённый ключами пресета из `PRESET_KEYS` (движок тоже)

- [ ] **Step 1: Написать падающие тесты** — `test_append_keeps_newest_first_and_limit` (205 записей → 200, `load()[0]` — последняя), `test_load_corrupt_file_reports_and_returns_empty`, `test_new_record_counts_ok_and_n`, `test_old_record_display_and_tree` (`{'input': 'a.fasta', 'tree': 'x.txt', 'ok': 1, 'n': 1}` → `'a.fasta'`, `'x.txt'`), `test_new_record_best_tree_is_last_ok`, `test_extract_excludes_paths_and_display`, `test_apply_switches_engine_and_keeps_paths`, `test_builtin_screening_uses_alrt` (`BUILTIN['preset_builtin_screen']['support_method'] == '-4'`)
- [ ] **Step 2: Run `python -m pytest tests/unit/test_history.py tests/unit/test_presets.py -q`** — Expected: FAIL (модулей нет)
- [ ] **Step 3: Реализовать оба модуля; добавить ключ `err_history_broken`**
- [ ] **Step 4: Run набор и `python -m pytest -q`** — Expected: PASS
- [ ] **Step 5: Коммит** — `git commit -m "Add HistoryStore with full run params and engine-aware presets"`

---

### Task 5: окно на `AppPaths` / `settings` / `HistoryStore` / `presets`

**Files:**
- Modify: `phyml_ui/main_window.py` (удалить `CONFIG_FILE`, `HISTORY_FILE`, `_BUILTIN_PRESETS`, `_PRESET_KEYS`, `_load_history`; `load_config`/`auto_save`/`_append_history`/`_refresh_history`/`_open_history_entry`/пресеты — через новые модули)
- Modify: `phymlgui.py` (убрать реэкспорт `CONFIG_FILE`)
- Modify: `tests/conftest.py` (фикстура `data_dir` вместо `isolated_config`), все GUI/e2e-тесты, которые брали `isolated_config`; `e2e/test_batch.py::test_queue_history_open_folder` читает историю через `HistoryStore(w.paths.history_file)` вместо `HISTORY_FILE`
- Modify: `locales.json` (`settings_migrated`, `err_settings_save`)
- Test: `tests/gui/test_main_window_storage.py`

**Interfaces:**
- Consumes: Task 3, Task 4.
- Produces: `PhyMLApp.__init__(self, paths: AppPaths | None = None)` — `None` → `AppPaths.detect()`; атрибут `self.paths`. Перед загрузкой конфига окно вызывает `settings.migrate_legacy(self.paths, os.getcwd())` и пишет `settings_migrated` в журнал для каждого скопированного файла. Ошибки `settings.save` / `HistoryStore.append` → строка `err_settings_save` в журнал. Пути инструментов и `recent` пишутся через `settings.to_disk`, читаются через `settings.from_disk`.
- Produces (`tests/conftest.py`): фикстура `data_dir(tmp_path, monkeypatch) -> Path` — `monkeypatch.setenv('PHYMLGUI_DATA_DIR', ...)` и `monkeypatch.chdir(tmp_path / 'cwd')` (пустая папка), чтобы миграция не находила настоящий конфиг в корне репозитория.

- [ ] **Step 1: Написать падающие тесты** — `test_config_saved_in_data_dir` (сменить модель → `data_dir/phyml_config.json` содержит её; в `cwd` файла нет), `test_legacy_config_migrated_on_first_start` (в `cwd` старый конфиг с `"model": "GTR"` → окно показывает `GTR`, журнал содержит текст `settings_migrated`), `test_history_written_to_data_dir` (`w._append_history(1, 1, 'x.txt')` → `HistoryStore(paths.history_file).load()[0]['ok'] == 1`), `test_tool_path_inside_app_dir_saved_relative` (`AppPaths(app_dir=tmp/'app', data_dir=tmp/'d')`, путь PhyML `app/bin/phyml-mpi.exe` → в JSON `os.path.join('bin', 'phyml-mpi.exe')`)
- [ ] **Step 2: Run `python -m pytest tests/gui/test_main_window_storage.py -q`** — Expected: FAIL
- [ ] **Step 3: Перевести окно; заменить `isolated_config` на `data_dir` во всех тестах и удалить старую фикстуру**
- [ ] **Step 4: Run `python -m pytest -q -rs`** — Expected: всё PASS, `guard_user_files` проходит
- [ ] **Step 5: Ручная проверка** — `python phymlgui.py` из корня: настройки на месте (миграция в журнале не появляется, так как `cwd == app_dir == data_dir`); закрыть окно
- [ ] **Step 6: Коммит** — `git commit -m "Store settings and history in the data dir via AppPaths, migrate legacy files once"`

---

### Task 6: способы запуска, интерфейс движка и PhyML

**Files:**
- Create: `phyml_core/launchers.py`, `phyml_core/engines/__init__.py`, `phyml_core/engines/base.py`, `phyml_core/engines/phyml.py`
- Modify: `phyml_core/pipeline.py` (`parse_stats` → импорт `parse_phyml_stats` из `engines.phyml`), `locales.json` (`val_not_number`, `val_no_exe`, `val_no_mpiexec`)
- Test: `tests/unit/test_launchers.py`, `tests/unit/test_engine_phyml.py`; `tests/unit/test_stats_parsers.py` импортирует новые функции

**Interfaces:**
- Produces (`phyml_core/launchers.py`): `class Native: wrap(self, argv: list[str]) -> list[str]`; `@dataclass(frozen=True) class Mpi: mpiexec: str; np: int; wrap(self, argv) -> [mpiexec, '-np', str(np), *argv]`
- Produces (`phyml_core/engines/base.py`): `Issue`, `EngineOutputs` — как в спецификации, разделы 3; `format_issue(issue: Issue) -> str` = `_t(issue.key).format(*issue.args)`; `positive_number(value: str) -> bool` (целое или дробное > 0); `class Engine(ABC)` с атрибутами `key: str`, `name: str` (для сообщений: `'PhyML'`, `'IQ-TREE'`), `label_key: str` и методами спецификации; сигнатура проверки — `validate(self, params: dict, paths: AppPaths) -> list[Issue]`
- Produces (`phyml_core/engines/phyml.py`): `parse_phyml_stats(path: str) -> dict` (бывшая `pipeline.parse_stats`), `class PhyML(Engine)`: `key='phyml'`, `name='PhyML'`, `label_key='engine_phyml'`
- Produces (`phyml_core/engines/__init__.py`): `ENGINES: dict[str, Engine] = {'phyml': PhyML()}` (IQ-TREE добавит Task 7)

- [ ] **Step 1: Написать падающие тесты**

```python
P = {'datatype': 'nt', 'model': 'HKY85', 'support_method': 'bootstrap', 'bootstrap_replicates': '100',
     'freq': 'default', 'tstv': 'e', 'pinv': '0.0', 'classes': '4', 'gamma': 'e',
     'search': 'NNI', 'optimize': 'tlr', 'parsimony': False}

def test_command_matches_current_argv():
    assert PhyML().command('C:/b/phyml.exe', 'D:/d/a.phy', P) == [
        'C:/b/phyml.exe', '-i', 'D:/d/a.phy', '-d', 'nt', '-m', 'HKY85', '-b', '100',
        '-t', 'e', '-v', '0.0', '-c', '4', '-a', 'e', '-s', 'NNI', '-o', 'tlr']

def test_command_alrt_freq_parsimony_and_empty_values():
    argv = PhyML().command('x', 'a.phy', dict(P, support_method='-4', freq='m', parsimony=True, tstv=''))
    assert argv[argv.index('-b') + 1] == '-4' and argv[argv.index('-f') + 1] == 'm'
    assert '-t' not in argv and argv[-1] == '-p'

def test_command_omits_freq_when_missing():           # dict без 'freq' → '-f' отсутствует (сейчас уходит None)
def test_launcher_mpi_and_native():
    l = PhyML().launcher(dict(P, use_mpi=True, mpirun_path='C:/MPI/mpiexec.exe', mpi_np='2'))
    assert l.wrap(['x']) == ['C:/MPI/mpiexec.exe', '-np', '2', 'x']
    assert PhyML().launcher(dict(P, use_mpi=False)).wrap(['x']) == ['x']
def test_outputs():                                    # tree/stats/boot_trees = 'D:/d/a.phy' + '_phyml_tree.txt' / '_phyml_stats.txt' / '_phyml_boot_trees.txt', log None
def test_validate_ok(tmp_path)                         # exe существует, use_mpi False, support '-4' → []
def test_validate_missing_exe(tmp_path)                # → [Issue('error', 'val_no_exe', ...)]
def test_validate_serial_bootstrap_on_mpi_build(tmp_path)   # exe 'phyml-mpi.exe', use_mpi False, bootstrap → key 'mpi_boot_msg'
def test_validate_numbers(tmp_path)                    # bootstrap_replicates 'abc', classes '0', pinv 'x' → три 'val_not_number'; pinv 'e', gamma 'e' допустимы
def test_validate_mpiexec_missing(tmp_path)            # use_mpi True, mpirun_path не существует и не находится shutil.which → 'val_no_mpiexec'
def test_executable_falls_back_to_bin(tmp_path)        # phyml_path '' и app/bin/phyml-mpi.exe есть → этот путь
def test_models_unchanged()                            # models('nt') и models('aa') == нынешние списки update_models
```

- [ ] **Step 2: Run `python -m pytest tests/unit/test_launchers.py tests/unit/test_engine_phyml.py -q`** — Expected: FAIL (модулей нет)
- [ ] **Step 3: Реализовать модули; `pipeline.py` импортирует `parse_phyml_stats`; ключи локализации**
- [ ] **Step 4: Run набор и `python -m pytest -q`** — Expected: PASS
- [ ] **Step 5: Коммит** — `git commit -m "Add launchers, the Engine interface and the PhyML engine with argv tests"`

---

### Task 7: движок IQ-TREE, реестр и модели из движков

**Files:**
- Create: `phyml_core/engines/iqtree.py`
- Modify: `phyml_core/engines/__init__.py` (`ENGINES = {'phyml': PhyML(), 'iqtree': IqTree()}`), `phyml_core/pipeline.py` (импорт `parse_iqtree_stats` и `ufboot_replicates` из `engines.iqtree`), `phyml_ui/main_window.py` (`update_models` → `ENGINES[self.engine_setting].models(datatype)`)
- Test: `tests/unit/test_engine_iqtree.py`; `tests/unit/test_pipeline_regressions.py::test_ufboot_replicates_raised_to_1000` переносится сюда как `test_normalize_raises_ufboot`; `tests/e2e/test_iqtree.py::test_every_listed_model_accepted` берёт список из `ENGINES['iqtree'].models(dt)`

**Interfaces:**
- Produces: `parse_iqtree_stats(path: str) -> dict`, `UFBOOT_MIN_REPLICATES = 1000`, `ufboot_replicates(value) -> str` (перенос без изменений), `class IqTree(Engine)`: `key='iqtree'`, `name='IQ-TREE'`, `label_key='engine_iqtree'`; префикс вывода — `phylip.rsplit('.', 1)[0] + '_iqtree'`

- [ ] **Step 1: Написать падающие тесты**

```python
Q = {'model': 'MFP', 'mpi_np': '2', 'support_method': 'bootstrap', 'bootstrap_replicates': '1000'}

def test_command_ufboot():
    assert IqTree().command('C:/b/iqtree2.exe', 'D:/d/a.phy', Q) == [
        'C:/b/iqtree2.exe', '-s', 'D:/d/a.phy', '--prefix', 'D:/d/a_iqtree', '-redo',
        '-m', 'MFP', '-T', '2', '-B', '1000']
def test_command_alrt_and_none():   # '-4' → хвост ['--alrt', '1000']; '0' → после ['-T', '2'] ничего
def test_normalize_raises_ufboot():
    p, notes = IqTree().normalize(dict(Q, bootstrap_replicates='100'))
    assert p['bootstrap_replicates'] == '1000' and notes == [Issue('warning', 'iqtree_ufboot_min', ('1000', '100'))]
    assert IqTree().normalize(dict(Q, bootstrap_replicates='5000')) == (dict(Q, bootstrap_replicates='5000'), [])
def test_validate(tmp_path)          # нет exe → 'val_no_exe'; mpi_np 'x' → 'val_not_number'; всё верно → []
def test_outputs()                   # tree 'D:/d/a_iqtree.treefile', stats '.iqtree', boot_trees None, log '.log'
def test_launcher_is_native()
def test_models_list_has_hky_not_hky2()   # 'HKY+F+G4' in models('nt'), 'HKY2+F+G4' not in
def test_registry_keys()             # list(ENGINES) == ['phyml', 'iqtree']
```

- [ ] **Step 2: Run `python -m pytest tests/unit/test_engine_iqtree.py -q`** — Expected: FAIL
- [ ] **Step 3: Реализовать; окно берёт модели из реестра; `pipeline.py` импортирует перенесённые функции**
- [ ] **Step 4: Run `python -m pytest -q -rs`** — Expected: PASS (включая `e2e/test_iqtree.py` локально)
- [ ] **Step 5: Коммит** — `git commit -m "Add the IQ-TREE engine and an engine registry; the model list comes from engines"`

---

### Task 8: `alignment.py`

**Files:**
- Create: `phyml_core/alignment.py`
- Modify: `phyml_ui/main_window.py` (`_update_fasta_info` → `alignment.summarize`), `locales.json` (`err_id_collision`)
- Test: `tests/unit/test_alignment.py`

**Interfaces:**
- Produces:
  - `class AlignmentError(ValueError)`
  - `read_fasta(path: str) -> list[SeqRecord]` — открывает с `encoding='utf-8-sig'` (BOM), CRLF допустим; пустой или без записей → `AlignmentError(_t('err_empty'))`
  - `is_aligned(records: list[SeqRecord]) -> bool`
  - `clean_id(raw: str) -> str` — `re.sub(r'[.|:;(),\s]', '_', raw)` (как сейчас)
  - `find_collisions(ids: list[str]) -> dict[str, list[str]]` — очищенный ID → исходные, только где исходных больше одного (включая полные дубликаты)
  - `write_phylip(records: list[SeqRecord], out_path: str) -> None` — `.` → `-` в последовательностях, ID через `clean_id`, формат `phylip-relaxed`; при коллизиях — `AlignmentError(_t('err_id_collision').format('; '.join(f"{', '.join(orig)} → {clean}" ...)))`
  - `summarize(path: str) -> dict` — `{'n', 'min_len', 'max_len', 'gap_pct'}` (как в нынешнем `_update_fasta_info`)
  - `aligned_path(fasta: str) -> str` (`rsplit('.', 1)[0] + '_aligned.fasta'`), `phylip_path(fasta: str) -> str` (`rsplit('.', 1)[0] + '.phy'`)

- [ ] **Step 1: Написать падающие тесты** — `test_read_fasta_empty_raises`, `test_read_fasta_tolerates_bom_and_crlf` (байты `b'\xef\xbb\xbf>A\r\nACGT\r\n>B\r\nACGA\r\n'` → ID `['A', 'B']`, `str(seq) == 'ACGT'`), `test_is_aligned`, `test_clean_id` (`'Homo sapiens|x:1'` → `'Homo_sapiens_x_1'`), `test_find_collisions` (`['A.1', 'A_1', 'B']` → `{'A_1': ['A.1', 'A_1']}`), `test_find_collisions_reports_exact_duplicates` (`['X', 'X']` → `{'X': ['X', 'X']}`), `test_write_phylip_cleans_ids_and_dots` (чтение через `AlignIO` возвращает очищенные ID и `-` вместо `.`), `test_write_phylip_raises_on_collision` (текст содержит `A.1` и `A_1`), `test_summarize`, `test_path_helpers`
- [ ] **Step 2: Run `python -m pytest tests/unit/test_alignment.py -q`** — Expected: FAIL
- [ ] **Step 3: Реализовать; окно использует `summarize`; ключ `err_id_collision`**
- [ ] **Step 4: Run `python -m pytest -q`** — Expected: PASS
- [ ] **Step 5: Коммит** — `git commit -m "Add alignment helpers with BOM-tolerant reading and ID collision detection"`

---

### Task 9: `PipelineRunner`

**Files:**
- Create: `phyml_core/runner.py`
- Test: `tests/unit/fakes.py`, `tests/unit/test_runner.py`; `test_pipeline_regressions.py::test_empty_fasta_fails_cleanly` переносится сюда
- Modify: `locales.json` (`err_engine_exit`, `err_no_tree`)

**Interfaces:**
- Consumes: `AppPaths` (T3), `Engine`/`Issue`/`format_issue`/`ENGINES` (T6–T7), `alignment` (T8).
- Produces:
  - `LEVELS = ('error', 'success', 'system', 'out')`; статусы файла для `on_status`: `'pending'`, `'running'`, `'ok'`, `'fail'`, `'cancelled'`
  - `FileResult`, `RunResult` — как в спецификации, раздел 5; `RunResult.ok_count -> int`, `RunResult.success -> bool` (файлы есть, все `ok`, не `cancelled`)
  - `kill_process_tree(pid: int) -> None` — `psutil.Process(pid).children(recursive=True)` + сам процесс: `terminate`, ожидание 3 с, затем `kill`; без `psutil` — `os.kill(pid, signal.SIGTERM)`; исчезнувшие процессы игнорируются
  - `class PipelineRunner: __init__(self, params: dict, files: list[str], paths: AppPaths, on_log=None, on_status=None, engines: Mapping[str, Engine] | None = None)`; `run(self) -> RunResult`; `cancel(self) -> None`; свойство `active_pid -> int | None`
- Поведение (порядок шагов и гарантии — спецификация, раздел 5): MUSCLE — `paths.find_tool(params['muscle_path'], ('muscle.exe',))`, аргументы v5 `['-align', in, '-output', out]`, при ненулевом коде v3 `['-in', in, '-out', out]`; вывод процессов — уровень `'out'`; предупреждения `validate`/`normalize` — `'system'`; сообщения пакета — нынешние ключи `batch_found`, `batch_file_header`, `batch_summary`; после отмены оставшиеся файлы получают `cancelled`.
- Produces (`tests/unit/fakes.py`): `FakeEngine(Engine)` с `key='fake'`, `name='Fake'`; `command` возвращает `[sys.executable, FAKE_TOOL, mode, phylip]`, где `mode` берётся из `params['fake_mode']`: `'ok'` (пишет `outputs.tree` и `outputs.stats`), `'exit3'` (код 3), `'notree'` (код 0, без дерева), `'hang'` (запускает дочерний `python -c "import time; time.sleep(60)"` и сам спит), `'raise'` (`command` бросает `RuntimeError('boom')`); `fake_muscle(tmp_path, mode) -> str` — `.cmd`-обёртка над Python-скриптом: `'copy'` (копирует вход в выход) или `'hang'`.

- [ ] **Step 1: Написать падающие тесты**

```python
def test_ok_run_returns_tree_and_stats(tmp_path)              # статус ok, tree существует, on_status: pending → running → ok
def test_empty_fasta_fails_cleanly(tmp_path)                   # status 'fail', error содержит текст err_empty, run() не бросает
def test_engine_exit_code_reported(tmp_path)                   # 'exit3' → fail, error == _t('err_engine_exit').format('Fake', 3)
def test_missing_tree_reported(tmp_path)                       # 'notree' → fail, текст err_no_tree
def test_engine_exception_never_escapes(tmp_path)              # 'raise' → fail, 'boom' в error, второй файл пакета обработан
def test_validate_error_stops_file_and_warning_is_logged(tmp_path)
def test_id_collision_fails_with_listing(tmp_path)             # ID 'A.1' и 'A_1' → fail, оба в error
def test_unaligned_input_runs_muscle(tmp_path)                 # fake_muscle 'copy', длины разные → *_aligned.fasta создан
def test_cancel_kills_process_tree(tmp_path):
    # 'hang': дождаться on_status 'running', запомнить active_pid и pid дочернего (psutil),
    # cancel() из другого потока → run() вернулся < 10 с, status 'cancelled', оба pid не живы
def test_cancel_during_alignment_marks_rest_cancelled(tmp_path)   # fake_muscle 'hang', 2 файла → оба 'cancelled'
def test_run_in_cyrillic_dir_with_spaces(tmp_path)             # папка tmp_path / 'Мои данные' / 'проект 1' → ok
def test_log_levels_are_from_levels(tmp_path)                  # все уровни в on_log ∈ LEVELS
```

- [ ] **Step 2: Run `python -m pytest tests/unit/test_runner.py -q`** — Expected: FAIL (`ModuleNotFoundError: phyml_core.runner`)
- [ ] **Step 3: Реализовать `runner.py` и фейки; ключи локализации**
- [ ] **Step 4: Run `python -m pytest tests/unit/test_runner.py -q` три раза подряд, затем `python -m pytest -q`** — Expected: PASS каждый раз (тесты отмены не должны «мигать»)
- [ ] **Step 5: Коммит** — `git commit -m "Add a Qt-free PipelineRunner that never raises and cancels whole process trees"`

---

### Task 10: `report.py` — сводка CSV/XLSX

**Files:**
- Create: `phyml_core/report.py`
- Test: `tests/unit/test_report.py`

**Interfaces:**
- Consumes: `FileResult` (T9).
- Produces: `SUMMARY_COLUMNS = ('file', 'status', 'model', 'taxa', 'lnL', 'gamma', 'tstv', 'time', 'tree')`; `summary_rows(files: list[FileResult]) -> list[dict]` (`status` → `'OK'`/`'FAIL'`/`'CANCELLED'`, `file` — basename, статистика из `stats`); `write_summary(rows: list[dict], out_dir: str) -> list[str]` — `phymlgui_summary.csv` (`;`, `utf-8-sig`, заголовок — ключи колонок, как сейчас) и, если установлен openpyxl, `phymlgui_summary.xlsx` (лист `Summary`, заголовки `_t('sum_col_' + c)` без `tree`, ширины как сейчас); возвращает пути записанных файлов; `OSError` пробрасывается.

- [ ] **Step 1: Написать падающие тесты** — `test_rows_from_results`, `test_csv_matches_current_format` (первая строка `file;status;model;taxa;lnL;gamma;tstv;time;tree`, кодировка с BOM), `test_xlsx_written_when_openpyxl_available` (`pytest.importorskip('openpyxl')`, `max_row == len(rows) + 1`)
- [ ] **Step 2: Run `python -m pytest tests/unit/test_report.py -q`** — Expected: FAIL
- [ ] **Step 3: Реализовать**
- [ ] **Step 4: Run** — Expected: PASS
- [ ] **Step 5: Коммит** — `git commit -m "Move the CSV/XLSX run summary into phyml_core.report"`

---

### Task 11: `RunWorker`, окно на runner, журнал по уровням, проверка до запуска

**Files:**
- Create: `phyml_ui/worker.py`
- Modify: `phyml_ui/main_window.py` (`start_pipeline`, `cancel_pipeline`, `pipeline_finished`, `update_cpu_status`, `LogConsole`, удаление `_save_summary_csv`)
- Delete: `phyml_core/pipeline.py`; из `phymlgui.py` — реэкспорт `PipelineWorker`
- Modify: тесты, использовавшие `PipelineWorker` или `LogConsole.append(text)`
- Test: `tests/gui/test_worker.py`, дополнения в `tests/gui/test_main_window.py`

**Interfaces:**
- Consumes: `PipelineRunner`, `RunResult`, `ENGINES`, `format_issue`, `report.summary_rows/write_summary`, `history.new_record`.
- Produces (`phyml_ui/worker.py`): `class RunWorker(QThread)` — сигналы `log = Signal(str, str)`, `status = Signal(str, str)`, `done = Signal(object)` (`RunResult`); `__init__(self, runner: PipelineRunner)`; `run()` эмитит `done(runner.run())`; `cancel()`; свойство `active_pid`
- Produces (`LogConsole`): `append(self, level: str, text: str) -> None` (уровень обязателен, `_classify` удаляется); остальной API без изменений
- Поведение окна: `start_pipeline` вызывает `ENGINES[engine].validate(params, self.paths)`; есть `error` → `QMessageBox.warning(self, _t('err_box_title'), '\n'.join(format_issue(i) for i in errors))` и выход; нынешние проверки «нет IQ-TREE» и «бутстреп на MPI-сборке» удаляются (их делает `validate`). `pipeline_finished(result: RunResult)` заполняет статистику и сводку из `result.files`, пишет отчёт, историю (`new_record`), включает «Повторить неудавшиеся» для `fail`, грузит дерево при `result.success` и включённом «Показывать дерево». CPU-монитор берёт `self.worker.active_pid`.

- [ ] **Step 1: Написать падающие тесты** — `gui/test_worker.py::test_worker_emits_log_status_done(qtbot, tmp_path)` (FakeEngine `'ok'` через `engines=`: `qtbot.waitSignal(w.done, timeout=10000)`, `result.success`), `gui/test_main_window.py::test_window_recovers_after_engine_exception(qtbot, data_dir)` (окно с реестром, где FakeEngine `'raise'`: после `done` кнопка Run снова доступна, журнал содержит `boom`), `::test_prerun_validation_lists_all_errors(qtbot, data_dir)` (два ошибочных параметра → в тексте предупреждения обе строки), `gui/test_log_console.py::test_levels_drive_colors_and_filter` (`append('error', 'x')` виден в фильтре «ошибки», `append('out', 'y')` — нет)
- [ ] **Step 2: Run эти тесты** — Expected: FAIL (`ModuleNotFoundError: phyml_ui.worker`)
- [ ] **Step 3: Реализовать `RunWorker`, перевести окно, удалить `pipeline.py`, обновить затронутые тесты (e2e используют `PipelineRunner` напрямую)**
- [ ] **Step 4: Run `python -m pytest -q -rs`** — Expected: PASS, включая e2e локально
- [ ] **Step 5: Ручная проверка** — одиночный прогон, пакет из двух файлов, отмена MPI-прогона (в диспетчере задач не остаётся `phyml-mpi.exe`), смена движка
- [ ] **Step 6: Коммит** — `git commit -m "Drive the window through PipelineRunner and RunWorker; log levels come from the core"`

---

### Task 12: CLI без Qt и ленивая точка входа

**Files:**
- Modify: `phyml_core/cli.py`, `phymlgui.py` (импорт PySide6 и `phyml_ui` — только в ветке GUI; реэкспорты удаляются)
- Test: `tests/unit/test_cli.py`, `tests/unit/test_core_has_no_qt.py`

**Interfaces:**
- Consumes: `AppPaths.detect`, `settings.load`, `PipelineRunner`.
- Produces: `phyml_core.cli.main(argv: list[str] | None = None) -> int` — аргументы `--file`, `--batch`, `--config` (как сейчас); параметры = `settings.from_disk(settings.load(paths.config_file), paths)`, поверх — JSON из `--config`, если задан; пакет — те же правила отбора файлов, что в окне (`.fasta/.fas/.fa`, без `*_aligned.fasta`); лог в stdout строками `text`; коды: 0 — `result.success`, 1 — есть `fail`/`cancelled`, 2 — нет `--file`/`--batch`, пустая папка или несуществующий путь.

- [ ] **Step 1: Написать падающие тесты**

```python
BLOCK_QT = "import sys; sys.modules['PySide6'] = None; "

def test_core_has_no_qt():
    code = BLOCK_QT + ("import pkgutil, importlib, phyml_core; "
                       "[importlib.import_module(m.name) for m in "
                       "pkgutil.walk_packages(phyml_core.__path__, 'phyml_core.')]")
    r = subprocess.run([sys.executable, '-c', code], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr

def test_cli_without_qt_fails_cleanly_on_empty_fasta(tmp_path):   # env PHYMLGUI_DATA_DIR=tmp; rc == 1; 'ImportError' not in stderr
def test_entry_point_cli_without_qt(tmp_path)                     # BLOCK_QT + sys.argv=['phymlgui.py','--file',empty]; import phymlgui; phymlgui.main() → SystemExit 1
def test_cli_usage_error_exit_2()                                 # main([]) → 2 (argparse error перехватывается)
def test_cli_empty_batch_dir_exit_2(tmp_path)
```

- [ ] **Step 2: Run `python -m pytest tests/unit/test_cli.py tests/unit/test_core_has_no_qt.py -q`** — Expected: FAIL (CLI сейчас тянет `QCoreApplication`)
- [ ] **Step 3: Переписать CLI и точку входа**
- [ ] **Step 4: Run `python -m pytest -q`** — Expected: PASS
- [ ] **Step 5: Коммит** — `git commit -m "Run the CLI on PipelineRunner without importing PySide6"`

---

### Task 13: вынести журнал, диалог настроек и строку состояния

**Files:**
- Create: `phyml_ui/log_console.py` (`LogConsole`), `phyml_ui/settings_dialog.py` (`SettingsDialog`), `phyml_ui/status_bar.py`
- Modify: `phyml_ui/main_window.py`, импорты в тестах

**Interfaces:**
- Produces (`phyml_ui/status_bar.py`): `class AppStatusBar(QStatusBar)` — сигналы `open_dir_clicked`, `settings_clicked`; `track(self, pid_provider: Callable[[], int | None]) -> None` (начать сбор выборок CPU по дереву процессов), `stop_tracking(self) -> float` (вернуть среднее и показать `cpu_analysis_done`), `set_open_dir_enabled(self, on: bool)`; атрибуты `cpu_sys_bar`, `cores_label`, `cpu_run_label`, `cpu_timer`, `samples` (список выборок) — сохраняют то, что проверяют нынешние тесты
- `SettingsDialog` получает окно как сейчас; `LogConsole` — API из Task 11

- [ ] **Step 1: Перенести классы без изменения поведения; окно хранит `self.status = AppStatusBar(...)`**
- [ ] **Step 2: Обновить тесты на новые пути импорта и атрибуты (`w.status.cpu_sys_bar`, `w.status.samples`)**
- [ ] **Step 3: Run `python -m pytest -q -rs`** — Expected: PASS
- [ ] **Step 4: Коммит** — `git commit -m "Split LogConsole, SettingsDialog and the status bar out of main_window"`

---

### Task 14: панели параметров и навигации, `main_window.py` ≤ ~350 строк

**Files:**
- Create: `phyml_ui/params_panel.py`, `phyml_ui/nav_panel.py`
- Modify: `phyml_ui/main_window.py`, GUI-тесты
- Test: `tests/gui/test_params_panel.py`, `tests/gui/test_nav_panel.py`

**Interfaces:**
- Produces (`params_panel.py`): `class ParamsPanel(QWidget)` — сигнал `changed`; `set_engine(self, engine: Engine) -> None` (перезаполняет модели); `params(self) -> dict` (ключи `PRESET_KEYS` без `engine`, плюс `use_mpi`, `mpi_np`); `set_params(self, params: dict) -> None` (без эмиссии `changed` на каждое поле, один `changed` в конце); виджеты остаются атрибутами с нынешними именами (`cb_model`, `cb_support_method`, `le_bootstrap_replicates`, `chk_use_mpi`, `le_mpi_np`, …)
- Produces (`nav_panel.py`): `class NavPanel(QToolBox)` — сигналы `recent_activated(str)`, `preset_activated(dict)`, `preset_save_requested()`, `preset_delete_requested(str)`, `history_activated(int)`; методы `set_recent(list[str])`, `set_presets(builtin: dict, user: dict)`, `set_history(records: list[dict])` (подписи через `history.display_input`)
- Окно: `self.params = ParamsPanel()`, `self.nav = NavPanel()`; автосохранение — по `params.changed`

- [ ] **Step 1: Написать падающие тесты** — `test_params_roundtrip(qtbot)` (`set_params(p)`; `params() == p` для полного словаря), `test_set_params_emits_changed_once(qtbot)` (`qtbot.waitSignal`; счётчик == 1), `test_set_engine_refills_models(qtbot)` (IQ-TREE → первая модель `MFP`), `test_nav_signals(qtbot)` (двойной клик по пресету → `preset_activated` с его параметрами; по записи истории → `history_activated(0)`)
- [ ] **Step 2: Run `python -m pytest tests/gui/test_params_panel.py tests/gui/test_nav_panel.py -q`** — Expected: FAIL
- [ ] **Step 3: Реализовать панели, перевести окно, обновить GUI-тесты (`w.params.cb_model` и т. п.)**
- [ ] **Step 4: Проверить размер** — Run: `python -c "print(sum(1 for _ in open('phyml_ui/main_window.py', encoding='utf-8')))"` — Expected: ≤ 350
- [ ] **Step 5: Run `python -m pytest -q -rs`** — Expected: PASS
- [ ] **Step 6: Ручная проверка** — критерий 6 спецификации целиком: одиночный прогон, пакет, отмена MPI, пресеты, история, смена движка; внешний вид не изменился
- [ ] **Step 7: Коммит** — `git commit -m "Split parameter and navigation panels; main_window only composes the window"`

---

### Task 15: CI с закреплёнными IQ-TREE/MUSCLE, README

**Files:**
- Create: `packaging/third_party.json`, `scripts/fetch_third_party.py`
- Modify: `.github/workflows/tests.yml`, `README.md`, `.gitignore` (`/bin/`), `tests/conftest.py` (уже ищет в `bin/` — проверить)
- Test: `tests/unit/test_fetch_third_party.py`

**Interfaces:**
- Produces (`packaging/third_party.json`) — значения проверены 2026-10-25 (`muscle-win64.v5.3.exe` совпадает с локальным `tools/muscle.exe`):

```json
{
  "iqtree": {
    "version": "2.4.0",
    "url": "https://github.com/iqtree/iqtree2/releases/download/v2.4.0/iqtree-2.4.0-Windows.zip",
    "sha256": "93f488a6cfef96ef664b23fefe5be97c2c80ebcae9cd2031c0cac92b467278be",
    "extract": {"iqtree-2.4.0-Windows/bin/iqtree2.exe": "iqtree2.exe",
                "iqtree-2.4.0-Windows/bin/libiomp5md.dll": "libiomp5md.dll"}
  },
  "muscle": {
    "version": "5.3",
    "url": "https://github.com/rcedgar/muscle/releases/download/v5.3/muscle-win64.v5.3.exe",
    "sha256": "a86637db99deb3efa1cb6762c4e3160ca33644608270eb167e4214f1f9409711",
    "save_as": "muscle.exe"
  }
}
```

- Produces (`scripts/fetch_third_party.py`): `fetch(name: str, spec: dict, dest: str) -> list[str]` — скачивает `url` (`urllib.request`, поддерживает `file://` для тестов) во временный файл, сверяет SHA256 (несовпадение → `ValueError` с ожидаемым и фактическим хешем, в `dest` ничего не пишется), затем `extract` (zip → только перечисленные члены) или `save_as`; возвращает пути; `main(argv) -> int` с `--dest` (по умолчанию `bin`) и `--only`.

- [ ] **Step 1: Написать падающие тесты** — `test_fetch_verifies_sha256(tmp_path)` (`file://` на локальный файл, неверный хеш → `ValueError`, `dest` пуст), `test_fetch_save_as(tmp_path)`, `test_fetch_extracts_listed_members(tmp_path)` (zip из двух файлов, в `extract` один → в `dest` только он)
- [ ] **Step 2: Run `python -m pytest tests/unit/test_fetch_third_party.py -q`** — Expected: FAIL
- [ ] **Step 3: Реализовать скрипт и `third_party.json`; добавить `/bin/` в `.gitignore`**
- [ ] **Step 4: Переписать `.github/workflows/tests.yml`** — job `test` на `windows-latest`, матрица `python-version: ['3.11', '3.13']`; шаги: checkout → setup-python → `pip install -r requirements.txt -r requirements-dev.txt` → `actions/cache` для `bin/` с ключом `third-party-${{ hashFiles('packaging/third_party.json') }}` → при промахе кэша `python scripts/fetch_third_party.py --dest bin` → `python -m pytest -q -rs` с `env: QT_QPA_PLATFORM: offscreen`
- [ ] **Step 5: Повторить шаги CI локально** — Run: `python scripts/fetch_third_party.py --dest bin` (папка в `.gitignore`; `conftest` находит бинарники в `bin/`), затем `python -m pytest -q -rs -m "not needs_phyml and not needs_mpi"` — Expected: PASS; в `-rs` нет пропусков по `needs_iqtree`/`needs_muscle`
- [ ] **Step 6: README (en/ru)** — Python ≥ 3.11; где лежат настройки (рядом с exe, иначе `%APPDATA%\phymlGUI`, переменная `PHYMLGUI_DATA_DIR`); раздел «Тесты»: `pip install -r requirements-dev.txt`, `python -m pytest`, переменные `PHYMLGUI_*`
- [ ] **Step 7: Финальная проверка** — Run: `python -m pytest -q -rs` — Expected: всё PASS, 0 skipped на этой машине; `git status` чистый, кроме коммита
- [ ] **Step 8: Коммит** — `git commit -m "Run the full pytest suite in CI with pinned IQ-TREE and MUSCLE"`
- [ ] **Step 9: Пуш ветки и проверка CI — только после явного «да» пользователя** (действие наружу)
