"""Prepare existing RS age-width parameter tests and a complete 32-versus-8 PPA pair.

No RTL logic changes: shorter unsigned scheduling ages can change issue order
at wrap, so neither cycle equivalence nor whole-CPU benefit is claimed.
"""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def replace(code, before, after):
    assert code.count(before) == 1, before
    return code.replace(before, after)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--outdir', type=Path, required=True)
    a = p.parse_args()
    out = a.outdir.resolve()
    assert not out.exists()
    source = Path('F:/CPU2026Candidates/legal_addi_fix_20261003')
    name = 'rtl/backend/rv32_reservation_station.v'
    profile = json.loads((ROOT/'build/cpu2026/verified_legal_addi_profile_20261003.json').read_text())
    assert sha(source/name) == profile['source_sha256'][name]
    basic_path = ROOT/'tb/unit/rv32_reservation_station_tb.v'
    basic = basic_path.read_text()
    basic = replace(basic, '    parameter integer ENTRIES = 4',
                    '    parameter integer ENTRIES = 4,\n    parameter integer AGE_WIDTH = 8')
    basic = replace(basic, '    localparam integer TAGW = 16;', '    localparam integer TAGW = 17;')
    basic = replace(basic, '.ENTRIES(ENTRIES)) dut (',
                    '.ENTRIES(ENTRIES), .TAG_WIDTH(TAGW), .AGE_WIDTH(AGE_WIDTH), .WAKE_MUX_IMPL(1), .ALLOC_STATIC_WRITE(1)) dut (')
    basic = replace(basic, '    integer bad;', '''    integer bad;
    integer batch, wl, sl, chosen, best, consumed, wraps;
    reg [AGE_WIDTH-1:0] model_age, before_age, selected_age;
    reg [AGE_WIDTH-1:0] model_entry_age [0:ENTRIES-1];
    reg [ENTRIES-1:0] model_selected, model_consumed;''')
    anchor = '        if (bad != 0) begin $display("FAIL: B-04 RS BE_WIDTH=%0d ENTRIES=%0d checks=%0d", BE_WIDTH, ENTRIES, bad); $finish(1); end'
    basic = replace(basic, anchor, '''        // Reach at least two age wraps by real accepted allocations. No
        // force, deposits into DUT state, or assumed output ordering.
        wraps = 0;
        if (AGE_WIDTH <= 8) begin
            clear_inputs(); reset=1; @(posedge clk); #1; reset=0;
            model_age=0;
            for (batch=0; batch<(2*(1<<AGE_WIDTH)/BE_WIDTH+3); batch=batch+1) begin
                clear_inputs(); issue_ready=0;
                for (wl=0; wl<BE_WIDTH; wl=wl+1) begin
                    alloc_entry(wl, 17'h01001+wl*2, batch*16+wl, 1, 1);
                    alloc_store[wl*32 +: 32]=(batch*16+wl)^32'h5aa51234;
                    model_entry_age[wl]=model_age+wl;
                end
                #1;
                if (alloc_fire !== {BE_WIDTH{1'b1}} || alloc_count != BE_WIDTH)
                    $fatal(1,"Natural-wrap allocation prefix failed batch=%0d",batch);
                before_age=model_age; model_age=model_age+BE_WIDTH;
                if (model_age<before_age) wraps=wraps+1;
                @(posedge clk); #1; clear_inputs(); issue_ready=0; #1;
                if (dut.age_counter !== model_age || occupancy != BE_WIDTH)
                    $fatal(1,"Natural-wrap counter/occupancy mismatch batch=%0d",batch);
                for (wl=0; wl<BE_WIDTH; wl=wl+1)
                    if (dut.age_mem[wl] !== model_entry_age[wl])
                        $fatal(1,"Stored allocation age mismatch batch=%0d slot=%0d",batch,wl);
                model_selected=0; model_consumed=0; consumed=0;
                for (wl=0; wl<BE_WIDTH; wl=wl+1) begin
                    best=-1; selected_age={AGE_WIDTH{1'b1}};
                    for (sl=0; sl<BE_WIDTH; sl=sl+1)
                        if (!model_selected[sl] && (best<0 || model_entry_age[sl]<selected_age)) begin
                            best=sl; selected_age=model_entry_age[sl];
                        end
                    model_selected[best]=1;
                    if (!issue_valid[wl] || issue_slot[wl*SW +: SW] !== best[SW-1:0] ||
                        issue_pc[wl*32 +: 32] !== (batch*16+best) ||
                        issue_src1[wl*32 +: 32] !== (batch*16+best+1) ||
                        issue_src2[wl*32 +: 32] !== (batch*16+best+2) ||
                        issue_store[wl*32 +: 32] !== ((batch*16+best)^32'h5aa51234))
                        $fatal(1,"Wrapped numeric priority/payload mismatch batch=%0d lane=%0d",batch,wl);
                    if (wl%2==0) begin
                        issue_ready[wl]=1; model_consumed[best]=1; consumed=consumed+1;
                    end
                end
                @(posedge clk); #1; clear_inputs(); issue_ready=0; #1;
                if (occupancy != BE_WIDTH-consumed || dut.age_counter !== model_age)
                    $fatal(1,"Partial issue changed age or occupancy");
                for (sl=0; sl<BE_WIDTH; sl=sl+1)
                    if (dut.valid_mem[sl] !== !model_consumed[sl])
                        $fatal(1,"Backpressure consumed wrong wrapped-priority slot");
                flush_valid=1; flush_mask={ENTRIES{1'b1}}; alloc_valid={BE_WIDTH{1'b1}};
                @(posedge clk); #1; clear_inputs();
                if (occupancy != 0 || dut.age_counter !== model_age)
                    $fatal(1,"Flush must kill entries and preserve age despite allocation inputs");
            end
            if (wraps<2) $fatal(1,"Natural age wrap coverage insufficient");
        end
        $display("PASS age-width sequential AGE_WIDTH=%0d wraps=%0d",AGE_WIDTH,wraps);
''' + anchor)
    rank_path = ROOT/'tb/unit/rv32_rs_rank_tb.v'
    rank = rank_path.read_text()
    rank = replace(rank, '    parameter integer ENTRIES = 4',
                   '    parameter integer ENTRIES = 4,\n    parameter integer AGE_WIDTH = 8,\n    parameter integer WAKE_WIDTH = BE_WIDTH')
    rank = replace(rank, '    reg [BE_WIDTH-1:0] wake_valid, issue_ready;',
                   '    reg [WAKE_WIDTH-1:0] wake_valid;\n    reg [BE_WIDTH-1:0] issue_ready;')
    rank = rank.replace('BE_WIDTH*16-1:0] wake_tag', 'WAKE_WIDTH*16-1:0] wake_tag')
    rank = rank.replace('BE_WIDTH*32-1:0] wake_value', 'WAKE_WIDTH*32-1:0] wake_value')
    rank = rank.replace('wake < BE_WIDTH', 'wake < WAKE_WIDTH')
    rank = replace(rank, '.ENTRIES(ENTRIES)) dut (',
                   '.ENTRIES(ENTRIES), .AGE_WIDTH(AGE_WIDTH), .WAKE_WIDTH(WAKE_WIDTH), .WAKE_MUX_IMPL(1), .ALLOC_STATIC_WRITE(1)) dut (')
    # Selection model reads forced arbitrary register contents, then performs
    # independent serial selection. Values include ties and wrap boundaries.
    probe_path = Path('F:/CPU2026Candidates/rs_payload_banks_20261003/tools/probe_localized_component.py')
    probe = probe_path.read_text()
    probe = replace(probe, "case = out/f'payload_banks{variant}'", "case = out/f'age{32 if variant == 0 else 8}'")
    probe = replace(probe, 'AGE_WIDTH=32, WAKE_MUX_IMPL=1, ALLOC_STATIC_WRITE=1, ALLOC_PAYLOAD_BANKS=variant)',
                    'AGE_WIDTH=(32 if variant == 0 else 8), WAKE_MUX_IMPL=1, ALLOC_STATIC_WRITE=1)')
    files = {'tb/unit/rv32_reservation_station_tb.v': basic,
             'tb/unit/rv32_rs_rank_tb.v': rank, 'tools/probe_localized_component.py': probe}
    for name, text in files.items():
        path = out/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    rtl = out/'rtl/backend/rv32_reservation_station.v'
    rtl.parent.mkdir(parents=True, exist_ok=True)
    rtl.write_bytes((source/'rtl/backend/rv32_reservation_station.v').read_bytes())
    files['rtl/backend/rv32_reservation_station.v'] = ''
    report = dict(status='PREPARED', source_root=str(source), unchanged_rtl_sha256=sha(rtl),
                  files_sha256={n:sha(out/n) for n in files},
                  original_testbench_sha256={str(p):sha(p) for p in (basic_path,rank_path,probe_path)},
                  measured_age_widths=[32,8], cycle_equivalence_claim=False,
                  cpu_integrated=False, changes_issue_priority_on_wrap=True,
                  allocation_wake_flush_and_tag_semantics_unchanged=True, preparer_sha256=sha(__file__))
    (out/'candidate_manifest.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(dict(status='PREPARED', unchanged_rtl_sha256=sha(rtl), candidate=str(out))))


if __name__ == '__main__':
    main()
