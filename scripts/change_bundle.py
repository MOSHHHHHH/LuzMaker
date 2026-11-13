"""Validate and transfer state + website output as one immutable release asset."""
import gzip
import hashlib
import json
import shutil
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path


def validate(root):
    index=json.loads((root/'changes/index.json').read_text())
    assert index['version']==2 and index['start']<=index['end'] and index['stats']['trips']>0
    files=list((root/'changes/stations').glob('*.json'))
    assert len(files)==index['stations']
    count=0
    for p in files:
        data=json.loads(p.read_text())
        assert p.stem==hashlib.sha256(data['station'].encode()).hexdigest()[:20]
        for e in data['changes']:
            assert index['start']<=e['date']<=index['end'] and e['id'] and e['detectedAt']
            count+=1
    assert count==index['stats']['events']
    with tempfile.TemporaryDirectory() as tmp:
        db_path=Path(tmp)/'state.db'
        with gzip.open(root/'state.sqlite.gz','rb') as src,db_path.open('wb') as dst:
            shutil.copyfileobj(src,dst)
        with sqlite3.connect(db_path) as db:
            assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
            assert db.execute('SELECT count(*) FROM snapshots').fetchone()[0]>0
            assert db.execute('SELECT count(*) FROM events').fetchone()[0]==count
    return index


def main():
    operation, source, destination=sys.argv[1:]
    source,destination=Path(source),Path(destination)
    if operation=='bundle':
        validate(source)
        with zipfile.ZipFile(destination,'w',compression=zipfile.ZIP_DEFLATED) as z:
            for p in [source/'state.sqlite.gz',*sorted((source/'changes').rglob('*.json'))]:
                z.write(p,p.relative_to(source))
    elif operation=='restore':
        with zipfile.ZipFile(source) as z:
            for info in z.infolist():
                p=Path(info.filename)
                if p.is_absolute() or '..' in p.parts or not (info.filename=='state.sqlite.gz' or info.filename.startswith('changes/')):
                    raise ValueError('Unsafe bundle path')
            z.extractall(destination)
        validate(destination)
    else:
        raise ValueError('Unknown operation')

if __name__=='__main__':
    main()
