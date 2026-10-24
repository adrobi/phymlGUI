# Подпроект «Фундамент» — дизайн

Дата: 2026-10-25 · Статус: на ревью · Связано: [спайк RAxML-NG под Windows](../spikes/2026-10-24-raxml-ng-windows/README.md)

## 1. Контекст и цель

Раунд доработок phymlGUI разбит на четыре подпроекта в порядке
**Фундамент → (Наука ∥ Рисунки) → Релиз**. «Фундамент» идёт первым: все
новые функции «Науки» (повтор прогона из истории, таблица сравнения,
третий движок) и «Релиза» (exe со встроенными бинарниками) должны лечь на
код, который тестируется без окна и не зависит от текущей папки.

**Сказано пользователем:** делаем все направления, релиз в конце; подход A
(ядро без Qt); конфиг рядом с exe; полный переход на pytest; CI с IQ-TREE и
MUSCLE; RAxML-NG в этом раунде, собранный нативно под Windows (спайк
успешен); Python ≥ 3.11.

**Допущения:** пользователи — коллеги и студенты на Windows 10/11;
интерфейс остаётся двуязычным (en/ru); видимое поведение окна в этом
подпроекте не меняется, кроме мест, явно перечисленных ниже.

**Проблемы, которые закрывает подпроект:**

- `phyml_ui/main_window.py` (~1000 строк) смешивает виджеты, конфиг,
  историю, пресеты, проверки и запуск;
- конфиг и история пишутся относительно текущей папки — у exe, запущенного
  ярлыком, «теряются» настройки;
- ядро (`pipeline.py`) зависит от Qt-сигналов, поэтому и CLI тянет PySide6;
- выбор движка — ветвление `if engine == ...` в нескольких местах;
- тесты — скрипты, которые двигают настоящий `phyml_config.json`, содержат
  машинно-зависимые проверки (8 ядер / 16 потоков) и в CI запускаются
  только частично (просмотрщик деревьев там пропускается).

## 2. Архитектура

Правило зависимостей: **`phyml_core` не импортирует PySide6** (проверяется
тестом). `phyml_ui` зависит от `phyml_core`, но не наоборот.

```
phyml_core/                    — без Qt
  paths.py        AppPaths: папка приложения, папка данных, bin/, ресурсы
  settings.py     схема конфига с умолчаниями, атомарные загрузка/сохранение, миграция
  history.py      HistoryStore
  presets.py      встроенные и пользовательские пресеты
  alignment.py    чтение FASTA, проверка выравнивания, очистка ID, PHYLIP, сводка
  launchers.py    Native, Mpi
  engines/
    base.py       Engine, Issue, EngineOutputs
    phyml.py      PhyML
    iqtree.py     IqTree
    __init__.py   ENGINES = {'phyml': PhyML(), 'iqtree': IqTree()}
  runner.py       PipelineRunner, FileResult, RunResult
  cli.py          headless-режим поверх runner
  i18n.py, utils.py   без изменений по смыслу

phyml_ui/
  main_window.py  только сборка окна и связи между частями (цель ≤ ~350 строк)
  params_panel.py группы параметров ⇄ словарь params
  nav_panel.py    недавние / пресеты / история
  log_console.py  структурированный журнал (уровни приходят из ядра)
  settings_dialog.py
  status_bar.py   CPU-монитор, кнопка папки результатов, настройки
  worker.py       QThread-адаптер над PipelineRunner
  tree_viewer.py, themes.py   без изменений (просмотрщик — в подпроекте «Рисунки»)

phymlgui.py       только точка входа; реэкспорты «для совместимости» удаляются
```

## 3. Движки и способы запуска

```python
# launchers.py
class Native:  wrap(argv) -> argv
class Mpi:     __init__(mpiexec: str, np: int); wrap(argv) -> [mpiexec, '-np', str(np), *argv]

# engines/base.py
@dataclass(frozen=True)
class Issue:
    level: Literal['error', 'warning']
    key: str                 # ключ локализации
    args: tuple = ()

@dataclass(frozen=True)
class EngineOutputs:
    tree: str
    stats: str
    boot_trees: str | None
    log: str | None

class Engine(ABC):
    key: str                 # 'phyml' | 'iqtree' | позже 'raxml'
    label_key: str
    def models(self, datatype: str) -> list[str]
    def validate(self, params: dict, paths: AppPaths) -> list[Issue]
    def normalize(self, params: dict) -> tuple[dict, list[Issue]]
    def executable(self, params: dict, paths: AppPaths) -> str
    def command(self, exe: str, phylip: str, params: dict) -> list[str]   # чистая функция
    def outputs(self, phylip: str) -> EngineOutputs
    def parse_stats(self, outputs: EngineOutputs) -> dict[str, str]     # model, taxa, lnL, gamma, tstv, time
    def launcher(self, params: dict) -> Native | Mpi
```

- Параметры остаются **плоским словарём** с теми же ключами, что в
  нынешнем конфиге, — сохранённые настройки и пресеты не ломаются.
