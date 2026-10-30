import gc
import locale

import pytest
from Bio import AlignIO
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from phyml_core import alignment
from phyml_core.alignment import AlignmentError
from phyml_core.i18n import _t


@pytest.fixture
def locale_codec(monkeypatch):
    """locale_codec('cp1251'): make the preferred (ANSI) encoding the same on every machine."""
    def use(name):
        monkeypatch.setattr(locale, 'getpreferredencoding', lambda *args, **kwargs: name)
    return use


def rec(rid, seq):
    return SeqRecord(Seq(seq), id=rid, name=rid, description='')


def write_fasta(path, records):
    path.write_text(''.join(f'>{rid}\n{seq}\n' for rid, seq in records), encoding='utf-8')
    return str(path)


def test_alignment_error_is_a_value_error():
    assert issubclass(AlignmentError, ValueError)


@pytest.mark.parametrize('content', ['', '\n\n', '   \n', 'just some text\n>A\nACGT\n'])
def test_read_fasta_empty_raises(tmp_path, content):
    path = tmp_path / 'empty.fasta'
    path.write_text(content)
    with pytest.raises(AlignmentError) as exc:
        alignment.read_fasta(str(path))
    assert str(exc.value) == _t('err_empty')


def test_read_fasta_falls_back_to_locale_encoding(tmp_path, locale_codec, recwarn):
    """An ANSI file (cp1251 headers) still reads, as it did with the locale codec."""
    locale_codec('cp1251')
    path = tmp_path / 'ansi.fasta'
    path.write_bytes('>Волк_1 обыкновенный\nACGT\n>Лиса\nACGA\n'.encode('cp1251'))
    records = alignment.read_fasta(str(path))
    assert [r.id for r in records] == ['Волк_1', 'Лиса']
    assert records[0].description.endswith('обыкновенный')
    gc.collect()
    assert [w for w in recwarn if issubclass(w.category, ResourceWarning)] == []


def test_read_fasta_prefers_utf8_over_the_locale_encoding(tmp_path, locale_codec):
    locale_codec('cp1251')
    path = tmp_path / 'utf8.fasta'
    path.write_bytes('>Волк\nACGT\n'.encode('utf-8'))
    assert [r.id for r in alignment.read_fasta(str(path))] == ['Волк']


def test_read_fasta_reports_a_file_no_encoding_decodes(tmp_path, locale_codec):
    locale_codec('ascii')
    path = tmp_path / 'ansi.fasta'
    path.write_bytes('>Волк\nACGT\n'.encode('cp1251'))
    with pytest.raises(AlignmentError) as exc:
        alignment.read_fasta(str(path))
    assert 'ascii' in str(exc.value) and 'decode' in str(exc.value)


def test_read_fasta_closes_the_file_when_it_is_empty(tmp_path, recwarn):
    """An empty file must not leave an open handle behind (a ResourceWarning at collection)."""
    path = tmp_path / 'empty.fasta'
    path.write_text('')
    with pytest.raises(AlignmentError):
        alignment.read_fasta(str(path))
    gc.collect()
    leaked = [w for w in recwarn if issubclass(w.category, ResourceWarning)]
    assert leaked == []


def test_read_fasta_tolerates_bom_and_crlf(tmp_path):
    path = tmp_path / 'выравнивание с пробелом.fasta'
    path.write_bytes(b'\xef\xbb\xbf>A\r\nACGT\r\n>B\r\nACGA\r\n')
    records = alignment.read_fasta(str(path))
    assert [r.id for r in records] == ['A', 'B']
    assert str(records[0].seq) == 'ACGT'
    assert str(records[1].seq) == 'ACGA'


def test_is_aligned():
    assert alignment.is_aligned([rec('A', 'ACGT'), rec('B', 'AC-T')])
    assert alignment.is_aligned([rec('A', 'ACGT')])
    assert not alignment.is_aligned([rec('A', 'ACGT'), rec('B', 'ACG')])


def test_is_aligned_rejects_an_empty_list():
    with pytest.raises(AlignmentError) as exc:
        alignment.is_aligned([])
    assert str(exc.value) == _t('err_empty')


def test_clean_id():
    assert alignment.clean_id('Homo sapiens|x:1') == 'Homo_sapiens_x_1'
    assert alignment.clean_id('a.b;c(d),e\tf') == 'a_b_c_d__e_f'
    assert alignment.clean_id('plain-id_1') == 'plain-id_1'


def test_find_collisions():
    assert alignment.find_collisions(['A.1', 'A_1', 'B']) == {'A_1': ['A.1', 'A_1']}


