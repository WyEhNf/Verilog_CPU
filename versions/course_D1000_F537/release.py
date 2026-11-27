"""Verify or extract the exact measured netlist, without local experiment paths."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil

VERSION=Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def verify():
    manifest=json.loads((VERSION/'manifest.json').read_text(encoding='utf-8'))
    for name,expected in manifest['files_sha256'].items():
        path=VERSION/name
        if not path.is_file() or sha(path)!=expected:
            raise ValueError('Release file missing or changed: '+name)
    with gzip.open(VERSION/'netlist/mapped.v.gz','rb') as stream:
        actual=hashlib.file_digest(stream,'sha256').hexdigest()
    if actual!=manifest['mapped_netlist_sha256']:
        raise ValueError('Uncompressed netlist differs from the measured version')
    return manifest


def materialize(out):
    manifest=verify()
    # Never replace another run's source files or compiled simulator.
    out.mkdir(parents=True,exist_ok=False)
    with gzip.open(VERSION/'netlist/mapped.v.gz','rb') as source:
        with (out/'mapped.v').open('wb') as dest:
            shutil.copyfileobj(source,dest)
    for name in ('cells.v','macros.v'):
        shutil.copyfile(VERSION/'simulation'/name,out/name)
    (out/'filelist.f').write_text('mapped.v\ncells.v\nmacros.v\n',encoding='utf-8')
    if sha(out/'mapped.v')!=manifest['mapped_netlist_sha256']:
        raise ValueError('Extracted netlist hash mismatch')
    (out/'release_identity.json').write_text(json.dumps(dict(name=manifest['name'],
        release_manifest_sha256=sha(VERSION/'manifest.json'),
        mapped_netlist_sha256=manifest['mapped_netlist_sha256']),indent=2)+'\n',encoding='utf-8')
    print('EXTRACTED '+str(out))
    print('Build with the frozen official framework:')
    print('python "'+str(VERSION/'framework/scripts/build.py')+'" --filelist "'+str(out/'filelist.f')+
          '" --out "'+str(out/'build')+'"')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['verify','materialize'])
    parser.add_argument('--out',type=Path)
    args=parser.parse_args()
    if args.action=='verify':
        result=verify();print('VERIFIED '+result['name']+' '+result['mapped_netlist_sha256'])
    else:
        if args.out is None:parser.error('materialize requires --out')
        materialize(args.out.resolve())


if __name__=='__main__':main()
