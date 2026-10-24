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
    assert history.display_input(rec) == 'data/'      # one input, other paths in files: a folder


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


def _entry(path, status='ok'):
    return {'file': path, 'status': status, 'tree': '', 'stats': {}, 'error': ''}


def test_new_record_display_input_file_folder_and_batch(tmp_path):
    # nothing here exists on disk: the label comes from the record alone
    folder = tmp_path / 'Мои данные'
    single = str(folder / 'a.fasta')
    assert history.display_input({'inputs': [single], 'files': [_entry(single)]}) == 'a.fasta'
    inside = [_entry(str(folder / 'a.fasta')), _entry(str(folder / 'b.fasta'))]
    assert history.display_input({'inputs': [str(folder)], 'files': inside}) == 'Мои данные/'
    assert history.display_input({'inputs': [str(folder) + os.sep], 'files': inside}) == 'Мои данные/'
    batch = [str(folder / 'a.fasta'), str(folder / 'b.fasta'), str(folder / 'c.fasta')]
    assert history.display_input({'inputs': batch, 'files': [_entry(p) for p in batch]}) == 'Мои данные/'
    assert history.display_input({'inputs': []}) == ''
    assert history.display_input({'inputs': ['']}) == ''


def test_single_input_is_a_file_when_its_only_file_entry_is_that_path(tmp_path):
    single = str(tmp_path / 'a.fasta')
    assert history.display_input({'inputs': [single], 'files': [_entry(single)]}) == 'a.fasta'
    # the same path spelled differently (case on Windows, bare file name), or a failed file
    assert history.display_input({'inputs': [single], 'files': [_entry(os.path.normcase(single))]}) == 'a.fasta'
    assert history.display_input({'inputs': [single], 'files': [_entry('a.fasta')]}) == 'a.fasta'
    assert history.display_input({'inputs': [single], 'files': [_entry(single, 'error')]}) == 'a.fasta'


def test_single_input_is_a_folder_when_its_file_entries_are_other_paths(tmp_path):
    folder = str(tmp_path / 'set')
    files = [_entry(os.path.join(folder, 'a.fasta')), _entry(os.path.join(folder, 'b.fasta'))]
    assert history.display_input({'inputs': [folder], 'files': files}) == 'set/'
    assert history.display_input({'inputs': [folder], 'files': files[:1]}) == 'set/'    # one file inside
    assert history.display_input({'inputs': [folder], 'files': [_entry('a.fasta')]}) == 'set/'


def test_single_input_without_file_entries_shows_the_plain_name(tmp_path):
    # no evidence of a folder: the name is shown as it is
    path = str(tmp_path / 'set')
    assert history.display_input({'inputs': [path]}) == 'set'
    assert history.display_input({'inputs': [path], 'files': []}) == 'set'


class _NoFilesystem:
    """Stands in for the os module inside phyml_core.history: pure path functions work,
    everything that asks the filesystem fails the test."""
    _FORBIDDEN = {'isdir', 'isfile', 'exists', 'lexists', 'islink', 'ismount', 'realpath', 'abspath',
                  'getsize', 'samefile', 'stat', 'lstat', 'listdir', 'scandir', 'getcwd'}

    def __init__(self, real):
        self._real = real

    def __getattr__(self, name):
        if name in self._FORBIDDEN:
            raise AssertionError(f'display_input must not query the filesystem ({name})')
        return _NoFilesystem(getattr(self._real, name)) if name == 'path' else getattr(self._real, name)


def test_display_input_does_not_touch_the_filesystem(tmp_path, monkeypatch):
    folder = tmp_path / 'set'
    folder.mkdir()                                    # it exists, yet display_input must not ask
    files = [_entry(str(folder / 'a.fasta')), _entry(str(folder / 'b.fasta'))]
    monkeypatch.setattr(history, 'os', _NoFilesystem(os))
    with pytest.raises(AssertionError):               # the guard itself works
        history.os.path.isdir(str(folder))
    assert history.display_input({'inputs': [str(folder)], 'files': files}) == 'set/'
    assert history.display_input({'inputs': [files[0]['file']], 'files': files[:1]}) == 'a.fasta'
    assert history.display_input({'inputs': [e['file'] for e in files], 'files': files}) == 'set/'
    assert history.display_input({'input': 'old.fasta'}) == 'old.fasta'


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


