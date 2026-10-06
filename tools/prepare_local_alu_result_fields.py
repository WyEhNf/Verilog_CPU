"""Move ALU result acceptance, reset and hold decisions beside real field FFs."""
from pathlib import Path
import hashlib,json,re,shutil

BASE=Path('F:/CPU2026Candidates/completion_rank_v8_20261003')
STAGE=Path('F:/CPU2026Candidates/local_alu_fields_v10_20261003')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()

FIELD=r'''
// This bank owns real result bits and their original acceptance priority.
// Ready/valid/reset decisions are evaluated locally, so the central result
// enable does not directly drive the muxes of every execution payload bit.
(* keep_hierarchy = 1 *)
module rv32_alu_result_field #(parameter integer WIDTH=16, SHIFT_VALUE=0, RESET_VALUE=0) (
    input wire clk_i,reset_i,flush_i,
    input wire result_valid_i,ready_i,stale_i,shift_busy_i,issue_valid_i,
    input wire [WIDTH-1:0] data_i,shift_data_i,
    output reg [WIDTH-1:0] data_o
);
    wire slot_accepts=!shift_busy_i && (!result_valid_i || ready_i || stale_i);
    wire cancel_pending=result_valid_i && stale_i && !ready_i;
    always @(posedge clk_i) begin
        if(reset_i || flush_i) data_o<=RESET_VALUE;
        else if(shift_busy_i) begin
            if(SHIFT_VALUE && !stale_i) data_o<=shift_data_i;
        end else if(!cancel_pending && slot_accepts && issue_valid_i) data_o<=data_i;
    end
endmodule
'''

def bank(name,width,value,indent='    ',shift=False):
    controls=r'''.clk_i(clk_i),.reset_i(reset_i),.flush_i(flush_i),
            .result_valid_i(result_valid_reg),.ready_i(exec_ready_i),
            .stale_i(result_is_stale),.shift_busy_i(shift_busy),.issue_valid_i(issue_valid_i),'''
    if width in ('1','2','4'):
        reset=',.RESET_VALUE(`RV32IM_MEM_NONE)' if name=='result_mem_size_reg' else ''
        return indent+f'rv32_alu_result_field #(.WIDTH({width}){reset}) {name}_owner (\n'+indent+controls+'\n'+indent+f'    .data_i({value}),.shift_data_i({width}\'b0),.data_o({name}));\n'
    data=f'{name}_input';word=f'{name}_word'
    return f'''
{indent}wire [{width}-1:0] {data}={value};
{indent}genvar {word};
{indent}generate for({word}=0;{word}<({width}+15)/16;{word}={word}+1) begin:g_{name}_word
{indent}    localparam integer W=({width}-{word}*16<16)?{width}-{word}*16:16;
{indent}    rv32_alu_result_field #(.WIDTH(W),.SHIFT_VALUE({int(shift)})) bank (
{indent}        {controls}
{indent}        .data_i({data}[{word}*16 +: W]),
{indent}        .shift_data_i({'shifted_result_word['+word+'*16 +: W]' if shift else '{W{1\'b0}}'}),
{indent}        .data_o({name}[{word}*16 +: W]));
{indent}end endgenerate
'''

