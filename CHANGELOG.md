# Changelog

All notable changes to phymlGUI are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning is
[SemVer](https://semver.org/).

## [2.0.0] — 2026-10-31

A new window, a second engine, an interactive tree viewer and ready-to-run
packages for Windows and Linux with all analysis programs included.

### Added
- IQ-TREE 2 engine: ModelFinder (`MFP`), ultrafast bootstrap with the
  1000-replicate minimum enforced, the chosen model and statistics in the window
- Tree viewer: rectangular, slanted and circular layouts, distance grid and
  scale, support threshold highlighting, clade collapsing, rerooting on an
  outgroup, majority-rule consensus from bootstrap trees, Robinson–Foulds
  comparison, PNG/SVG/PDF export
- Run history (double click reopens a tree) and built-in and user parameter
  presets
- Batch queue with per-file statuses, retry of the failed files and an Excel
  (`.xlsx`) summary next to the CSV one
- Command line without the window: `--file`, `--batch`, `--config`,
  `--version`, documented exit codes
- Linux support: XDG data folder, `mpirun` (OpenMPI), tools on `PATH`
- Release packages built by GitHub Actions: a Windows zip
  (`phymlgui.exe` and `phymlgui-cli.exe`) and a Linux AppImage, each with
  PhyML, IQ-TREE 2.4.0, MUSCLE 5.3 and RAxML-NG 2.0.3; `SHA256SUMS`; the
  RAxML-NG sources and Windows patch attached to every release
- Native Windows build of RAxML-NG 2.0.3, checked against the official Linux
  build (same best tree, likelihood, bootstrap replicates)
- Light and dark themes (following the system) with an accent colour

### Changed
- Two-pane window: parameters, recent files, presets and history on the left;
  the tree, log, statistics, summary and queue on the right
- Settings and history live in a data folder (next to the program when it is
  writable, otherwise `%APPDATA%\phymlGUI` or `~/.config/phymlGUI`); settings
  and history found in the working folder are copied there once
- All settings are checked before a run and every problem is listed at once
- The analysis core no longer depends on Qt; Cancel stops the whole process
  tree, MPI ranks included

### Fixed
- Crash when starting a run from an empty input
- IQ-TREE UFBoot and model errors
- Tree drawing: internal nodes at their own depth, non-overlapping supports,
  circular layout of polytomies
- On Linux the serial PhyML is used when MPI is off, and child programs no
  longer inherit the libraries of the package

## [1.2] — 2026-10-24

### Added
- Batch mode for a folder of FASTA files with a CSV summary
- MPI autodetection, automatic core count and a live CPU monitor
- One-line statistics summary after each run

### Changed
- Migrated the GUI from PyQt5 to PySide6 and split the code into modules

## [1.1] — 2026-04-11

### Added
- MPI support, a single English/Russian program with `locales.json`

## [1.0] — 2026-04-11

First release: a Windows GUI for the MUSCLE → PhyML pipeline.