def test_load_drops_non_dict_entries_and_keeps_broken_copy(tmp_path):
    path = tmp_path / 'h.json'
    valid = {'ts': '2026-01-01 10:00', 'input': 'a.fasta', 'ok': 1, 'n': 1, 'tree': 'x.txt'}
    raw = json.dumps([1, 'x', None, valid, [2], True]).encode('utf-8')
    path.write_bytes(raw)
    errors = []
    store = HistoryStore(str(path))
    assert store.load(on_error=errors.append) == [valid]       # the good history is not thrown away
    assert errors == [_t('err_history_broken').format(str(path))]
    assert (tmp_path / 'h.json.broken').read_bytes() == raw
    assert path.read_bytes() == raw                             # load alone does not rewrite the file
    assert store.get(0) == valid and store.get(1) is None       # indexes follow the cleaned list


def test_load_list_without_any_dict_is_empty_and_broken(tmp_path):
    path = tmp_path / 'h.json'
    path.write_text('[1, "x"]', 'utf-8')
    errors = []
    assert HistoryStore(str(path)).load(errors.append) == []
    assert len(errors) == 1 and (tmp_path / 'h.json.broken').read_text('utf-8') == '[1, "x"]'


def test_load_clean_list_is_not_reported(tmp_path):
    path = tmp_path / 'h.json'
    path.write_text('[{"n": 1}, {"n": 2}]', 'utf-8')
    errors = []
    assert HistoryStore(str(path)).load(errors.append) == [{'n': 1}, {'n': 2}]
    assert errors == [] and not (tmp_path / 'h.json.broken').exists()


def test_append_after_non_dict_entries_keeps_the_valid_ones_and_the_original_bytes(tmp_path):
    path = tmp_path / 'h.json'
    raw = b'[1, {"n": 1}, "x"]'
    path.write_bytes(raw)
    store = HistoryStore(str(path))
    store.append({'n': 2})
    assert store.load() == [{'n': 2}, {'n': 1}]                 # junk is gone from the live file
    assert (tmp_path / 'h.json.broken').read_bytes() == raw     # but kept in the copy


@pytest.mark.parametrize('rec', [
    {'files': None}, {'files': [None]}, {'files': 'abc'}, {'files': 7}, {'files': [1, 'x', []]},
    {'files': {'file': 'a'}}, {'inputs': 'abc'}, {'inputs': None}, {'inputs': 5}, {'inputs': [None, 5]},
    {'inputs': {'a': 1}}, {'input': None}, {'input': 5}, {'input': ['a']}, {'tree': None}, {'tree': 7},
    {'files': [{'status': 'ok', 'tree': None}]}, {'files': [{'status': 'ok', 'tree': 3}]},
    {'files': [{'status': 'ok', 'tree': ['t']}]}, {'files': [{'status': ['ok']}]}, {},
    {'inputs': ['a.fasta'], 'files': [None, 5, {'file': None}]},
])
def test_helpers_tolerate_malformed_records(rec):
    assert isinstance(history.display_input(rec), str)
    assert isinstance(history.best_tree(rec), str)


def test_malformed_new_style_fields_fall_back_to_the_old_record_keys():
    rec = {'inputs': 'abc', 'files': None, 'input': 'old.fasta', 'tree': 'x.txt'}
    assert history.display_input(rec) == 'old.fasta'
    assert history.best_tree(rec) == 'x.txt'
    assert history.display_input({'inputs': None, 'input': None}) == ''
    assert history.best_tree({'files': 'abc', 'tree': None}) == ''


def test_malformed_items_inside_lists_are_skipped():
    rec = {'inputs': [None, 'D:/data/a.fasta', 5],
           'files': [None, {'status': 'ok', 'tree': 't.txt'}, 'x', 3, {'status': 'error', 'tree': 'bad.txt'}]}
    assert history.display_input(rec) == 'a.fasta'
    assert history.best_tree(rec) == 't.txt'
