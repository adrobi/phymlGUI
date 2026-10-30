"""FASTA reading, alignment checks and the FASTA -> PHYLIP conversion (no Qt)."""
import io
import locale
import re

from Bio import AlignIO, SeqIO
from Bio.Align import MultipleSeqAlignment
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord

from .i18n import _t


class AlignmentError(ValueError):
    """A problem with the input sequences; the message is already localized."""


def _parse_fasta(path, encoding):
    with open(path, encoding=encoding) as handle:
        return list(SeqIO.parse(handle, 'fasta'))


def read_fasta(path):
    """Records of a FASTA file; an empty file, or one that is not FASTA, is an AlignmentError.

    The file is opened here (not by SeqIO) so the handle is always closed, a BOM is
    skipped and CRLF line ends are accepted. It is read as UTF-8 first; a file that is not
    valid UTF-8 (ANSI, for example cp1251 headers) is read again with the locale encoding,
    as the old pipeline read every file. When neither decodes it, the AlignmentError
    carries the decoder's message.
    """
    try:
        try:
            records = _parse_fasta(path, 'utf-8-sig')
        except UnicodeDecodeError:
            records = _parse_fasta(path, locale.getpreferredencoding(False))
    except UnicodeDecodeError as e:
        raise AlignmentError(str(e)) from e
    except ValueError as e:
        # Biopython refuses text that comes before the first '>'
        raise AlignmentError(_t('err_empty')) from e
    if not records:
        raise AlignmentError(_t('err_empty'))
    return records


def is_aligned(records):
    """True when all the sequences have the same length."""
    if not records:
        raise AlignmentError(_t('err_empty'))
    first_len = len(records[0].seq)
    return all(len(rec.seq) == first_len for rec in records)


def clean_id(raw):
    """A sequence ID safe for PHYLIP and Newick: the separators become underscores."""
    return re.sub(r'[.|:;(),\s]', '_', raw)


def find_collisions(ids):
    """Cleaned ID -> the original IDs that give it, only where there is more than one.

    Exact duplicates count: ['X', 'X'] gives {'X': ['X', 'X']}.
    """
    groups = {}
    for raw in ids:
        groups.setdefault(clean_id(raw), []).append(raw)
    return {clean: originals for clean, originals in groups.items() if len(originals) > 1}


def write_phylip(records, out_path):
    """Write the records as relaxed PHYLIP: cleaned IDs, '.' gaps turned into '-'.

    The sequences must have the same length (check with is_aligned first). The records
    are not changed. Nothing is written when IDs collide after cleaning, as PhyML and
    IQ-TREE would then merge or reject the taxa. The file is written in the locale
    encoding, as the old conversion did, so the tree files that come back are read the
    same way by the tree viewer; an ID the locale encoding cannot hold is an AlignmentError.
    """
    collisions = find_collisions([rec.id for rec in records])
    if collisions:
        details = '; '.join(f"{', '.join(originals)} → {clean}"
                            for clean, originals in collisions.items())
        raise AlignmentError(_t('err_id_collision').format(details))
    cleaned = []
    for rec in records:
        new_id = clean_id(rec.id)
        cleaned.append(SeqRecord(Seq(str(rec.seq).replace('.', '-')),
                                 id=new_id, name=new_id, description=''))
    buffer = io.StringIO()
    AlignIO.write(MultipleSeqAlignment(cleaned), buffer, 'phylip-relaxed')
    text = buffer.getvalue()
    encoding = locale.getpreferredencoding(False)
    try:
        text.encode(encoding)  # fail before the file is created, not halfway through it
    except UnicodeEncodeError as e:
        raise AlignmentError(str(e)) from e
    with open(out_path, 'w', encoding=encoding) as handle:
        handle.write(text)


def summarize(path):
    """Taxa count, shortest and longest sequence and the share of '-' as a percentage."""
    records = read_fasta(path)
    lengths = [len(rec.seq) for rec in records]
    total = sum(lengths)
    gaps = sum(rec.seq.count('-') for rec in records)
    return {'n': len(records), 'min_len': min(lengths), 'max_len': max(lengths),
            'gap_pct': round(gaps / total * 100, 1) if total else 0}


def aligned_path(fasta):
    """Where MUSCLE puts the alignment of a FASTA file."""
    return fasta.rsplit('.', 1)[0] + '_aligned.fasta'


def phylip_path(fasta):
    """Where the PHYLIP conversion of a FASTA file goes."""
    return fasta.rsplit('.', 1)[0] + '.phy'
