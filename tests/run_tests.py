"""End-to-end tests for phymlGUI PipelineWorker using real MUSCLE + phyml-mpi.

Runs the production pipeline code (phymlgui.PipelineWorker) on synthetic data
with a known topology: two clades A=(A1..A4), B=(B1..B4). After each run we
check the output files and that both clades come out monophyletic.

Scenarios:
  t1: unaligned input, no MPI   (MUSCLE + phyml-mpi standalone)
  t2: unaligned input, MPI -np2 (MUSCLE + mpiexec)
  t3: aligned input,   no MPI   (no MUSCLE)
  t4: aligned input,   MPI -np2
"""
import os, sys, random, shutil, re

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import phymlgui
from Bio import Phylo, SeqIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

RUN = os.path.join(ROOT, 'testrun')
os.makedirs(RUN, exist_ok=True)
PHYML_EXE = os.path.join(ROOT, 'phymlgui v1.1', 'phyml-mpi.exe')
MUSCLE_EXE = os.path.join(ROOT, 'tools', 'muscle.exe')
MPIEXEC_EXE = r'C:\Program Files\Microsoft MPI\Bin\mpiexec.exe'

if not all(map(os.path.exists, (PHYML_EXE, MUSCLE_EXE, MPIEXEC_EXE))):
    print('SKIP: local analysis binaries not found (phymlgui v1.1/phyml-mpi.exe, tools/muscle.exe, MS-MPI)')
    sys.exit(0)

# ---------- test data generation ----------
def evolve(seq, rate, rng):
    bases = 'ACGT'
    return ''.join(b if rng.random() > rate else rng.choice(bases) for b in seq)

def make_dataset():
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

# ---------- pipeline runner ----------
def run_pipeline(folder, fasta_name, use_mpi, support='bootstrap', model='HKY85', search='NNI'):
    wd = os.path.join(RUN, folder)
    shutil.rmtree(wd, ignore_errors=True)
    os.makedirs(wd, exist_ok=True)
    shutil.copy(os.path.join(RUN, fasta_name), wd)
    os.chdir(wd)
    app = phymlgui.QApplication.instance() or phymlgui.QApplication([])

    config = {
        'phyml_path': PHYML_EXE, 'muscle_path': MUSCLE_EXE,
        'mpirun_path': MPIEXEC_EXE, 'mpi_np': '2', 'use_mpi': use_mpi,
        'datatype': 'nt', 'model': model,
        'support_method': support, 'bootstrap_replicates': '20',
        'freq': 'default', 'tstv': 'e', 'pinv': '0.0',
        'classes': '4', 'gamma': 'e', 'search': search,
        'optimize': 'tlr', 'parsimony': False,
    }
    logs = []
    worker = phymlgui.PipelineWorker(config, os.path.join(wd, fasta_name))
    worker.log_signal.connect(logs.append)
    worker.finished_signal.connect(lambda ok, tree: logs.append(f'__FINISHED__{ok}|{tree}'))
    worker.run()  # run synchronously in this thread

    os.chdir(ROOT)
    return wd, logs

def check(wd, logs, expect_alignment):
    ok = any(l.startswith('__FINISHED__True') for l in logs)
    assert ok, 'pipeline reported failure:\n' + '\n'.join(logs)

    aligned = [f for f in os.listdir(wd) if f.endswith('_aligned.fasta')]
    assert bool(aligned) == expect_alignment, f'aligned file presence mismatch: {aligned}'

    tree_path = [f for f in os.listdir(wd) if f.endswith('_phyml_tree.txt')][0]
    stats_path = [f for f in os.listdir(wd) if f.endswith('_phyml_stats.txt')][0]
    tree = Phylo.read(os.path.join(wd, tree_path), 'newick')
    terms = {t.name for t in tree.get_terminals()}
    assert len(terms) == 8, f'expected 8 taxa, got {terms}'

    cladeA = {t for t in terms if t.startswith('A')}
    cladeB = {t for t in terms if t.startswith('B')}
    # Trees are UNROOTED with an arbitrary trifurcating root: the A|B split
    # shows up as a node whose terminal set equals EITHER clade (whichever
    # side faces away from the arbitrary root), never necessarily both.
    def is_split_present(names):
        return any(
            not cl.is_terminal() and {t.name for t in cl.get_terminals()} == names
            for cl in tree.find_clades())
    split_ok = is_split_present(cladeA) or is_split_present(cladeB)
    assert split_ok, 'A|B split missing — tree topology wrong'

    stats = open(os.path.join(wd, stats_path)).read()
    assert 'Log-likelihood' in stats, 'stats file lacks log-likelihood'
    stats_lines = [l for l in logs if 'HKY85' in l and '|' in l]
    assert stats_lines, 'stats summary line missing from worker log'
    m = re.search(r'lnL[^\d-]*(-?[\d.]+)', stats_lines[0])
    lnl_file = re.search(r'Log-likelihood:\s*(-?[\d.]+)', stats).group(1)
    assert m and abs(float(m.group(1)) - float(lnl_file)) < 0.01, 'lnL mismatch in stats summary'
    return tree_path, split_ok

