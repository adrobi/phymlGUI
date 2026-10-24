# phymlGUI test suites

Binary-free checks run under pytest (`pip install -r requirements-dev.txt`):

    python -m pytest tests/unit tests/gui   # no analysis binaries needed (CI-friendly)

Standalone scripts, runnable on any machine with the Python dependencies:

    python tests/run_tests.py         # end-to-end pipeline, needs local binaries
    python tests/test_gui_logic.py    # GUI behaviour + live CPU monitoring
    python tests/test_batch.py        # batch mode + CSV summary + history
    python tests/test_iqtree.py       # IQ-TREE engine (skips without the binary)

Suites that need local analysis binaries (`phymlgui v1.1/phyml-mpi.exe`,
`tools/muscle.exe`, Microsoft MPI, optionally `tools/iqtree2/iqtree2.exe`)
print `SKIP` and exit 0 when the binaries are absent — e.g. on CI.

Working files and generated datasets live in `testrun/` (gitignored);
`tests/fetch_real_data.py` downloads and caches real NCBI mitochondrial
CytB sequences used by the `t9` end-to-end scenario.
