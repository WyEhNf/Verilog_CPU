"""Create a frequency-first candidate: registered credits and real state banks.

No simulation is run here. Frozen adopted sources remain untouched.
"""
from pathlib import Path
import json, re, shutil, hashlib

BASE=Path('F:/CPU2026Integration/frequency_combined_v2_20261003')
SOURCE=Path('F:/CPU2026Candidates/frequency_combined_v2_20261003')
STAGE=Path('F:/CPU2026Candidates/control_islands_v2_20261003')

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def strip_comments(s):
    return re.sub(r'/\*.*?\*/|//[^\n]*','',s,flags=re.S)


class NonblockingStatements:
    """Find NBA statements without consuming relational <= expressions.

    The former broad regex could start at an age comparison in an if guard
    and consume the following assignment. Brackets in a real assignment LHS
    are balanced, and its preceding token must be a statement boundary.
    """
    token = re.compile(r'"(?:\\.|[^"\\])*"|[A-Za-z_$][\w$]*|<=|[^\s]')
    identifier = re.compile(r'[A-Za-z_$][\w$]*\Z')
    boundary = {'begin', 'end', ';', ')', 'else', ':'}

    def finditer(self, source):
        tokens = list(self.token.finditer(source))
        for index, op in enumerate(tokens):
            if op[0] != '<=' or index == 0:
                continue
            left = index - 1
            if tokens[left][0] in {']', '}'}:
                closing = tokens[left][0]
                opening = '[' if closing == ']' else '{'
                level = 1
                left -= 1
                while left >= 0 and level:
                    if tokens[left][0] == closing:
                        level += 1
                    elif tokens[left][0] == opening:
                        level -= 1
                    left -= 1
                if level:
                    raise ValueError('Unbalanced assignment LHS')
                if closing == '}':
                    left += 1
                elif left < 0 or not self.identifier.fullmatch(tokens[left][0]):
                    continue
            elif not self.identifier.fullmatch(tokens[left][0]):
                continue
            if left == 0 or tokens[left - 1][0] not in self.boundary:
                continue
            start = tokens[left].start()
            match = re.match(r'(.+?)\s*<=\s*([^;]*);', source[start:], re.S)
            if not match:
                raise ValueError('Missing assignment terminator')
            yield start, match

    def sub(self, replacement, source):
        edits = [(start, match) for start, match in self.finditer(source)]
        for start, match in reversed(edits):
            source = source[:start] + replacement(match) + source[start + match.end():]
        return source


