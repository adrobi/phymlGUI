"""End-to-end tests for PipelineWorker with real MUSCLE + phyml-mpi.

Runs the production pipeline on synthetic data with a known topology: two
clades A=(A1..A4), B=(B1..B4). After each run we check the output files and
that the A|B split is present in the tree.

Scenarios:
  t1: unaligned input, no MPI   (MUSCLE + phyml-mpi standalone)
  t2: unaligned input, MPI -np2 (MUSCLE + mpiexec)
  t3: aligned input,   no MPI   (no MUSCLE)
  t4: aligned input,   MPI -np2
"""
import re
import shutil
from pathlib import Path

import pytest
from Bio import Phylo

from datasets import phyml_config, synthetic  # noqa: F401  (fixture)
from phyml_core.pipeline import PipelineWorker

pytestmark = [pytest.mark.needs_phyml, pytest.mark.needs_muscle]


def run_pipeline(tmp_path, monkeypatch, source, folder, config):
    """Copy `source` into tmp_path/folder and run the worker there synchronously."""
    wd = tmp_path / folder
    wd.mkdir()
    fasta = wd / Path(source).name
    shutil.copy(source, fasta)
    monkeypatch.chdir(wd)
    logs = []
    worker = PipelineWorker(config, str(fasta))
    worker.log_signal.connect(logs.append)
    worker.finished_signal.connect(lambda ok, tree: logs.append(f'__FINISHED__{ok}|{tree}'))
    worker.run()  # run synchronously in this thread
    return wd, logs


def split_present(tree, names):
    return any(not cl.is_terminal() and {t.name for t in cl.get_terminals()} == names
               for cl in tree.find_clades())


def check_run(wd, logs, expect_alignment):
    ok = any(line.startswith('__FINISHED__True') for line in logs)
    assert ok, 'pipeline reported failure:\n' + '\n'.join(logs)

    files = [f.name for f in wd.iterdir()]
    aligned = [f for f in files if f.endswith('_aligned.fasta')]
    assert bool(aligned) == expect_alignment, f'aligned file presence mismatch: {aligned}'

    tree_path = [f for f in files if f.endswith('_phyml_tree.txt')][0]
    stats_path = [f for f in files if f.endswith('_phyml_stats.txt')][0]
    tree = Phylo.read(str(wd / tree_path), 'newick')
    terms = {t.name for t in tree.get_terminals()}
    assert len(terms) == 8, f'expected 8 taxa, got {terms}'

    clade_a = {t for t in terms if t.startswith('A')}
    clade_b = {t for t in terms if t.startswith('B')}
    # Trees are UNROOTED with an arbitrary trifurcating root: the A|B split
    # shows up as a node whose terminal set equals EITHER clade (whichever
    # side faces away from the arbitrary root), never necessarily both.
    assert split_present(tree, clade_a) or split_present(tree, clade_b), \
        'A|B split missing - tree topology wrong'

    stats = (wd / stats_path).read_text()
    assert 'Log-likelihood' in stats, 'stats file lacks log-likelihood'
    stats_lines = [line for line in logs if 'HKY85' in line and '|' in line]
    assert stats_lines, 'stats summary line missing from worker log'
    m = re.search(r'lnL[^\d-]*(-?[\d.]+)', stats_lines[0])
    lnl_file = re.search(r'Log-likelihood:\s*(-?[\d.]+)', stats).group(1)
    assert m and abs(float(m.group(1)) - float(lnl_file)) < 0.01, 'lnL mismatch in stats summary'


# phyml-mpi cannot distribute a serial bootstrap (asserts n_proc > 1), so
# standalone runs use aLRT branch support; MPI runs use bootstrap.
SCENARIOS = [
    pytest.param('t1_unaligned_serial_alrt', 'unaligned', False, True, '-4', id='t1'),
    pytest.param('t2_unaligned_mpi_boot', 'unaligned', True, True, 'bootstrap', id='t2',
                 marks=pytest.mark.needs_mpi),
    pytest.param('t3_aligned_serial_alrt', 'aligned', False, False, '-4', id='t3'),
    pytest.param('t4_aligned_mpi_boot', 'aligned', True, False, 'bootstrap', id='t4',
                 marks=pytest.mark.needs_mpi),
]


@pytest.mark.parametrize('folder, dataset, use_mpi, expect_alignment, support', SCENARIOS)
def test_scenarios(qapp, tmp_path, monkeypatch, binaries, synthetic,
                   folder, dataset, use_mpi, expect_alignment, support):
    config = phyml_config(binaries, use_mpi=use_mpi, support_method=support)
    wd, logs = run_pipeline(tmp_path, monkeypatch, synthetic[dataset], folder, config)
    check_run(wd, logs, expect_alignment)


def test_serial_bootstrap_on_mpi_build_fails_gracefully(qapp, tmp_path, monkeypatch,
                                                        binaries, synthetic):
    """Serial bootstrap on the MPI build must fail gracefully (PhyML assert)."""
    config = phyml_config(binaries, use_mpi=False, support_method='bootstrap')
    _, logs = run_pipeline(tmp_path, monkeypatch, synthetic['unaligned'],
                           't5_serial_boot_expected_fail', config)
    failed_ok = any(line.startswith('__FINISHED__False') for line in logs)
    assert failed_ok, 'expected graceful failure for serial bootstrap on MPI build'


@pytest.mark.needs_mpi
@pytest.mark.slow
def test_real_cytb_tree(qapp, tmp_path, monkeypatch, binaries):
    """Real NCBI data (mammalian mitochondrial CytB) with a known phylogeny."""
    import fetch_real_data  # imported lazily: it creates testrun/ on import
    if not Path(fetch_real_data.OUT_FA).exists():
        try:
            assert fetch_real_data.main() == 0
        except Exception as e:
            pytest.skip(f'real data unavailable ({e})')

    # cross-order mammalian mtDNA needs GTR+gamma and SPR search;
    # HKY85+NNI scrambles the short hominoid internal branches
    config = phyml_config(binaries, use_mpi=True, support_method='bootstrap',
                          model='GTR', search='SPR')
    wd, logs = run_pipeline(tmp_path, monkeypatch, fetch_real_data.OUT_FA,
                            't9_real_ncbi', config)
    ok = any(line.startswith('__FINISHED__True') for line in logs)
    assert ok, 'real-data pipeline failed:\n' + '\n'.join(logs[-8:])
    tree_path = [f.name for f in wd.iterdir() if f.name.endswith('_phyml_tree.txt')][0]
    tree = Phylo.read(str(wd / tree_path), 'newick')
    terms = {t.name for t in tree.get_terminals()}
    rodents = {'Mus_musculus', 'Rattus_norvegicus'}
    primates = {'Homo_sapiens', 'Pan_troglodytes', 'Pan_paniscus',
                'Gorilla_gorilla', 'Pongo_pygmaeus', 'Macaca_mulatta'}
    assert terms == primates | rodents, f'unexpected taxa: {terms}'
    # rodents|primates is one split: either side may face the arbitrary root
    assert split_present(tree, rodents) or split_present(tree, primates), \
        'rodents/primates split missing'
    # Pan paniscus + Pan troglodytes is the strongly supported sister pair
    # (~19/20). NB: Homo+Pan and the exact hominoid backbone are NOT
    # recoverable from a single 1141 bp mitochondrial gene (saturated 3rd
    # codon positions, long macaque branch) - a known single-gene CytB
    # limitation, not a pipeline defect, so we do not assert them.
    assert split_present(tree, {'Pan_troglodytes', 'Pan_paniscus'}), \
        'Pan sister pair missing in CytB tree'
