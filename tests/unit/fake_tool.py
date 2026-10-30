"""Stand-in for an analysis program or MUSCLE in the runner tests (no real binaries).

    python fake_tool.py MODE ARGS...

Engine modes, ARGS = the PHYLIP file:
  ok      prints a few lines (one with bytes no codec decodes cleanly), writes the tree and
          the stats next to the PHYLIP file, exits 0
  exit3   prints a line and exits with code 3
  notree  exits 0 without writing anything
  hang    starts a child `python -c "import time; time.sleep(60)"` and sleeps itself

MUSCLE modes, ARGS = MUSCLE's options:
  copy    `-align IN -output OUT` (MUSCLE 5): copies IN to OUT, padding the short
          sequences with '-' so the output is aligned; any other syntax exits 1
  v3only  `-in IN -out OUT` (MUSCLE 3) as copy; the MUSCLE 5 syntax exits 1
  hang    as the engine's hang
"""
import subprocess
import sys
import time

# FakeEngine.outputs() in fakes.py uses the same suffixes
TREE_SUFFIX = '_fake_tree.txt'
STATS_SUFFIX = '_fake_stats.txt'

SLEEPER = 'import time; time.sleep(60)'


def say(text):
    sys.stdout.write(text + '\n')
    sys.stdout.flush()


def hang():
    say('fake tool: working')
    subprocess.Popen([sys.executable, '-c', SLEEPER])
    time.sleep(60)
    return 0


def engine_ok(phylip):
    say('fake engine: reading ' + phylip)
    # 0x81 is undefined in cp1252, 0x98 in cp1251, 0xff is never valid UTF-8
    sys.stdout.buffer.write(b'progress \x81\x98\xff\n')
    sys.stdout.flush()
    with open(phylip, encoding='latin-1') as handle:
        ids = [line.split()[0] for line in handle.read().splitlines()[1:] if line.strip()]
    with open(phylip + TREE_SUFFIX, 'w', encoding='utf-8') as handle:
        handle.write('(' + ','.join(ids) + ');\n')
    with open(phylip + STATS_SUFFIX, 'w', encoding='utf-8') as handle:
        handle.write(f'model=FAKE\ntaxa={len(ids)}\nlnL=-123.45\ngamma=0.5\ntstv=2.0\ntime=1s\n')
    say('fake engine: done')
    return 0


def read_fasta(path):
    records, name = [], None
    with open(path, encoding='latin-1') as handle:
        for line in handle.read().splitlines():
            if line.startswith('>'):
                name = line
                records.append([name, ''])
            elif name is not None:
                records[-1][1] += line.strip()
    return records


def muscle(args, source_flag, out_flag):
    if source_flag not in args or out_flag not in args:
        say('fake muscle: unknown syntax ' + ' '.join(args))
        return 1
    source = args[args.index(source_flag) + 1]
    target = args[args.index(out_flag) + 1]
    records = read_fasta(source)
    width = max(len(seq) for _, seq in records)
    with open(target, 'w', encoding='latin-1') as handle:
        for header, seq in records:
            handle.write(f'{header}\n{seq.ljust(width, "-")}\n')
    return 0


def main(argv):
    mode, args = argv[1], argv[2:]
    if mode == 'hang':
        return hang()
    if mode == 'ok':
        return engine_ok(args[0])
    if mode == 'exit3':
        say('fake engine: failing')
        return 3
    if mode == 'notree':
        return 0
    if mode == 'copy':
        return muscle(args, '-align', '-output')
    if mode == 'v3only':
        return muscle(args, '-in', '-out')
    say('fake tool: unknown mode ' + mode)
    return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv))