def bank_arrays(text, depth, bank_module):
    decl=re.compile(r'    reg\s+(\[[^\n]+?\]\s+)?(\w+_mem)\s*\[0:'+depth+r'-1\];')
    fields={m[2]:(m[1] or '').strip() for m in decl.finditer(text)}
    assert fields
    text=decl.sub(lambda m:f'    wire {m[1] or ""}{m[2]} [0:{depth}-1];\n'
        f'    reg {m[1] or ""}{m[2]}_write_data [0:{depth}-1];\n'
        f'    reg {m[2]}_write_enable [0:{depth}-1];',text)
    begin=text.index('    always @(posedge clk_i) begin')
    # The final clocked block is followed by functions (LSQ) or endmodule (RS).
    finish=text.find('\n    function ',begin)
    if finish<0: finish=text.index('\nendmodule',begin)
    block=text[begin:finish]
    clean=strip_comments(block)
    nb=NonblockingStatements()
    assignments=list(nb.finditer(clean))
    assert assignments
    # Per-field write commands reproduce the old last-NBA-wins priority.
    def command(m):
        lhs,rhs=m[1],m[2]
        refs=[]
        for ref in re.finditer(r'\b(\w+_mem)\[',lhs):
            k=ref.end()-1; end=k; level=0
            while end<len(lhs):
                if lhs[end]=='[': level+=1
                elif lhs[end]==']':
                    level-=1
                    if level==0: break
                end+=1
            assert level==0,lhs
            refs.append((ref[1],lhs[k:end+1]))
        if not refs: return ';'
        assert all(n in fields for n,_ in refs),(lhs,fields)
        new_lhs=lhs
        for n in set(n for n,_ in refs): new_lhs=re.sub(r'\b'+n+r'\b',n+'_write_data',new_lhs)
        enables=' '.join(n+'_write_enable'+idx+' = 1\'b1;' for n,idx in refs)
        return 'begin '+new_lhs+' = '+rhs+'; '+enables+' end'
    commands=nb.sub(command,clean)
    assert not list(nb.finditer(commands)), 'An NBA remains in combinational commands'
    # Scratch values belong to this combinational block, not the retained
    # pointer/count process or any existing combinational process.
    vars_assigned=set(re.findall(r'\b(\w+)\s*=(?!=)',commands))
    declarations={}
    for m in re.finditer(r'^    (integer|reg)(?:\s+(\[[^\n]+?\]))?\s+(\w+)\s*;',text,re.M):
        declarations[m[3]]=m[1]+(' '+m[2] if m[2] else '')
    scratch=vars_assigned & declarations.keys()
    for n in scratch: commands=re.sub(r'\b'+n+r'\b','bank_'+n,commands)
    commands=commands.replace('always @(posedge clk_i) begin','always @* begin : g_state_commands',1)
    pos=commands.index('\n')
    defaults='\n'+''.join(f'        {declarations[n]} bank_{n};\n' for n in sorted(scratch))
    defaults+='        integer bank_default_row;\n'
    # Default data is arbitrary when WE=0. Hold muxes stay inside the state owner.
    defaults+=f'        for(bank_default_row=0;bank_default_row<{depth};bank_default_row=bank_default_row+1) begin\n'
    for name in fields:
        defaults+=f"            {name}_write_data[bank_default_row]=0; {name}_write_enable[bank_default_row]=0;\n"
    defaults+='        end\n'
    # Original temporaries can otherwise infer diagnostic latches at inactive paths.
    defaults+=''.join(f'        bank_{n}=0;\n' for n in sorted(scratch))
    commands=commands[:pos]+defaults+commands[pos:]
    def remove_array(m):
        return ';' if any(re.search(r'\b'+n+r'\b',m[1]) for n in fields) else m[0]
    scalar=nb.sub(remove_array,clean)
    # Inspect actual NBA left-hand sides. A broad scan can begin at an array
    # READ in an if condition, cross a newline, and falsely report a later
    # scalar assignment as a remaining array writer.
    remaining=[m[1] for _,m in nb.finditer(scalar)
               if any(re.search(r'\b'+n+r'\[',m[1]) for n in fields)]
    assert not remaining,remaining
    banks='\n    genvar storage_row;\n    generate for(storage_row=0;storage_row<'+depth+';storage_row=storage_row+1) begin:g_state_row\n'
    for n,width in fields.items():
        expr=(width[1:-1].split(':')[0]+'+1') if width else '1'
        banks+=f'        {bank_module} #(.WIDTH({expr})) {n}_owner (\n'
        banks+=f'            .clk_i(clk_i),.write_i({n}_write_enable[storage_row]),\n'
        banks+=f'            .data_i({n}_write_data[storage_row]),.data_o({n}[storage_row]));\n'
    banks+='    end endgenerate\n'
    text=text[:begin]+commands+'\n'+scalar+banks+text[finish:]
    text+=f'''
// Owns actual architectural queue fields. The enable/hold mux is local,
// so a shared write decision drives one input rather than every data bit.
(* keep_hierarchy = 1 *)
module {bank_module} #(parameter integer WIDTH=32) (
    input wire clk_i,write_i,
    input wire [WIDTH-1:0] data_i,
    output reg [WIDTH-1:0] data_o
);
    always @(posedge clk_i) if(write_i) data_o<=data_i;
endmodule
'''
    return text,len(fields)