- `validate` — единственный источник правил: «бутстреп на MPI-сборке
  PhyML без MPI» (error), «нечисловое число реплик/ядер/pinv» (error),
  «нет исполняемого файла» (error), «UFBoot < 1000» (warning) и т. п.
- `normalize` подгоняет параметры с заметкой в журнал (UFBoot → 1000,
  сегодняшняя `ufboot_replicates` переезжает сюда).
- `executable`: путь из конфига; если он пуст — бинарник из `bin/` рядом с
  приложением.
- Сообщение об ошибке процесса подставляет имя движка (сейчас при ошибке
  IQ-TREE пишется «PhyML завершил работу с кодом …»).
- RAxML-NG добавляется в «Науке» одним классом `engines/raxml.py`;
  исполняемый файл — нативная сборка по рецепту спайка, запуск `Native`.
  WSL-запуск не нужен.

## 4. Хранение данных

**`AppPaths`**

- `app_dir`: у собранного exe — `dirname(sys.executable)`, из исходников —
  корень репозитория;
- `data_dir`: `$PHYMLGUI_DATA_DIR`, если задана; иначе `app_dir`, если в неё
  можно писать (проба созданием временного файла); иначе
  `%APPDATA%\phymlGUI` (создаётся);
- `bin_dir`: `app_dir/bin`;
- `resource(name)`: ресурсы сборки (`sys._MEIPASS`) с откатом на `app_dir`;
- `to_stored(path)` / `from_stored(path)`: пути внутри `app_dir` хранятся
  относительными, остальные — абсолютными.

**`settings.py`**

- `DEFAULTS` — все ключи нынешнего конфига + `schema_version: 2`;
- `load(path) -> dict`: умолчания ← файл; неизвестные ключи сохраняются;
  битый JSON → умолчания + ошибка в журнал (файл не перезаписывается до
  первого успешного сохранения, копия кладётся в `*.broken`);
- `save(path, cfg) -> None`: временный файл + `os.replace`; исключение
  `OSError` пробрасывается вызывающему, интерфейс пишет его в журнал;
- `migrate_legacy(paths, cwd)`: если в `data_dir` нет конфига, а в `cwd`
  лежат `phyml_config.json` / `phyml_history.json` — **копирует** их,
  возвращает список скопированного для журнала. Однократно.

**`HistoryStore(path, limit=200)`**

- `load() -> list[dict]` (новые сверху; повреждённый файл → пустой список
  + ошибка в журнал), `append(record)`, `get(index)`;
- запись: `ts`, `inputs` (пути), `engine`, `params` (полный словарь),
  `ok`/`n`, `duration_s`, `files` (по файлу: статус, дерево, статистика);
- старые записи без `params`/`files` читаются (поля по умолчанию).

**`presets.py`**: `BUILTIN` (как сейчас + ключ `engine`), пользовательские
пресеты живут в конфиге; `apply(preset, params) -> dict` переключает и движок.

## 5. Пайплайн и ошибки

```python
@dataclass
class FileResult:
    file: str
    status: Literal['ok', 'fail', 'cancelled']
    tree: str = ''
    stats: dict = field(default_factory=dict)
    error: str = ''

@dataclass
class RunResult:
    files: list[FileResult]
    cancelled: bool
    # ok_count, success — вычисляемые свойства

class PipelineRunner:
    def __init__(self, params: dict, files: list[str], paths: AppPaths,
                 on_log: Callable[[str, str], None] | None = None,     # (level, text); None — молча
                 on_status: Callable[[str, str], None] | None = None)  # (file name, status)
    def run(self) -> RunResult        # никогда не бросает исключений
    def cancel(self) -> None          # потокобезопасно
```

Шаги для каждого файла:

1. `alignment.read_fasta` — пустой/битый файл → `fail` с понятным текстом;
2. если длины различаются — MUSCLE (синтаксис v5, при неудаче v3) через
   `Native`;
3. очистка ID → **проверка коллизий** (разные ID дали одинаковое имя →
   `fail` со списком конфликтов) → PHYLIP-relaxed;
4. `engine.validate(params, paths)` (error → `fail`, warning → журнал) → `engine.normalize`
   → `launcher.wrap(engine.command(...))` → построчный вывод в журнал →
   проверка кода возврата и наличия `outputs.tree` → `engine.parse_stats`.

Гарантии:

- каждый файл обёрнут в `try/except` → `FileResult(status='fail', error=...)`;
  `run()` в целом — `try/finally`, итог возвращается всегда;
- `cancel()` ставит флаг и завершает **дерево процессов** текущего шага
  (через `psutil`, если доступен; иначе `terminate()` корневого процесса);
- уровни журнала (`error` / `success` / `system` / `out`) задаёт ядро;
  `LogConsole` больше не угадывает их по префиксам строк;
- проверка перед запуском в окне вызывает тот же `engine.validate` и
  показывает проблемы до старта (ad-hoc проверки в `start_pipeline`
  удаляются).

`phyml_ui/worker.py`: `QThread`, который запускает `PipelineRunner.run()` и
переводит колбэки в сигналы `log(str, str)`, `status(str, str)`,
`finished(object)`; `cancel()` проксируется.

