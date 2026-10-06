"""Copy a missing OSS tool runtime without changing any frozen CPU inputs.

The destination must be absent. Preserve earlier failed build evidence, verify
all copied runtime files byte for byte, and bind the record to the existing
staging manifest. This only repairs host dependencies, not hardware or scoring.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--stage-root', type=Path, required=True)
    args = parser.parse_args()
    source, stage = args.source_root.resolve(), args.stage_root.resolve()
    rel = Path('.deps/oss-cad-suite-install/oss-cad-suite')
    original, target = source/rel, stage/rel
    manifest_path = stage/'staging_manifest.json'
    manifest_hash = sha(manifest_path)
    manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
    frozen = manifest['staged_sha256'] | manifest['measurement_dependencies_sha256']
    for name, expected in frozen.items():
        assert sha(stage/name) == expected.lower(), name
    assert original.is_dir() and not target.exists(), 'Require missing target runtime'
    assert (original/'bin/verilator_bin.exe').is_file()
    assert (original/'bin/yosys.exe').is_file()
    report_path = stage/'tool_runtime_repair.json'
    assert not report_path.exists(), 'Preserve prior repair evidence'
    files = sorted(p for p in original.rglob('*') if p.is_file())
    assert not any(p.is_symlink() or p.is_junction() for p in original.rglob('*'))
    hashes = {p.relative_to(original).as_posix(): sha(p) for p in files}
    print(f'Copying {len(files)} runtime files', flush=True)
    shutil.copytree(original, target)
    for name, expected in hashes.items():
        assert sha(original/name) == sha(target/name) == expected, name
    for name, expected in frozen.items():
        assert sha(stage/name) == expected.lower(), name
    assert sha(manifest_path) == manifest_hash
    result = dict(status='VERIFIED', source_root=str(source), stage_root=str(stage),
                  runtime_relative_path=rel.as_posix(), file_count=len(files),
                  runtime_sha256=hashes, frozen_inputs_unchanged=True,
                  staging_manifest_sha256=manifest_hash, helper_sha256=sha(Path(__file__)),
                  reason='Missing Verilator/OSS runtime in isolated CPU staging directory',
                  hardware_change=False, previous_failed_build_preserved=True)
    report_path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: result[k] for k in ('status', 'file_count', 'frozen_inputs_unchanged', 'hardware_change')}))


if __name__ == '__main__':
    main()
