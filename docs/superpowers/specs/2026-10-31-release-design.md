# Подпроект «Релиз» — дизайн

Дата: 2026-10-31 · Статус: на ревью · Опирается на: [«Фундамент»](2026-10-25-foundation-design.md), [спайк RAxML-NG](../spikes/2026-10-24-raxml-ng-windows/README.md)

## 1. Цель и решения

Релиз phymlGUI собирается в GitHub Actions по тегу и даёт два самодостаточных
пакета: zip для Windows x64 и AppImage для Linux x86-64. В обоих пакетах уже
есть все анализ-программы.

**Решения пользователя:** Linux-пакет — AppImage; внутри оба PhyML
(последовательный и MPI), MPI на Linux — системный OpenMPI; релиз создаётся по
тегу `v*` как **черновик**, публикует его пользователь; RAxML-NG собирается и
кладётся в пакеты уже сейчас; один workflow `release.yml` (подход A); упаковщик
— PyInstaller. Задачи по Linux выполняются без субагентов.

## 2. Перенос приложения на Linux

- `phyml_core/utils.exe_name(base) -> str`: `base + '.exe'` на Windows, `base`
  иначе. Движки (`phyml-mpi`/`phyml`, `iqtree2`) и runner (`muscle`) ищут
  инструменты через него.
- `AppPaths.find_tool`: после `bin/` — поиск через `shutil.which` по тем же
  именам.
- «Открыть папку результатов»: `os.startfile` на Windows,
  `QDesktopServices.openUrl(QUrl.fromLocalFile(...))` на Linux.
- Тема «как в системе» на Linux: светлота палитры Qt; акцент — `green`.
- Папка данных: правило «папка приложения, если в неё можно писать» остаётся;
  запасной вариант — `%APPDATA%\phymlGUI` на Windows и
  `$XDG_CONFIG_HOME/phymlGUI` (по умолчанию `~/.config/phymlGUI`) на Linux.
  AppImage монтируется только для чтения, поэтому там всегда работает запасной
  вариант.
- MPI: по умолчанию `mpiexec` на Windows и `mpirun` на Linux. Значение
  `mpiexec` из конфига, перенесённого с Windows, на Linux заменяется на
  `mpirun`, если `mpiexec` не найден. Без OpenMPI проверка перед запуском даёт
  понятную ошибку (`val_no_mpiexec` с именем команды).
- `tests.yml`: к заданию на `windows-latest` добавляется `ubuntu-22.04`
  (Python 3.11 и 3.13, offscreen Qt, системные пакеты для Qt).

## 3. Сторонние инструменты

`packaging/third_party.json` получает секции `windows` и `linux`; у каждого
инструмента — версия, источник, SHA256 и способ получения (`download`,
`extract`, `build`).

| Инструмент | Windows | Linux |
|---|---|---|
| IQ-TREE 2.4.0 | официальный zip (закреплён) | официальный архив Linux x86-64 |
| MUSCLE 5.3 | официальный exe (закреплён) | официальный бинарник linux x86 |
| RAxML-NG 2.0.3 | сборка MSYS2 UCRT64 по рецепту спайка + patch | официальный zip |
| PhyML | `phyml-mpi.exe` из релиза phymlGUI v1.2, закреплён по SHA256 | сборка из закреплённого тега исходников: `phyml` и `phyml-mpi` (OpenMPI) |

- Рецепты сборки — `packaging/build_raxml_windows.sh`,
  `packaging/build_phyml_linux.sh`; их можно запускать локально.
- `scripts/fetch_third_party.py --platform {windows,linux} --dest bin`
  выполняет загрузки и сборки по манифесту; проверка SHA256 до записи в `dest`
  сохраняется.
- Лицензии: `packaging/licenses/` (GPL для PhyML, IQ-TREE, MUSCLE; AGPL-3.0 для
  RAxML-NG) кладётся в оба пакета.

## 4. Упаковка

- `packaging/phymlgui.spec` (в git) — PyInstaller, режим onedir, общий для обеих
  платформ; включает `locales.json`, `icon.png`. Старый `phymlgui.spec` из
  `.gitignore` удаляется из списка игнорируемых и заменяется этим.