def test_find_collisions_reports_exact_duplicates():
    assert alignment.find_collisions(['X', 'X']) == {'X': ['X', 'X']}


def test_find_collisions_empty_when_ids_are_distinct():
    assert alignment.find_collisions(['A.1', 'A.2', 'B']) == {}
    assert alignment.find_collisions([]) == {}


def test_write_phylip_cleans_ids_and_dots(tmp_path):
    out = tmp_path / 'вывод с пробелом.phy'
    records = [rec('Homo sapiens|x:1', 'AC.GT'), rec('Pan.troglodytes', 'ACGG.')]
    alignment.write_phylip(records, str(out))
    back = AlignIO.read(str(out), 'phylip-relaxed')
    assert [r.id for r in back] == ['Homo_sapiens_x_1', 'Pan_troglodytes']
    assert [str(r.seq) for r in back] == ['AC-GT', 'ACGG-']
    # the caller's records are left as they were
    assert records[0].id == 'Homo sapiens|x:1'
    assert str(records[0].seq) == 'AC.GT'


def test_write_phylip_raises_on_collision(tmp_path):
    out = tmp_path / 'clash.phy'
    with pytest.raises(AlignmentError) as exc:
        alignment.write_phylip([rec('A.1', 'ACGT'), rec('A_1', 'ACGA'), rec('B', 'ACGG')], str(out))
    text = str(exc.value)
    assert 'A.1' in text and 'A_1' in text
    assert text == _t('err_id_collision').format('A.1, A_1 → A_1')
    assert not out.exists()


def test_write_phylip_raises_on_exact_duplicates(tmp_path):
    out = tmp_path / 'dup.phy'
    with pytest.raises(AlignmentError):
        alignment.write_phylip([rec('X', 'ACGT'), rec('X', 'ACGA')], str(out))
    assert not out.exists()


def test_write_phylip_uses_locale_encoding(tmp_path, locale_codec):
    """The bytes are the locale codec's, as with the old conversion; the tree viewer reads them back so."""
    locale_codec('cp1251')
    out = tmp_path / 'ru.phy'
    alignment.write_phylip([rec('Волк обыкновенный', 'ACGT'), rec('Лиса', 'ACGA')], str(out))
    raw = out.read_bytes()
    assert 'Волк_обыкновенный'.encode('cp1251') in raw
    assert 'Лиса'.encode('cp1251') in raw
    assert 'Лиса'.encode('utf-8') not in raw
    with open(out, encoding='cp1251') as fh:
        back = AlignIO.read(fh, 'phylip-relaxed')
    assert [r.id for r in back] == ['Волк_обыкновенный', 'Лиса']


def test_write_phylip_reports_an_id_the_locale_encoding_cannot_hold(tmp_path, locale_codec):
    locale_codec('cp1251')
    out = tmp_path / 'bad.phy'
    with pytest.raises(AlignmentError) as exc:
        alignment.write_phylip([rec('café', 'ACGT'), rec('B', 'ACGA')], str(out))
    assert 'encode' in str(exc.value)
    assert not out.exists()


def test_summarize(tmp_path):
    path = tmp_path / 'набор данных 1.fasta'
    write_fasta(path, [('A', 'ACGT--'), ('B', 'AC'), ('C', 'ACGTA')])
    # 13 sites, 2 gaps -> 15.4 %
    assert alignment.summarize(str(path)) == {'n': 3, 'min_len': 2, 'max_len': 6, 'gap_pct': 15.4}


def test_summarize_without_gaps(tmp_path):
    path = tmp_path / 'a.fasta'
    write_fasta(path, [('A', 'ACGT'), ('B', 'ACGA')])
    assert alignment.summarize(str(path)) == {'n': 2, 'min_len': 4, 'max_len': 4, 'gap_pct': 0.0}


def test_summarize_of_empty_sequences_has_no_division_by_zero(tmp_path):
    path = tmp_path / 'blank.fasta'
    path.write_text('>A\n>B\n')
    assert alignment.summarize(str(path)) == {'n': 2, 'min_len': 0, 'max_len': 0, 'gap_pct': 0}


def test_summarize_of_an_empty_file_raises(tmp_path):
    path = tmp_path / 'empty.fasta'
    path.write_text('')
    with pytest.raises(AlignmentError):
        alignment.summarize(str(path))


def test_path_helpers():
    assert alignment.aligned_path('/d/run 1/in.fasta') == '/d/run 1/in_aligned.fasta'
    assert alignment.phylip_path('/d/run 1/in.fasta') == '/d/run 1/in.phy'
    assert alignment.aligned_path('in.fas') == 'in_aligned.fasta'
    assert alignment.phylip_path('in.fas') == 'in.phy'
