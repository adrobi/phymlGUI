# phymlGUI test suites

All suites run under pytest (`pip install -r requirements-dev.txt`):

    python -m pytest -q -rs                # everything; tests without their binary are skipped
    python -m pytest tests/unit tests/gui  # no analysis binaries needed (CI-friendly)
    python -m pytest tests/e2e             # real MUSCLE / PhyML / MPI / IQ-TREE runs
    python -m pytest -m "not slow"         # skip the long real-data scenario

Layout:

- `unit/`, `gui/` - fast checks. `gui/` builds `PhyMLApp` under `QT_QPA_PLATFORM=offscreen`.
- `e2e/` - end-to-end runs of the pipeline, batch mode, CPU monitor and IQ-TREE engine.
  `e2e/datasets.py` holds the synthetic two-clade dataset (fixture `synthetic`).
- `data/` - static fixtures (stats files, trees).
- `conftest.py` - binary lookup, markers, the `isolated_config` fixture and a session guard
  that fails the run if a test rewrites the real `phyml_config.json` / `phyml_history.json`.

## Binaries and markers

Tests that need an analysis binary carry a marker and are skipped (not failed) when the
binary is missing, e.g. on CI:

| Marker | Binary | Environment variable | Default locations |
|---|---|---|---|
| `needs_phyml` | PhyML (MPI build) | `PHYMLGUI_PHYML` | `bin/phyml-mpi.exe`, `phymlgui v1.1/phyml-mpi.exe` |
| `needs_mpi` | MS-MPI `mpiexec` | `PHYMLGUI_MPIEXEC` | `bin/mpiexec.exe`, `C:\Program Files\Microsoft MPI\Bin\mpiexec.exe` |
| `needs_muscle` | MUSCLE | `PHYMLGUI_MUSCLE` | `bin/muscle.exe`, `tools/muscle.exe` |
| `needs_iqtree` | IQ-TREE 2 | `PHYMLGUI_IQTREE` | `bin/iqtree2.exe`, `tools/iqtree2/iqtree2.exe` |

`PHYMLGUI_RAXML` (RAxML-NG) is looked up the same way for the upcoming engine.
The environment variable wins over the default locations. `slow` marks long end-to-end
tests; `-rs` prints the reason for every skip.

## Working files

Tests work in pytest's `tmp_path` and never write to the repository. The one exception
is the real-data cache `testrun/real/cytb_mammals.fasta` (gitignored): `e2e/fetch_real_data.py`
downloads mitochondrial CytB sequences from NCBI once for `test_real_cytb_tree`, which is
skipped when the cache is absent and the network is unreachable.
