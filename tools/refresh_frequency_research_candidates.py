"""Update reviewed candidate text/manifests only. No hardware tools or tests."""
import difflib
import hashlib
import json
import shutil
from pathlib import Path
import prepare_frequency_research_candidates as preparation

BASE = Path('F:/CPU2026CourseRuns/current_adopted_20261003/source')
OUT = Path('F:/CPU2026Candidates/frequency_research_20261003')


def main():
    for directory in sorted(OUT.iterdir()):
        if not directory.is_dir():
            continue
        manifest_path = directory / 'candidate.json'
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if directory.name.startswith(('B_', 'C_')):
            path = directory / 'rtl/backend/rv32_backend_joint.v'
            text = path.read_text(encoding='utf-8')
            start = text.index('    // Keep producer positions fixed.')
            end = text.index('    always @(posedge clk_i) begin', start)
            text = text[:start] + text[start:end].replace('recovery_domains[5]', 'recovery_domains[6]') + text[end:]
            path.write_text(text, encoding='utf-8', newline='\n')
        if directory.name.startswith('C_'):
            path = directory / 'rtl/rv32m_multiplier.v'
            text = preparation.pipelined_multiplier((BASE / 'rtl/rv32m_multiplier.v').read_text(encoding='utf-8'))
            path.write_text(text, encoding='utf-8', newline='\n')
        if directory.name.startswith(('B_', 'C_')):
            for name, width, raw in [('rtl/cpu_core.v', 'LANES', 'selected_local'),
                                      ('rtl/frontend/rv32_fetch_frontend.v', 'FE_WIDTH', 'granted_local')]:
                path = directory / name
                text = path.read_text(encoding='utf-8')
                declaration = '    reg [WIDTH-1:0] next_data;' if width == 'LANES' else '    reg [WIDTH-1:0] packet;'
                if 'write_enable_tree (' not in text:
                    text = text.replace(declaration, f'''    wire write_local;
    rv32_frequency_control_tree #(.LEAVES(1)) write_enable_tree (
        .signal_i(|{raw}),.views_o(write_local));
''' + declaration, 1)
                    text = text.replace(f'if(|{raw}) data_o<=', 'if(write_local) data_o<=', 1)
                path.write_text(text, encoding='utf-8', newline='\n')
        diffs = []
        for name in manifest['changed_files']:
            diffs.extend(difflib.unified_diff((BASE / name).read_text(encoding='utf-8').splitlines(keepends=True),
                                            (directory / name).read_text(encoding='utf-8').splitlines(keepends=True),
                                            fromfile='measured/' + name, tofile=directory.name + '/' + name))
        for name in manifest['source_sha256']:
            if name not in manifest['changed_files']:
                shutil.copyfile(BASE / name, directory / name)
            manifest['source_sha256'][name] = hashlib.sha256((directory / name).read_bytes()).hexdigest()
        manifest['preparation_script_sha256'] = hashlib.sha256(Path(__file__).with_name('prepare_frequency_research_candidates.py').read_bytes()).hexdigest()
        manifest['source_review'] = 'Manually inspected validity ownership, domain connections, signed-product identity and stalled-stage behavior; no tools run'
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        (directory / 'review.patch').write_text(''.join(diffs), encoding='utf-8')
        print(directory.name, manifest['status'])


if __name__ == '__main__':
    main()