def transform(text):
    fields={
        'result_value_reg':('32','calc_value'),
        'result_phys_rd_reg':('PHYS_ADDR_WIDTH','issue_phys_rd_i'),
        'result_rob_tag_reg':('TAG_WIDTH','issue_rob_tag_i'),
        'result_epoch_reg':('EPOCH_WIDTH','issue_epoch_i'),
        'result_rd_we_reg':('1','calc_rd_we'),
        'result_is_branch_reg':('1','calc_is_branch'),
        'result_branch_taken_reg':('1','calc_branch_taken'),
        'result_branch_target_reg':('32','calc_branch_target'),
        'result_redirect_valid_reg':('1','calc_redirect_valid'),
        'result_redirect_pc_reg':('32','calc_redirect_pc'),
        'result_is_memory_reg':('1','calc_is_memory'),
        'result_is_load_reg':('1','calc_is_load'),
        'result_is_store_reg':('1','calc_is_store'),
        'result_mem_addr_reg':('32','calc_mem_addr'),
        'result_mem_size_reg':('2','calc_mem_size'),
        'result_mem_unsigned_reg':('1','calc_mem_unsigned'),
        'result_store_data_reg':('32','calc_store_data'),
    }
    for name in fields:
        pattern=r'\breg(\s+(?:\[[^\n]+?\]\s+)?)'+name+r'\s*;'
        text,n=re.subn(pattern,r'wire\1'+name+';',text)
        assert n==1,name
    start=text.index('    always @(posedge clk_i) begin\n        if (reset_i || flush_i) begin\n            result_valid_reg')
    before,scalar=text[:start],text[start:]
    for name in fields:
        scalar,n=re.subn(r'\b'+name+r'\s*<=\s*[^;]*;', ';',scalar)
        assert n>=2,name
    banks=r'''
    wire result_is_stale=live_tag_valid_i && result_rob_tag_reg!=live_tag_i;
    wire [31:0] shifted_result_word=shift_right?
        {(shift_arithmetic && result_value_reg[31]),result_value_reg[31:1]}:
        {result_value_reg[30:0],1'b0};
'''+''.join(bank(n,w,v,shift=n=='result_value_reg') for n,(w,v) in fields.items())
    text=before+banks+'\n'+scalar
    # Forwarded prediction fields use exactly the same acceptance priority.
    start=text.index('        always @(posedge clk_i) begin\n            if (reset_i || flush_i) begin\n                source_pc_reg')
    stop=text.index('    end else begin : g_no_forward_metadata',start)
    text=text[:start]+''.join(bank(n,w,v,'        ').replace('generate for','for').replace('end endgenerate','end') for n,w,v in [
        ('source_pc_reg','32','issue_pc_i'),('pred_target_reg','32','issue_pred_target_i'),
        ('pred_taken_reg','1','issue_pred_taken_i'),('pred_kind_reg','2','issue_pred_kind_i')])+text[stop:]
    text=text.replace('        reg [31:0] source_pc_reg, pred_target_reg;',
        '        wire [31:0] source_pc_reg, pred_target_reg;')
    text=text.replace('        reg pred_taken_reg;','        wire pred_taken_reg;')
    text=text.replace('        reg [1:0] pred_kind_reg;','        wire [1:0] pred_kind_reg;')
    return text+FIELD

def main():
    assert not STAGE.exists(),'Preserve previous candidates'
    manifest=json.loads((BASE/'candidate.json').read_text(encoding='utf-8'))
    STAGE.mkdir(parents=True)
    for n,h in manifest['source_sha256'].items():
        assert sha(BASE/n)==h.lower(),n
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(BASE/n,p)
    name='rtl/rv32i_alu.v';p=STAGE/name
    p.write_text(transform(p.read_text(encoding='utf-8')),encoding='utf-8')
    # Free-lane ranks must represent CDB_WIDTH even when SOURCES<CDB_WIDTH.
    name2='rtl/backend/rv32_completion_network.v';p=STAGE/name2;text=p.read_text(encoding='utf-8')
    old='localparam integer RANK_WIDTH=(SOURCES<=1)?1:$clog2(SOURCES+1);'
    assert text.count(old)==1
    text=text.replace(old,'localparam integer RANK_WIDTH=($clog2(SOURCES+1)>$clog2(CDB_WIDTH+1))?\n        $clog2(SOURCES+1):$clog2(CDB_WIDTH+1);')
    p.write_text(text,encoding='utf-8')
    manifest['changed'].append(dict(file=name,change='Local real ALU result fields reproduce acceptance/shift/reset priorities without new cycles'))
    manifest.update(source_root=str(STAGE),parent_candidate=str(BASE/'candidate.json'),
        source_sha256={n:sha(STAGE/n) for n in manifest['source_sha256']},tool_sha256=sha(__file__),
        strategy=manifest['strategy']+'; local 16-bit ALU result fields evaluate transaction/reset/shift priority beside their FFs')
    (STAGE/'candidate.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=manifest['status'],source_root=str(STAGE),no_simulation_run=True)))

if __name__=='__main__':main()