def lsq_recovery(text):
    start=text.index('            recovery_branch_slot = recovery_tag_i[3 +: ROB_SLOT_WIDTH];')
    stop=text.index('            // Address generation can complete',start)
    text=text[:start]+'''            recovery_branch_age = recovery_branch_age_parallel;
            recovery_keep_count = recovery_keep_tree[1];
            recovery_first_killed = recovery_kill_slot_tree[1];
            recovery_kill_found = recovery_kill_valid_tree[1];
            for (slot=0;slot<LSQ_ENTRIES;slot=slot+1) begin
                if(recovery_kill_parallel[slot]) begin
                    valid_mem[slot]<=0; request_sent_mem[slot]<=0;
                    response_wait_mem[slot]<=0; complete_mem[slot]<=0;
                    load_reported_mem[slot]<=0; store_commit_mem[slot]<=0;
                    store_ack_mem[slot]<=0;
                end
            end
'''+text[stop:]
    anchor='    always @(posedge clk_i) begin'
    parallel='''
    // Recovery compares physical rows in parallel. No head-relative payload
    // mux is repeated for every age in a serial scan.
    wire [ROB_SLOT_WIDTH-1:0] recovery_branch_age_parallel =
        recovery_tag_i[3 +: ROB_SLOT_WIDTH] - recovery_head_i;
    wire [LSQ_ENTRIES-1:0] recovery_kill_parallel;
    wire [COUNT_WIDTH-1:0] recovery_keep_tree [1:2*LSQ_ENTRIES-1];
    wire recovery_kill_valid_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_age_tree [1:2*LSQ_ENTRIES-1];
    wire [SLOT_WIDTH-1:0] recovery_kill_slot_tree [1:2*LSQ_ENTRIES-1];
    genvar recovery_row,recovery_node;
    generate for(recovery_row=0;recovery_row<LSQ_ENTRIES;recovery_row=recovery_row+1) begin:g_recovery_row
        wire [ROB_SLOT_WIDTH-1:0] age = rob_tag_mem[recovery_row][3 +: ROB_SLOT_WIDTH] - recovery_head_i;
        wire live = entry_age[recovery_row]<occupancy_reg && valid_mem[recovery_row];
        assign recovery_kill_parallel[recovery_row] = live &&
            !(store_mem[recovery_row] && store_commit_mem[recovery_row]) &&
            !(load_mem[recovery_row] && retired_mem[recovery_row]) &&
            age>recovery_branch_age_parallel && age<recovery_occupancy_i;
        assign recovery_keep_tree[LSQ_ENTRIES+recovery_row] = live && !recovery_kill_parallel[recovery_row];
        assign recovery_kill_valid_tree[LSQ_ENTRIES+recovery_row] = recovery_kill_parallel[recovery_row];
        assign recovery_kill_age_tree[LSQ_ENTRIES+recovery_row] = entry_age[recovery_row];
        assign recovery_kill_slot_tree[LSQ_ENTRIES+recovery_row] = recovery_row;
    end
    for(recovery_node=1;recovery_node<LSQ_ENTRIES;recovery_node=recovery_node+1) begin:g_recovery_tree
        wire pick_left = recovery_kill_valid_tree[2*recovery_node] &&
            (!recovery_kill_valid_tree[2*recovery_node+1] ||
             recovery_kill_age_tree[2*recovery_node] <= recovery_kill_age_tree[2*recovery_node+1]);
        assign recovery_keep_tree[recovery_node] = recovery_keep_tree[2*recovery_node] + recovery_keep_tree[2*recovery_node+1];
        assign recovery_kill_valid_tree[recovery_node] = recovery_kill_valid_tree[2*recovery_node] || recovery_kill_valid_tree[2*recovery_node+1];
        assign recovery_kill_age_tree[recovery_node] = pick_left ? recovery_kill_age_tree[2*recovery_node] : recovery_kill_age_tree[2*recovery_node+1];
        assign recovery_kill_slot_tree[recovery_node] = pick_left ? recovery_kill_slot_tree[2*recovery_node] : recovery_kill_slot_tree[2*recovery_node+1];
    end endgenerate
'''
    return text.replace(anchor,parallel+'\n'+anchor,1)

