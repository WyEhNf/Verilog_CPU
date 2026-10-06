"""Separate wakeup identity width from ROB identity; preserve live filtering."""
import re
from prepare_staged_frequency_candidate import ROOT, prepare, change


ENCODE = r'''
    // ROB tags still guard producer ownership before wake_valid. RS source
    // identity is physical-register identity while that allocation is live.
    // P0/out-of-range source IDs never claim a wake dependency.
    localparam integer RS_SOURCE_TAG_WIDTH=RS_PHYSICAL_WAKEUP?(PAW+1):TAG_WIDTH;
    wire [BE_WIDTH*RS_SOURCE_TAG_WIDTH-1:0] rs_source1_identity,rs_source2_identity;
    genvar source_identity_lane;
    generate if(RS_PHYSICAL_WAKEUP!=0) begin:g_physical_source_identity
        for(source_identity_lane=0;source_identity_lane<BE_WIDTH;source_identity_lane=source_identity_lane+1) begin:g_lane
            wire [PAW-1:0] phys1=d_src1_phys[source_identity_lane*PAW +: PAW];
            wire [PAW-1:0] phys2=d_src2_phys[source_identity_lane*PAW +: PAW];
            assign rs_source1_identity[source_identity_lane*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]={phys1,(phys1!=0 && phys1<PHYS_REGS)};
            assign rs_source2_identity[source_identity_lane*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]={phys2,(phys2!=0 && phys2<PHYS_REGS)};
        end
    end else begin:g_rob_source_identity
        assign rs_source1_identity=rs_src1_tag;
        assign rs_source2_identity=rs_src2_tag;
    end endgenerate
'''


WAKE = r'''
    genvar wake_identity_lane;
    generate if(RS_PHYSICAL_WAKEUP!=0) begin:g_physical_wake_identity
        for(wake_identity_lane=0;wake_identity_lane<RS_WAKE_WIDTH;wake_identity_lane=wake_identity_lane+1) begin:g_lane
            wire [PAW-1:0] phys;
            if(wake_identity_lane<BE_WIDTH) begin:g_completed
                // Completion exports wake tag/value from this same CDB lane.
                assign phys=cdb_phys[wake_identity_lane*PAW +: PAW];
            end else begin:g_held_producer
                assign phys=producer_phys[(wake_identity_lane-BE_WIDTH)*PAW +: PAW];
            end
            assign rs_wake_tag[wake_identity_lane*RS_SOURCE_TAG_WIDTH +: RS_SOURCE_TAG_WIDTH]={phys,(phys!=0 && phys<PHYS_REGS)};
        end
    end else begin:g_rob_wake_identity
        assign rs_wake_tag={producer_tag,wake_wb_tag};
    end endgenerate
'''


def backend(t):
    t=change(t,'    parameter integer PHYS_TAG_IMPL = 0,',
             '    parameter integer RS_PHYSICAL_WAKEUP = 0,\n    parameter integer PHYS_TAG_IMPL = 0,')
    t=change(t,'    wire [RS_WAKE_WIDTH*TAG_WIDTH-1:0] rs_wake_tag;',
             '    wire [RS_WAKE_WIDTH*RS_SOURCE_TAG_WIDTH-1:0] rs_wake_tag;')
    t=change(t,'    reg [BE_WIDTH*TAG_WIDTH-1:0] rs_src1_tag, rs_src2_tag;',
             '    reg [BE_WIDTH*TAG_WIDTH-1:0] rs_src1_tag, rs_src2_tag;\n'+ENCODE)
    t=change(t,'if(PHYS_TAG_IMPL==0) begin:g_owned_producer_tags',
             'if(PHYS_TAG_IMPL==0 && RS_PHYSICAL_WAKEUP==0) begin:g_owned_producer_tags')
    t=change(t,'.METADATA_WIDTH(RS_METADATA_WIDTH), .WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL)',
             '.METADATA_WIDTH(RS_METADATA_WIDTH), .SOURCE_TAG_WIDTH(RS_SOURCE_TAG_WIDTH), .WAKE_MUX_IMPL(RS_WAKE_MUX_IMPL)')
    t=change(t,'.alloc_src1_tag_i(rs_src1_tag)', '.alloc_src1_tag_i(rs_source1_identity)')
    t=change(t,'.alloc_src2_tag_i(rs_src2_tag)', '.alloc_src2_tag_i(rs_source2_identity)')
    return change(t,'    assign rs_wake_tag = {producer_tag, wake_wb_tag};',WAKE)


