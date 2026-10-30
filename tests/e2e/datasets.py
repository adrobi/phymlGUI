"""Synthetic test data and shared configs for the end-to-end suites.

The dataset has a known topology: two clades A=(A1..A4) and B=(B1..B4), so a
finished run can be checked for the A|B split.
"""
import random

import pytest


def evolve(seq, rate, rng):
    bases = 'ACGT'
    return ''.join(b if rng.random() > rate else rng.choice(bases) for b in seq)


def make_dataset():
    """(names, aligned sequences, unaligned sequences) of the two-clade dataset."""
    rng = random.Random(42)
    ancestor = ''.join(rng.choice('ACGT') for _ in range(600))
    names, seqs_aligned, seqs_unaligned = [], [], []
    for clade, clade_rate in (('A', 0.16), ('B', 0.18)):
        clade_consensus = evolve(ancestor, clade_rate, rng)
        for i in range(1, 5):
            s = evolve(clade_consensus, 0.03, rng)
            name = f'{clade}{i}_testsp'
            names.append(name)
            seqs_aligned.append(s)
            # unaligned variant: drop a random block from most sequences
            if rng.random() < 0.8:
                start = rng.randrange(50, 500)
                ln = rng.randrange(8, 15)
                s = s[:start] + s[start + ln:]
            seqs_unaligned.append(s)
    return names, seqs_aligned, seqs_unaligned


def write_fasta(path, names, seqs):
    with open(path, 'w') as f:
        for n, s in zip(names, seqs):
            f.write(f'>{n}\n{s}\n')


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
