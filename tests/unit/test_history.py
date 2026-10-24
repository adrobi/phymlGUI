import json
import os
from datetime import datetime

import pytest

from phyml_core import history
from phyml_core.history import HistoryStore
from phyml_core.i18n import STRINGS, _t


def _rec(i):
    return history.new_record(inputs=[f'D:/данные/{i}.fasta'], engine='phyml', params={'model': 'GTR'},
                              files=[], duration_s=1.0, ts=datetime(2026, 1, 1, 12, 0))


def test_append_keeps_newest_first_and_limit(tmp_path):
    store = HistoryStore(str(tmp_path / 'h.json'))
    for i in range(205):
        store.append({'n': i})
    records = store.load()
    assert len(records) == 200
    assert records[0] == {'n': 204}                  # the last appended record is first
    assert records[-1] == {'n': 5}                   # 0..4 fell off the end


def test_custom_limit(tmp_path):
    store = HistoryStore(str(tmp_path / 'h.json'), limit=3)
    for i in range(5):
        store.append({'n': i})
    assert [r['n'] for r in store.load()] == [4, 3, 2]


def test_load_missing_file_returns_empty_without_creating_it(tmp_path):
    path = tmp_path / 'h.json'
    errors = []
    assert HistoryStore(str(path)).load(on_error=errors.append) == []
    assert errors == [] and not path.exists()


def test_load_corrupt_file_reports_and_returns_empty(tmp_path):
    path = tmp_path / 'h.json'
    path.write_text('[{oops', 'utf-8')
    errors = []
    assert HistoryStore(str(path)).load(on_error=errors.append) == []
    assert errors == [_t('err_history_broken').format(str(path))]


def test_load_corrupt_file_without_callback(tmp_path):
    path = tmp_path / 'h.json'
    path.write_text('', 'utf-8')                    # an empty file is not valid JSON
    assert HistoryStore(str(path)).load() == []
    assert (tmp_path / 'h.json.broken').exists()


def test_load_non_list_json_is_broken(tmp_path):
    path = tmp_path / 'h.json'
    path.write_text('{"ts": "x"}', 'utf-8')
    errors = []
    assert HistoryStore(str(path)).load(errors.append) == []
    assert len(errors) == 1
    assert (tmp_path / 'h.json.broken').read_text('utf-8') == '{"ts": "x"}'


def test_load_non_utf8_file_is_broken(tmp_path):
    path = tmp_path / 'h.json'
    path.write_bytes('[{"input": "Ж"}]'.encode('cp1251'))
    errors = []
    assert HistoryStore(str(path)).load(errors.append) == []
    assert len(errors) == 1 and (tmp_path / 'h.json.broken').read_bytes() == path.read_bytes()


def test_load_unreadable_existing_history_raises(tmp_path):
    # the path exists but cannot be read (a directory is deterministic on Windows and POSIX):
    # returning [] would let the next append replace the user's real history
    errors = []
    with pytest.raises(OSError):
        HistoryStore(str(tmp_path)).load(on_error=errors.append)
    assert errors == [] and not os.path.exists(str(tmp_path) + '.broken')


def test_append_to_unreadable_existing_history_raises_and_changes_nothing(tmp_path):
    target = tmp_path / 'h.json'
    target.mkdir()
    with pytest.raises(OSError):
        HistoryStore(str(target)).append({'n': 1})
    assert os.listdir(tmp_path) == ['h.json'] and os.listdir(target) == []


def test_damaged_history_kept_as_broken_copy(tmp_path):
    path = tmp_path / 'h.json'
    path.write_bytes(b'[{"ts": "2026-01-01 10:00", "input": "a.fasta"}, {oops')
    errors = []
    store = HistoryStore(str(path))
    assert store.load(on_error=errors.append) == []
    assert path.read_bytes().endswith(b'{oops')      # load alone does not rewrite the damaged file
    store.append({'n': 1})                           # append loads first: the raw bytes survive
    broken = tmp_path / 'h.json.broken'
    assert broken.read_bytes() == b'[{"ts": "2026-01-01 10:00", "input": "a.fasta"}, {oops'
    assert store.load() == [{'n': 1}]                # and the history file is healthy again
    assert sorted(os.listdir(tmp_path)) == ['h.json', 'h.json.broken']


def test_append_roundtrips_readable_utf8_indent_2(tmp_path):
    path = tmp_path / 'h.json'
    store = HistoryStore(str(path))
    rec = _rec(1)
    store.append(rec)
    assert store.load() == [rec]
    text = path.read_text('utf-8')
    assert 'данные' in text and '\\u' not in text      # ensure_ascii=False
    assert text.startswith('[\n  {\n    "ts"')           # indent=2, like the files written so far
    assert os.listdir(tmp_path) == ['h.json']          # no temp file left behind


def test_append_propagates_oserror(tmp_path):
    store = HistoryStore(str(tmp_path / 'no such folder' / 'h.json'))
    with pytest.raises(OSError):
        store.append({'n': 1})
    assert os.listdir(tmp_path) == []


def test_append_failure_keeps_previous_history(tmp_path):
    path = tmp_path / 'h.json'
    store = HistoryStore(str(path))
    store.append({'n': 1})
    with pytest.raises(TypeError):
        store.append({'bad': object()})               # not JSON-serialisable
    assert json.loads(path.read_text('utf-8')) == [{'n': 1}]
    assert os.listdir(tmp_path) == ['h.json']


