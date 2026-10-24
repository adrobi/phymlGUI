from phyml_core.pipeline import PipelineWorker, ufboot_replicates


def test_empty_fasta_fails_cleanly(qapp, tmp_path):
    """A broken input fails the run cleanly instead of killing the worker thread."""
    empty = tmp_path / 'empty.fasta'
    empty.write_text('')
    worker = PipelineWorker({'engine': 'phyml'}, [str(empty)])
    done = []
    worker.finished_signal.connect(lambda ok, tree: done.append((ok, tree)))
    try:
        worker.run()
    except Exception as e:
        raise AssertionError(f'worker crashed on an empty FASTA: {e!r}')
    assert done == [(False, '')], done
    assert worker.results[0]['status'] == 'FAIL', worker.results


def test_ufboot_replicates_raised_to_1000():
    """IQ-TREE UFBoot refuses < 1000 replicates: the PhyML-sized value is raised."""
    assert ufboot_replicates('100') == '1000'
    assert ufboot_replicates('1000') == '1000'
    assert ufboot_replicates('5000') == '5000'
    assert ufboot_replicates('') == '1000'
    assert ufboot_replicates('abc') == '1000'