def decode_credits(s):
    offset=s.index('module rv32_decode_bundle_register #(')
    a,b=s[:offset],s[offset:]
    b=b.replace('parameter integer CW=(LANES<2)?1:$clog2(LANES+1),','parameter integer CAPACITY=2*LANES,\n    parameter integer CW=$clog2(CAPACITY+1),',1)
    b=b.replace('parameter integer PW=(LANES<2)?1:$clog2(LANES)','parameter integer PW=$clog2(CAPACITY)',1)
    b=b.replace('wire [LANES*PAYLOAD_WIDTH-1:0] rows;','wire [CAPACITY*PAYLOAD_WIDTH-1:0] rows;',1)
    b=b.replace('capacity=LANES-count+consumed;','// Registered occupancy is the sole upstream credit source.\n        capacity=CAPACITY-count;',1)
    # Flush discards both queues on the edge, so acceptance can be advertised
    # upstream without connecting flush into the ready chain; bank writes remain inhibited.
    b=b.replace('ready_o[lane]=prefix && (lane<capacity) && !reset_i && !flush_i;','ready_o[lane]=prefix && (lane<capacity) && !reset_i;',1)
    b=b.replace('head<=(head+consumed)%LANES;','head<=(head+consumed)%CAPACITY;',1)
    b=b.replace('tail<=(tail+accepted)%LANES;','tail<=(tail+accepted)%CAPACITY;',1)
    b=b.replace('for(slot=0;slot<LANES;slot=slot+1)','for(slot=0;slot<CAPACITY;slot=slot+1)',1)
    b=b.replace('.ROW(slot),.PW(PW))','.ROW(slot),.PW(PW),.CAPACITY(CAPACITY))',1)
    b=b.replace('rows[((head+read_lane)%LANES)*PAYLOAD_WIDTH','rows[((head+read_lane)%CAPACITY)*PAYLOAD_WIDTH',1)
    b=b.replace('parameter integer LANES=4,WIDTH=32,ROW=0,PW=(LANES<2)?1:$clog2(LANES)','parameter integer LANES=4,WIDTH=32,ROW=0,CAPACITY=LANES,PW=$clog2(CAPACITY)',1)
    b=b.replace('(((tail_i+writer)%LANES)==ROW)','(((tail_i+writer)%CAPACITY)==ROW)',1)
    assert 'capacity=LANES-count+consumed' not in b
    return a+b

def main():
    assert not STAGE.exists() or not any(STAGE.iterdir()),'Preserve earlier candidates'
    manifest=json.loads((BASE/'build/build_manifest.json').read_text())
    files=manifest['source_sha256']
    STAGE.mkdir(parents=True,exist_ok=True)
    for n,h in files.items():
        assert sha(SOURCE/n)==h.lower()
        p=STAGE/n;p.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/n,p)
    changed=[]
    for name,depth,bank in [('rtl/backend/rv32_lsq.v','LSQ_ENTRIES','rv32_lsq_state_word'),
                            ('rtl/backend/rv32_reservation_station.v','ENTRIES','rv32_rs_state_word')]:
        p=STAGE/name;s=p.read_text(encoding='utf-8')
        if depth=='LSQ_ENTRIES':s=lsq_recovery(s)
        s,n=bank_arrays(s,depth,bank)
        p.write_text(s,encoding='utf-8');changed.append(dict(file=name,fields=n))
    p=STAGE/'rtl/cpu_core.v';p.write_text(decode_credits(p.read_text(encoding='utf-8')),encoding='utf-8');changed.append(dict(file='rtl/cpu_core.v'))
    result=dict(status='FROZEN_FOR_SYNTHESIS_SCREEN',validation='DEFERRED_UNTIL_LARGE_FREQUENCY_GAIN',
        source_root=str(STAGE),base_result=str(BASE/'verified_cpu_result.json'),base_frequency_mhz=53.43909821521762,
        parameters=manifest['parameter_overrides'],source_sha256={n:sha(STAGE/n) for n in files},changed=changed,
        strategy='Two-bundle registered-credit decode queue; parallel physical-row LSQ recovery; local enabled field storage in LSQ and RS',
        no_simulation_run=True,tool_sha256=sha(__file__))
    (STAGE/'candidate.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(status=result['status'],changes=changed)))

if __name__=='__main__':main()