def test_get_returns_record_or_none(tmp_path):
    store = HistoryStore(str(tmp_path / 'h.json'))
    assert store.get(0) is None                       # no file yet
    store.append({'n': 1})
    store.append({'n': 2})
    assert store.get(0) == {'n': 2} and store.get(1) == {'n': 1}
    assert store.get(2) is None and store.get(-1) is None


def test_new_record_counts_ok_and_n():
    files = [
        {'file': 'a.fasta', 'status': 'ok', 'tree': 'a.txt', 'stats': {'lnl': -1.5}, 'error': ''},
        {'file': 'b.fasta', 'status': 'error', 'tree': '', 'stats': {}, 'error': 'boom'},
        {'file': 'c.fasta', 'status': 'ok', 'tree': 'c.txt', 'stats': {}, 'error': ''},
    ]
    params = {'model': 'GTR', 'engine': 'iqtree'}
    rec = history.new_record(inputs=['D:/data'], engine='iqtree', params=params, files=files,
                             duration_s=12.5, ts=datetime(2026, 3, 7, 9, 4))
    assert set(rec) == {'ts', 'inputs', 'engine', 'params', 'files', 'ok', 'n', 'duration_s'}
    assert rec['ts'] == '2026-03-07 09:04'
    assert rec['inputs'] == ['D:/data'] and rec['engine'] == 'iqtree'
    assert rec['params'] == params and rec['files'] == files
    assert rec['ok'] == 2 and rec['n'] == 3 and rec['duration_s'] == 12.5
    json.dumps(rec)                                   # JSON-serialisable as is


def test_new_record_does_not_alias_its_arguments():
    inputs, params, files = ['a.fasta'], {'model': 'GTR'}, [{'file': 'a.fasta', 'status': 'ok'}]
    rec = history.new_record(inputs=inputs, engine='phyml', params=params, files=files, duration_s=0.0)
    inputs.append('b.fasta')
    params['model'] = 'JC69'
    files[0]['status'] = 'error'
    assert rec['inputs'] == ['a.fasta'] and rec['params'] == {'model': 'GTR'}
    assert rec['files'][0]['status'] == 'ok' and rec['ok'] == 1


def test_new_record_timestamp_defaults_to_now():
    before = datetime.now().replace(second=0, microsecond=0)
    rec = history.new_record(inputs=[], engine='phyml', params={}, files=[], duration_s=0.0)
    stamp = datetime.strptime(rec['ts'], '%Y-%m-%d %H:%M')
    assert before <= stamp <= datetime.now()
    assert rec['ok'] == 0 and rec['n'] == 0


def test_old_record_display_and_tree():
    old = {'ts': '2025-05-01 10:00', 'input': 'a.fasta', 'ok': 1, 'n': 1, 'time': '30s',
           'model': 'GTR', 'engine': 'phyml', 'tree': 'x.txt'}
    assert history.display_input(old) == 'a.fasta'
    assert history.best_tree(old) == 'x.txt'
    assert history.display_input({}) == '' and history.best_tree({}) == ''
    assert history.best_tree({'input': 'a.fasta', 'tree': None}) == ''


def test_new_record_display_input_file_folder_and_batch(tmp_path):
    folder = tmp_path / 'Мои данные'
    folder.mkdir()
    single = str(folder / 'a.fasta')
    assert history.display_input({'inputs': [single]}) == 'a.fasta'
    assert history.display_input({'inputs': [str(folder)]}) == 'Мои данные/'
    assert history.display_input({'inputs': [str(folder) + os.sep]}) == 'Мои данные/'
    batch = [str(folder / 'a.fasta'), str(folder / 'b.fasta'), str(folder / 'c.fasta')]
    assert history.display_input({'inputs': batch}) == 'Мои данные/'
    assert history.display_input({'inputs': []}) == ''


def test_display_input_of_files_without_a_common_folder_falls_back_to_the_first_name():
    # relative names have no common parent folder to show
    assert history.display_input({'inputs': ['a.fasta', 'b.fasta']}) == 'a.fasta'


def test_new_record_best_tree_is_last_ok():
    rec = {'files': [
        {'file': 'a', 'status': 'ok', 'tree': 'a.txt'},
        {'file': 'b', 'status': 'ok', 'tree': 'b.txt'},
        {'file': 'c', 'status': 'error', 'tree': ''},
    ]}
    assert history.best_tree(rec) == 'b.txt'
    assert history.best_tree({'files': [{'file': 'c', 'status': 'error', 'tree': 't.txt'}]}) == ''
    assert history.best_tree({'files': []}) == ''
    assert history.best_tree({'files': [{'file': 'a', 'status': 'ok'}]}) == ''   # no tree recorded


def test_mixed_old_and_new_records_survive_append(tmp_path):
    path = tmp_path / 'h.json'
    old = {'ts': '2025-05-01 10:00', 'input': 'a.fasta', 'ok': 1, 'n': 1, 'time': '30s',
           'model': 'GTR', 'engine': 'phyml', 'tree': 'x.txt'}
    path.write_text(json.dumps([old], indent=2), 'utf-8')       # a history written before this version
    store = HistoryStore(str(path))
    new = _rec(2)
    store.append(new)
    assert store.load() == [new, old]
    assert history.display_input(store.get(1)) == 'a.fasta'


def test_err_history_broken_is_localised_with_a_placeholder():
    for lang in ('en', 'ru'):
        assert '{}' in STRINGS[lang]['err_history_broken']
    assert STRINGS['en']['err_history_broken'] == '[ERROR] Run history file is damaged and was ignored: {}'
    assert STRINGS['ru']['err_history_broken'] == '[ОШИБКА] Файл истории запусков повреждён и пропущен: {}'
