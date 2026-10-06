"""Remove discarded-payload recovery controls and localize issue read pointers."""
from pathlib import Path
import hashlib,json,shutil

BASE=Path('F:/CPU2026Candidates/response_fields_v6_20261003')
STAGE=Path('F:/CPU2026Candidates/bounded_controls_v7_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def replace_once(text,old,new):
    assert text.count(old)==1,old
    return text.replace(old,new,1)

def issue(text):
    start=text.index('module rv32_issue_pipeline_slot #(')
    a,b=text[:start],text[start:]
    b=replace_once(b,'    // These banks own the actual payload state and its hold/read muxes.',r'''
    // Each field's read pointer changes at this existing boundary, beside its
    // actual payload storage. The central pointer need not drive every bit mux.
    wire following_read_row = (reset_i || flush_i) ? 1'b0 :
        recovery_i ? (retain0 && retain1 ? read_row : retain1 ? 1'b1 : 1'b0) :
        pop ? !read_row : read_row;
    // These banks own the actual payload state and its hold/read muxes.''')
    b=b.replace('(PAYLOAD_WIDTH+31)/32','(PAYLOAD_WIDTH+15)/16')
    b=b.replace('PAYLOAD_WIDTH-field*32<32)?PAYLOAD_WIDTH-field*32:32','PAYLOAD_WIDTH-field*16<16)?PAYLOAD_WIDTH-field*16:16')
    b=b.replace('field*32 +: WIDTH','field*16 +: WIDTH')
    b=replace_once(b,'.read_row_i(read_row),','.read_row_i(following_read_row),')
    b=replace_once(b,'module rv32_issue_queue_field #(parameter integer WIDTH=32)',
        'module rv32_issue_queue_field #(parameter integer WIDTH=16)')
    b=replace_once(b,'    reg [WIDTH-1:0] row0,row1;','    reg [WIDTH-1:0] row0,row1;\n    reg local_read_row;')
    b=replace_once(b,'    always @(posedge clk_i) begin\n        if (write0_i)',
        '    always @(posedge clk_i) begin\n        local_read_row<=read_row_i;\n        if (write0_i)')
    b=replace_once(b,'    assign data_o=read_row_i?row1:row0;',
        '    assign data_o=local_read_row?row1:row0;')
    return a+b

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    name='rtl/backend/rv32_backend_joint.v';p=STAGE/name
    p.write_text(issue(p.read_text(encoding='utf-8')),encoding='utf-8')
    # Reset/redirect invalidate queue occupancy on the same edge. Payload in
    # discarded rows has no architectural meaning and is overwritten before
    # that row becomes valid again. Only accepted writes update the field.
    name='rtl/cpu_core.v';p=STAGE/name;text=p.read_text(encoding='utf-8')
    text=replace_once(text,r'''        if(reset_i) data_o<=0;
        else if(!flush_i && (|selected)) data_o<=next_data;''',
        r'''        if(|selected) data_o<=next_data;''')
    p.write_text(text,encoding='utf-8')
    name='rtl/frontend/rv32_fetch_frontend.v';p=STAGE/name;text=p.read_text(encoding='utf-8')
    text=replace_once(text,r'''        if(reset_i) data_o<=0;
        else if(!redirect_i && (|selected)) data_o<=packet;''',
        r'''        if(|selected) data_o<=packet;''')
    p.write_text(text,encoding='utf-8')
    name='rtl/backend/rv32_lsq.v';p=STAGE/name;text=p.read_text(encoding='utf-8')
    # Preserve the original tail when recovery encounters no killed entry.
    # In normal operation live entries form a prefix, but do not depend on
    # that invariant when choosing the default recovery tail.
    text=text.replace('recovery_first_killed = recovery_kill_slot_tree[1];',
        'recovery_first_killed = recovery_kill_valid_tree[1] ? recovery_kill_slot_tree[1] : tail_reg;')
    p.write_text(text,encoding='utf-8')
    manifest['changed'].extend([dict(file='rtl/backend/rv32_backend_joint.v',change='Local 16-bit issue fields own read pointers'),
        dict(file='rtl/cpu_core.v',change='Decode occupancy invalidates discarded payload; remove wide reset/flush muxes'),
        dict(file='rtl/frontend/rv32_fetch_frontend.v',change='Fetch occupancy invalidates discarded payload; remove redundant reset/redirect muxes')])
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        strategy=manifest['strategy']+'; bounded issue read controls and validity-only discard for fetch/decode payloads')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
