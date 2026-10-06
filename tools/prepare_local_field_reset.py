"""Let real RS/LSQ field banks enforce reset beside their own FFs."""
from pathlib import Path
import hashlib,json,re,shutil

BASE=Path('F:/CPU2026Candidates/local_transactions_v11_20261003')
STAGE=Path('F:/CPU2026Candidates/local_field_controls_v12_20261003')
REFERENCE=Path('F:/CPU2026Candidates/frequency_combined_v2_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def transform(text,original,module,expected):
    start=original.index('    always @(posedge clk_i) begin')
    block=original[start:]
    end=block.index('        end else if (flush')
    resets={}
    for m in re.finditer(r'\b(\w+_mem)\[(?:slot|reset_slot)\]\s*<=\s*([^;]+);',block[:end]):
        rhs=m[2].strip()
        if rhs in ('0',"1'b0"):resets[m[1]]=0
        elif m[1] in ('generation_mem','generation_next_mem'):
            assert rhs=="{{(GENERATION_WIDTH-1){1'b0}}, 1'b1}",rhs
            resets[m[1]]=1
        else:raise ValueError((m[1],rhs))
    assert resets
    pattern=module+r' #\(\.WIDTH\((.*?)\)\) (\w+_mem)_owner \('
    def instance(m):
        field=m[2]
        return module+f' #(.WIDTH({m[1]}),.RESETTABLE({int(field in resets)}),.RESET_VALUE({resets.get(field,0)})) {field}_owner ('
    text,n=re.subn(pattern,instance,text);assert n==expected,(module,n)
    old='.clk_i(clk_i),.write_i('
    assert text.count(old)==expected
    text=text.replace(old,'.clk_i(clk_i),.reset_i(reset_i),.write_i(')
    old=f'module {module} #(parameter integer WIDTH=32) ('
    assert text.count(old)==1
    text=text.replace(old,f'module {module} #(parameter integer WIDTH=32,RESETTABLE=0,RESET_VALUE=0) (')
    old='    input wire clk_i,write_i,'
    assert text.count(old)==1
    text=text.replace(old,'    input wire clk_i,reset_i,write_i,')
    old='    always @(posedge clk_i) if(write_i) data_o<=data_i;'
    assert text.count(old)==1
    text=text.replace(old,r'''    // A local reset-qualified enable drives this field's hold muxes. The
    // parent write decision reaches one qualification gate per field.
    always @(posedge clk_i) begin
        if(reset_i) begin
            if(RESETTABLE) data_o<=RESET_VALUE;
        end else if(write_i) data_o<=data_i;
    end''')
    return text,resets

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    details=[]
    for name,module,expected in [('rtl/backend/rv32_lsq.v','rv32_lsq_state_word',25),
                                ('rtl/backend/rv32_reservation_station.v','rv32_rs_state_word',15)]:
        p=STAGE/name
        text,resets=transform(p.read_text(encoding='utf-8'),(REFERENCE/name).read_text(encoding='utf-8'),module,expected)
        p.write_text(text,encoding='utf-8');details.append(dict(file=name,reset_values=resets))
    manifest['changed'].extend(dict(file=d['file'],change='Real field bank owns original reset semantics and reset-qualified write enable') for d in details)
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        original_reset_fields=details,strategy=manifest['strategy']+'; field-local reset ownership bounds shared write-decision fanout')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True,reset_fields=details)))

if __name__=='__main__':main()
