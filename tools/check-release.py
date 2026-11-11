"""Verify the deploy artifact and the byte identity of the analysis data."""
import csv
import gzip
import hashlib
import json
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / 'site'
FLOOD = SITE / 'data/processed/flood'

def digest(data):
    return hashlib.sha256(data).hexdigest()

def verify():
    assert (SITE / 'index.html').is_file()
    assert not any(path.is_symlink() for path in SITE.rglob('*')), 'Pages artifact contains symlinks'
    manifest = json.loads((FLOOD / 'manifest.json').read_bytes())
    assert len(manifest['layers']) == 13, 'Incomplete York snapshot'
    for layer, record in manifest['layers'].items():
        packed = SITE / (record['path'] + '.gz')
        assert digest(gzip.decompress(packed.read_bytes())) == record['sha256'], layer
        display = json.loads(gzip.decompress((FLOOD / 'display' / (layer + '.geojson.gz')).read_bytes()))
        assert display['type'] == 'FeatureCollection' and display['features'], layer
    for path in SITE.glob('data/**/*.json'):
        json.loads(path.read_bytes())
    for path in SITE.glob('models/*.json'):
        json.loads(path.read_bytes())
    with (SITE / 'data/reports/epc-subgroups.csv').open(newline='') as handle:
        assert next(csv.DictReader(handle)), 'No EPC subgroup data'
    runtime = SITE / 'runtime'
    for entry in (runtime / 'SHA256SUMS').read_text().splitlines():
        checksum, filename = entry.split(maxsplit=1)
        assert digest((runtime / filename).read_bytes()) == checksum, filename
    print('Verified 13 York layer pairs, static JSON, EPC CSV and pinned runtime hashes.')

if __name__ == '__main__':
    verify()
