"""Synthetic test data and shared configs for the end-to-end suites.

The dataset has a known topology: two clades A=(A1..A4) and B=(B1..B4), so a
finished run can be checked for the A|B split.
"""
import pytest

from dataset_gen import evolve, make_dataset, write_fasta  # noqa: F401  (re-exported)


@pytest.fixture
def synthetic(tmp_path):
    """The dataset written to tmp_path: {'aligned': Path, 'unaligned': Path}."""
    names, aligned, unaligned = make_dataset()
    folder = tmp_path / 'synthetic'
    folder.mkdir()
    paths = {'aligned': folder / 'test_prealigned.fasta',
             'unaligned': folder / 'test_unaligned.fasta'}
    write_fasta(paths['aligned'], names, aligned)
    write_fasta(paths['unaligned'], names, unaligned)
    return paths


def phyml_config(binaries, **overrides):
    """PipelineRunner params for a small PhyML run (MPI x2, HKY85, 20 bootstraps)."""
    config = {
        'phyml_path': binaries['phyml'], 'muscle_path': binaries['muscle'],
        'mpirun_path': binaries['mpiexec'], 'mpi_np': '2', 'use_mpi': True,
        'datatype': 'nt', 'model': 'HKY85',
        'support_method': 'bootstrap', 'bootstrap_replicates': '20',
        'freq': 'default', 'tstv': 'e', 'pinv': '0.0',
        'classes': '4', 'gamma': 'e', 'search': 'NNI',
        'optimize': 'tlr', 'parsimony': False,
    }
    config.update(overrides)
    return config