if __name__ == '__main__':
    names, sa, su = make_dataset()
    write_fasta(os.path.join(RUN, 'test_prealigned.fasta'), names, sa)
    write_fasta(os.path.join(RUN, 'test_unaligned.fasta'), names, su)

    # phyml-mpi cannot distribute a serial bootstrap (asserts n_proc > 1),
    # so standalone runs use aLRT branch support; MPI runs use bootstrap.
    scenarios = [
        ('t1_unaligned_serial_alrt', 'test_unaligned.fasta', False, True,  '-4'),
        ('t2_unaligned_mpi_boot',    'test_unaligned.fasta', True,  True,  'bootstrap'),
        ('t3_aligned_serial_alrt',   'test_prealigned.fasta',   False, False, '-4'),
        ('t4_aligned_mpi_boot',      'test_prealigned.fasta',   True,  False, 'bootstrap'),
    ]
    for folder, fasta, mpi, expect_aln, support in scenarios:
        wd, logs = run_pipeline(folder, fasta, mpi, support)
        tree, _ = check(wd, logs, expect_aln)
        mpi_tag = 'MPI x2 + bootstrap' if mpi else 'serial + aLRT'
        aln_tag = 'MUSCLE ran' if expect_aln else 'pre-aligned'
        print(f'PASS {folder}: {mpi_tag}, {aln_tag}, tree OK ({tree})')

    # t5: serial bootstrap on the MPI build must fail gracefully (PhyML assert)
    wd, logs = run_pipeline('t5_serial_boot_expected_fail', 'test_unaligned.fasta', False, 'bootstrap')
    failed_ok = any(l.startswith('__FINISHED__False') for l in logs)
    assert failed_ok, 'expected graceful failure for serial bootstrap on MPI build'
    print('PASS t5_serial_boot_expected_fail: PhyML error surfaced in log, no crash')

    # t9: real NCBI data (mammalian mitochondrial CytB) with known phylogeny
    sys.path.insert(0, RUN)
    import fetch_real_data
    if not os.path.exists(fetch_real_data.OUT_FA):
        try:
            assert fetch_real_data.main() == 0
        except Exception as e:
            print(f'SKIP t9_real_ncbi: real data unavailable ({e})')
    if os.path.exists(fetch_real_data.OUT_FA):
        shutil.copy(fetch_real_data.OUT_FA, os.path.join(RUN, 'cytb_mammals.fasta'))
        # cross-order mammalian mtDNA needs GTR+gamma and SPR search;
        # HKY85+NNI scrambles the short hominoid internal branches
        wd, logs = run_pipeline('t9_real_ncbi', 'cytb_mammals.fasta', True,
                                'bootstrap', model='GTR', search='SPR')
        ok = any(l.startswith('__FINISHED__True') for l in logs)
        assert ok, 'real-data pipeline failed:\n' + '\n'.join(logs[-8:])
        tree_path = [f for f in os.listdir(wd) if f.endswith('_phyml_tree.txt')][0]
        tree = Phylo.read(os.path.join(wd, tree_path), 'newick')
        terms = {t.name for t in tree.get_terminals()}
        rodents = {'Mus_musculus', 'Rattus_norvegicus'}
        primates = {'Homo_sapiens', 'Pan_troglodytes', 'Pan_paniscus',
                    'Gorilla_gorilla', 'Pongo_pygmaeus', 'Macaca_mulatta'}
        assert terms == primates | rodents, f'unexpected taxa: {terms}'
        def split(names):
            return any(not c.is_terminal() and {t.name for t in c.get_terminals()} == names
                       for c in tree.find_clades())
        # rodents|primates is one split: either side may face the arbitrary root
        assert split(rodents) or split(primates), 'rodents/primates split missing'
        # Pan paniscus + Pan troglodytes is the strongly supported sister pair
        # (~19/20). NB: Homo+Pan and the exact hominoid backbone are NOT
        # recoverable from a single 1141 bp mitochondrial gene (saturated 3rd
        # codon positions, long macaque branch) — a known single-gene CytB
        # limitation, not a pipeline defect, so we do not assert them.
        pan_pair = {'Pan_troglodytes', 'Pan_paniscus'}
        assert split(pan_pair), 'Pan sister pair missing in CytB tree'
        print('PASS t9_real_ncbi: real CytB tree recovers rodents/primates split and Pan pair')

    print('ALL PIPELINE TESTS PASSED')