- Версия: тег `vX.Y.Z` → `X.Y.Z` записывается в `phyml_core/__init__.py`
  `__version__` во время сборки (файл в репозитории не меняется).

Windows — `phymlGUI-X.Y.Z-windows-x64.zip`:

```
phymlGUI/  phymlgui.exe  _internal/  bin/{phyml-mpi.exe, iqtree2.exe, libiomp5md.dll, muscle.exe, raxml-ng.exe}  licenses/  README.txt
```

Linux — `phymlGUI-X.Y.Z-x86_64.AppImage` (собирается `appimagetool` на
ubuntu-22.04, glibc 2.35):

```
AppDir/  AppRun  phymlgui.desktop  phymlgui.png  usr/bin/{phymlgui, _internal/, bin/{phyml, phyml-mpi, iqtree2, muscle, raxml-ng}}  usr/share/licenses/phymlgui/
```

Без аргументов — окно; `--file`/`--batch` — консольный режим (тот же файл
работает на серверах).

## 5. Workflow `release.yml`

Триггеры: `push` тега `v*` и `workflow_dispatch` (пробная сборка без
публикации). Задания:

1. `tests` — переиспользует `tests.yml` (Windows и Linux).
2. `tools-windows` — RAxML-NG через MSYS2 + загрузки → артефакт `bin-windows`.
3. `tools-linux` — PhyML/PhyML-MPI из исходников (`libopenmpi-dev`) + загрузки →
   артефакт `bin-linux`.
4. `raxml-parity` — сверка Windows-сборки RAxML-NG с официальной Linux-сборкой
   (деревья, бутстреп-реплики, lnL на фиксированном дереве) на тестовых данных
   из `tests/data`; расхождение роняет workflow.
5. `package-windows`, `package-linux` — PyInstaller → zip / AppImage → дымовой
   тест готового пакета: `--version`; CLI `--file` на невыровненном FASTA через
   встроенные MUSCLE и PhyML (последовательный), отдельно IQ-TREE; проверяется,
   что дерево создано; на Linux — ещё MPI-прогон через OpenMPI раннера и запуск
   AppImage в контейнере `ubuntu:22.04` без дополнительных пакетов (кроме FUSE
   или `--appimage-extract-and-run`); окно открывается offscreen и
   закрывается.
6. `release` — только по тегу: **черновик** релиза с zip, AppImage,
   `SHA256SUMS`, `raxml-ng-2.0.3-source+patch.tar.gz` и описанием с версиями
   вложенных инструментов.

Защита: тег не формата `vX.Y.Z[-suffix]` роняет workflow до сборки; ручной
запуск ничего не публикует; сборки инструментов кэшируются по SHA256 из
манифеста.

## 6. Вне рамок

Движок RAxML-NG в приложении («Наука»); подпись файлов, MSI, `.deb`, Flatpak;
проверка обновлений; macOS и ARM.

## 7. Критерии готовности

1. Полный набор тестов проходит в CI на Windows и на ubuntu-22.04.
2. `workflow_dispatch` собирает оба пакета; все дымовые тесты, MPI на Linux и
   сверка RAxML-NG зелёные.
3. Тестовый тег (`v2.0.0-rc1`) создаёт черновик релиза со всеми файлами и
   `SHA256SUMS`; публикация только вручную.
4. AppImage работает на чистой Ubuntu 22.04 (контейнер в CI): окно открывается,
   последовательный PhyML выполняется.
5. В обоих пакетах есть `licenses/`; исходники RAxML-NG с patch'ем приложены к
   релизу.

## 8. Риски

- Сборка PhyML из исходников под Linux может потребовать правок — это первая
  задача плана; при неудаче — сообщить пользователю.
- AppImage около 200–300 МБ из-за Qt — приемлемо.
- Происхождение `phyml-mpi.exe` v1.2 известно только как «ваш прошлый релиз»;
  закрепляем его хешем, пересборка под Windows вне рамок.
