"""Fetch real mammalian mitochondrial CytB sequences from NCBI.

Downloads complete mitochondrial genomes via E-utilities (one request),
extracts the cytochrome-b CDS from each and writes a FASTA file used by
the t9 'real data' test scenario. The result is cached: if the output
already exists the network is not touched, so tests run offline too.

Species set has a well-known phylogeny:
  Hominidae: human, chimp, bonobo, gorilla, orangutan
  Cercopithecidae: macaque (outgroup inside primates)
  Rodentia: mouse, rat (outgroup to primates)
"""
import io
import os
import sys
import urllib.request

from Bio import SeqIO

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RUN = os.path.join(ROOT, 'testrun')
os.makedirs(RUN, exist_ok=True)
OUT_DIR = os.path.join(RUN, 'real')
OUT_FA = os.path.join(OUT_DIR, 'cytb_mammals.fasta')

# stable RefSeq master records for complete mitochondrial genomes
ACCESSIONS = {
    'NC_012920': 'Homo_sapiens',
    'NC_001643': 'Pan_troglodytes',
    'NC_001644': 'Pan_paniscus',
    'NC_011120': 'Gorilla_gorilla',
    'NC_002083': 'Pongo_pygmaeus',
    'NC_005943': 'Macaca_mulatta',
    'NC_005089': 'Mus_musculus',
    'NC_001665': 'Rattus_norvegicus',
}


def fetch():
    ids = ','.join(ACCESSIONS)
    url = (f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi'
           f'?db=nucleotide&id={ids}&rettype=gb&retmode=text')
    req = urllib.request.Request(url, headers={'User-Agent': 'phymlGUI-testsuite/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode('utf-8', errors='replace')


def extract_cytb(genbank_text):
    out = []
    for rec in SeqIO.parse(io.StringIO(genbank_text), 'genbank'):
        name = ACCESSIONS.get(rec.id.split('.')[0], rec.id)
        hit = None
        for f in rec.features:
            if f.type != 'CDS':
                continue
            gene = (f.qualifiers.get('gene') or [''])[0].lower()
            product = (f.qualifiers.get('product') or [''])[0].lower()
            if gene in ('cytb', 'cyb') or 'cytochrome b' in product:
                hit = f
                break
        if hit is None:
            print(f'WARN: no CytB CDS found in {rec.id} ({name})')
            continue
        seq = hit.extract(rec.seq)
        seq = str(seq).rstrip('*')  # drop terminal stop codon if annotated
        out.append((name, seq))
        print(f'{rec.id:12s} {name:20s} CytB {len(seq)} bp')
    return out


def main():
    if os.path.exists(OUT_FA):
        n = sum(1 for _ in SeqIO.parse(OUT_FA, 'fasta'))
        print(f'cached: {OUT_FA} ({n} records), skipping download')
        return 0
    records = extract_cytb(fetch())
    if len(records) < len(ACCESSIONS):
        print(f'ERROR: got {len(records)}/{len(ACCESSIONS)} records', file=sys.stderr)
        return 1
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_FA, 'w') as f:
        for name, seq in records:
            f.write(f'>{name}\n{seq}\n')
    print(f'written: {OUT_FA}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