CLI: `python phymlgui.py --file X | --batch DIR [--config PRESET.json]`;
работает без импорта PySide6; коды выхода: 0 — все файлы `ok`, 1 — есть
`fail`/`cancelled`, 2 — ошибка аргументов или входа.

## 6. Интерфейс

Окно собирается из модулей раздела 2; внешний вид и раскладка не
меняются. Видимые изменения только такие:

- конфиг и история — в `data_dir` (при первом запуске — сообщение о
  миграции в журнале);
- проблемы параметров показываются до запуска (раньше часть из них
  всплывала только в журнале);
- журнал раскрашивается по уровням из ядра;
- при отмене завершаются и дочерние процессы MPI.

## 7. Тесты и CI

- `requirements-dev.txt`: `pytest`, `pytest-qt`;
- `tests/unit/` (ядро, без Qt), `tests/gui/` (`qtbot`, offscreen),
  `tests/e2e/` (реальные бинарники), `tests/data/` (маленькие деревья с
  поддержками, файл бутстреп-деревьев, FASTA, образцы статистики);
- `conftest.py`: фикстура `data_dir` (временная папка через
  `PHYMLGUI_DATA_DIR`), поиск бинарников (`PHYMLGUI_PHYML`, `PHYMLGUI_IQTREE`,
  `PHYMLGUI_MUSCLE`, `PHYMLGUI_RAXML`, затем `bin/`, затем нынешние локальные
  пути), маркеры `needs_phyml`, `needs_mpi`, `needs_iqtree`, `needs_muscle`
  с автоматическим пропуском и причиной;
- все нынешние проверки переносятся один к одному (включая регрессионные
  тесты от 2026-10-24); машинно-зависимые утверждения заменяются
  сравнением с `detect_cores()`; старые скрипты-наборы удаляются, а
  загрузчик реальных данных `fetch_real_data.py` переезжает в `tests/e2e/`
  как вспомогательный модуль;
- новые тесты: ядро не импортирует PySide6; CLI работает без PySide6;
  `run()` не бросает исключений и при падении движка-заглушки окно
  возвращается в исходное состояние; отмена убивает дочерний процесс;
  коллизия ID → понятная ошибка; миграция старого конфига; относительные
  пути; повреждённые конфиг/история;
- CI (`windows-latest`, Python 3.11 и 3.13): скачивает официальные IQ-TREE и
  MUSCLE (версии и SHA256 — в `packaging/third_party.json`, его же потом
  использует «Релиз»), кэширует, запускает `pytest`; PhyML+MPI пропускаются;
- README: Python ≥ 3.11, где лежат настройки, как запускать тесты.

## 8. Вне рамок подпроекта

- класс движка RAxML-NG, таблица сравнения прогонов, повтор из истории,
  предпросмотр выравнивания — «Наука»;
- любые изменения просмотрщика деревьев — «Рисунки»;
- сборка exe, бинарники в `bin/`, сборка RAxML-NG в CI, проверка обновлений,
  лицензии в релизе — «Релиз»;
- изменение внешнего вида окна.

## 9. Критерии готовности

1. `phyml_core` не импортирует PySide6; CLI работает в окружении без PySide6.
2. `main_window.py` ≤ ~350 строк и содержит только сборку окна и связи.
3. Все прежние проверки и новые тесты из раздела 7 проходят: локально —
   полностью (с PhyML/MPI/IQ-TREE/MUSCLE), в CI — всё, кроме `needs_phyml`
   и `needs_mpi`.
4. Тестовый прогон не изменяет `phyml_config.json` / `phyml_history.json`
   пользователя (проверяется сравнением хешей до и после).
5. При запуске из любой текущей папки настройки читаются из `data_dir`;
   старые настройки из текущей папки переносятся один раз.
6. Ручная проверка в окне: одиночный прогон, пакетный режим, отмена при
   MPI-прогоне (в диспетчере задач не остаётся `phyml-mpi.exe`), пресеты,
   история, смена движка.

## 10. Порядок перехода (без «большого взрыва»)

Каждый шаг оставляет приложение рабочим, а тесты — зелёными:

1. pytest-инфраструктура и перенос текущих проверок как есть;
2. `paths` + `settings` + `history` + `presets` (окно переходит на них);
3. `launchers` + `engines` (PhyML, IQ-TREE) с тестами команд;
4. `alignment` + `runner` + `worker`; CLI на runner;
5. разрезание `main_window.py` на модули интерфейса;
6. CI с IQ-TREE/MUSCLE, обновление README.

## 11. Риски

- **Перенос тестов меняет то, что они проверяют.** Смягчение: шаг 1 —
  перенос без изменения логики, сверка числа проверок до и после.
- **Скрытые зависимости окна от порядка сигналов** (автосохранение во время
  загрузки конфига, `_is_loading`). Смягчение: GUI-тесты на загрузку
  конфига, применение пресета и смену движка до разрезания окна.
- **Разные версии IQ-TREE локально и в CI.** Смягчение: версия в CI
  фиксируется в `packaging/third_party.json`; локальный бинарник не
  обязан совпадать, тесты не сравнивают числа между машинами.