def station(t):
    t=change(t,'    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,',
             '''    parameter integer TAG_WIDTH = `RV32IM_ROB_TAG_WIDTH_DEFAULT,
    parameter integer SOURCE_TAG_WIDTH = TAG_WIDTH,''')
    t=change(t,'    parameter integer OP_WIDTH=6,TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,',
             '''    parameter integer OP_WIDTH=6,TAG_WIDTH=17,PHYS_ADDR_WIDTH=6,
    parameter integer SOURCE_TAG_WIDTH=TAG_WIDTH,''')
    t=change(t,'    wire [TAG_WIDTH-1:0] new_tag,new_tag1,new_tag2;',
             '''    wire [TAG_WIDTH-1:0] new_tag;
    wire [SOURCE_TAG_WIDTH-1:0] new_tag1,new_tag2;''')
    t=change(t,'        PHYS_ADDR_WIDTH + 32 + TAG_WIDTH + 1 + 32 + TAG_WIDTH + 1 +',
             '        PHYS_ADDR_WIDTH + 32 + SOURCE_TAG_WIDTH + 1 + 32 + SOURCE_TAG_WIDTH + 1 +')
    # Only source/wake identity lines are rewritten. ROB/tag transport and
    # recovery remain TAG_WIDTH. The mixed helper declaration was split above.
    changed=0
    lines=[]
    names=r'\b(?:alloc_src[12]_tag_i|src[12]_tag_mem(?:_legacy)?|wake_tag_i|tag_views|local_tags|src[12]_tag_o)\b'
    for line in t.splitlines(keepends=True):
        if re.search(names,line) or '.WIDTH(WAKE_WIDTH*TAG_WIDTH)' in line:
            if re.search(r'\bTAG_WIDTH\b',line):
                # A mixed source/ROB field would require explicit handling.
                if any(n in line for n in ['alloc_rob_tag_i','rob_tag_o','rob_tag_mem']):
                    raise ValueError('Preserve mixed ROB/source identity line: '+line)
                line,n=re.subn(r'\bTAG_WIDTH\b','SOURCE_TAG_WIDTH',line)
                changed+=n
        lines.append(line)
    t=''.join(lines)
    # This inventory covers only source and wake identities. ROB identity,
    # issue payload metadata and recovery fields deliberately keep TAG_WIDTH.
    if changed!=51: raise ValueError('Expected source/wake width inventory, got '+str(changed))
    return change(t,'rv32_rs_payload_row #(.OP_WIDTH(OP_WIDTH),.TAG_WIDTH(TAG_WIDTH),',
                  'rv32_rs_payload_row #(.OP_WIDTH(OP_WIDTH),.TAG_WIDTH(TAG_WIDTH),.SOURCE_TAG_WIDTH(SOURCE_TAG_WIDTH),')


def core(t):
    return change(t,'rv32_backend_joint #(.DISPATCH_PIPELINE(1),',
                  'rv32_backend_joint #(.RS_PHYSICAL_WAKEUP(1), .DISPATCH_PIPELINE(1),')


if __name__=='__main__':
    prepare('BY1_physical_register_wakeup',ROOT/'BX_elide_onehot_rearbitration',{
        'rtl/backend/rv32_backend_joint.v':backend,
        'rtl/backend/rv32_reservation_station.v':station,
        'rtl/cpu_core.v':core,
    },'BX plus optional physical-register wake identities: separate SOURCE_TAG_WIDTH from full ROB TAG_WIDTH, current core selects PAW+1=7-bit source/wake comparisons instead of 17 bits, no active producer-tag table; full ROB generation/age/live filtering, PRF readiness and held/accepted producer values unchanged; preserve legacy backend/RS defaults, P0/out-of-range invalid source identity; no new FF/cycles, same physical register lifetime invariant as rename/PRF; area/IPC/timing unmeasured, no EDA')
