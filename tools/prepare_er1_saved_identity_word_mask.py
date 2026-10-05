"""Bound saved report identity mask fanout using the A94 measured path."""
from datetime import datetime, timezone
from pathlib import Path
import shutil

from manage_frozen_baseline_programs import read, sha, write

BASE = Path('F:/CPU2026Candidates/tier3_er1_20261005')
PARENT = BASE/'A97_rs_elastic_skip_capacity'
TARGET = BASE/'A98_saved_identity_word_mask'
REVIEW = BASE/'A98_source_review.json'
RUN = Path('F:/CPU2026CourseRuns/ER1_A94_tier3_20261006')


def once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new)


def main():
    assert not TARGET.exists() and not REVIEW.exists()
    parent = read(PARENT/'candidate.json')
    assert sha(PARENT/'candidate.json') == '4e55dab4cf14ec71314535a1dc92db1e354939842df0a3f3d846366f35fb634f'
    for name,digest in parent['source_sha256'].items():
        assert sha(PARENT/name) == digest, name
    timing = read(RUN/'result/timing_only.json')
    assert timing['status'] == 'COURSE_STANDARD_WINDOWS_TIMING_ONLY_COMPLETE'
    assert timing['source_manifest_sha256'] == '9b76b2240190ea21bef13c8a574343f126002af4bdab78eafe1df43207d03f31'
    assert sha(RUN/'result/synth/opt/report.json') == timing['official_report_sha256']
    changes = {}
    name = 'rtl/backend/rv32_lsq.v'
    original = (PARENT/name).read_text(encoding='utf-8')
    marker = '    parameter integer HEAD_LOAD_PACKET_PRESELECT = 0,'
    text = once(original,marker,marker+'\n    parameter integer SAVED_IDENTITY_WORD_MASK = 0,')
    marker = '    wire [REPORT_IDENTITY_WIDTH-1:0] saved_identity_tree [1:2*REPORT_ROWS-1];'
    text = once(text,marker,'    localparam integer REPORT_IDENTITY_WORDS=(REPORT_IDENTITY_WIDTH+15)/16;\n'+marker)
    start = '                    if(HEAD_LOAD_PACKET_ACTIVE!=0) begin:g_full_saved_packet'
    end = '                end else begin:g_no_saved_identity_candidate'
    original_block = original[original.index(start):original.index(end)]
    new = '''                    if(SAVED_IDENTITY_WORD_MASK!=0) begin:g_saved_identity_words
                        wire [REPORT_IDENTITY_WIDTH-1:0] identity;
                        wire [REPORT_IDENTITY_WORDS-1:0] grant_views;
                        if(HEAD_LOAD_PACKET_ACTIVE!=0) begin:g_full_packet
                            assign identity={report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],saved_report_payload};
                        end else begin:g_identity_only
                            assign identity={report_payload[REPORT_BASE_WIDTH +: REPORT_ROB_QUERY_WIDTH],rob_tag_mem[report_row]};
                        end
                        rv32_frequency_control_tree #(.LEAVES(REPORT_IDENTITY_WORDS)) mask_tree (
                            .signal_i(saved_grant),.views_o(grant_views));
                        for(genvar identity_word=0;identity_word<REPORT_IDENTITY_WORDS;identity_word=identity_word+1) begin:g_word
                            localparam integer LOW=identity_word*16;
                            localparam integer BITS=(REPORT_IDENTITY_WIDTH-LOW>=16)?16:REPORT_IDENTITY_WIDTH-LOW;
                            assign saved_identity_tree[REPORT_ROWS+report_row][LOW +: BITS]=
                                {BITS{grant_views[identity_word]}} & identity[LOW +: BITS];
                        end
                    end else begin:g_original_saved_identity_mask
'''+original_block+'''                    end
'''
    text = once(text,original_block,new)
    assert original_block in text
    marker = '                end else begin:g_no_saved_identity_candidate'
    assert text[text.index(marker):] == original[original.index(marker):]
    assert text.index('REPORT_IDENTITY_WIDTH=') < text.index('REPORT_IDENTITY_WORDS=')
    changes[name] = text
    for name in ['rtl/backend/rv32_backend_joint.v','rtl/cpu_core.v','rtl/course/student_top.v']:
        original = (PARENT/name).read_text(encoding='utf-8')
        default = 1 if name.endswith('student_top.v') else 0
        marker = '    parameter integer LSQ_HEAD_LOAD_PACKET_PRESELECT = '+str(default)+','
        text = once(original,marker,marker+'\n    parameter integer LSQ_SAVED_IDENTITY_WORD_MASK = '+str(default)+',')
        if '/backend/' in name:
            text = once(text,'.HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT)',
                '.HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT), .SAVED_IDENTITY_WORD_MASK(LSQ_SAVED_IDENTITY_WORD_MASK)')
        else:
            text = once(text,'.LSQ_HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT)',
                '.LSQ_HEAD_LOAD_PACKET_PRESELECT(LSQ_HEAD_LOAD_PACKET_PRESELECT), .LSQ_SAVED_IDENTITY_WORD_MASK(LSQ_SAVED_IDENTITY_WORD_MASK)')
        changes[name] = text
    for name in parent['source_sha256']:
        destination = TARGET/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(PARENT/name,destination)
    for name,text in changes.items():
        (TARGET/name).write_text(text,encoding='utf-8')
    record = dict(parent)
    record.update(status='SOURCE_SAVED_IDENTITY_WORD_MASK_UNTESTED',source_root=str(TARGET),
        created_at=datetime.now(timezone.utc).isoformat(),parent_candidate=str(PARENT),parent_candidate_sha256=sha(PARENT/'candidate.json'),
        changed_from_parent_files=list(changes),source_sha256={name:sha(TARGET/name) for name in parent['source_sha256']},
        preparation_script_sha256=sha(Path(__file__)),source_review=str(REVIEW),tests_started=False,
        synthesis_started=False,timing_started=False,adopted=False,candidate_ipc=None,candidate_area_um2=None,candidate_frequency_mhz=None)
    record['parameter_overrides'] = dict(parent['parameter_overrides'],LSQ_SAVED_IDENTITY_WORD_MASK=1)
    record['enabled_profile'] = dict(parent['enabled_profile'],LSQ_SAVED_IDENTITY_WORD_MASK=1,
        saved_identity_word_mask_new_ff_bits=0,saved_identity_word_mask_new_sram_bits=0,
        saved_identity_word_mask_new_pipeline_edges=0,saved_identity_word_mask_max_payload_bits_per_grant_leaf=16)
    record['implemented_changes'] = list(parent['implemented_changes']) + [
        'Distribute unchanged saved/held report grant through existing bounded control-tree primitives to16bit slices of the full saved identity packet. Every output bit retains the identical grant AND identity function, with exact final partial slice. Default0 keeps original wide mask; no report arbitration, payload, field/query layout, liveness/GEN, hold/capture/reclaim, handshake or state changes.'
    ]
    record['material_gain_evidence'] = dict(parent['material_gain_evidence'],
        latest_measured_a94_fmax_mhz=timing['fmax_mhz'],latest_measured_a94_area_um2=timing['area_um2'],
        saved_identity_mask_limit='A94 latest worst path3.385ns originates LSQ report bound/held live, reaches saved identity query1.593ns/current ROB live1.811ns then completion/admission/LSQ GEN. Held-live stage _223268_ AOI21 drives61 loads30.9383fF with373.5ps delay and167.7ps next inverter. Source expanded A91 saved identity85bits is single saved_grant mask; association to this source mask is a hypothesis consistent with stage/cell fanout, not a proven one-to-one mapped alias. A98 bounds16bit mask loads and may reduce that stage; additional tree cost/new worst path unmeasured. Original A94 needs>111.979ps min-period reduction for>300MHz and has201.027um2 area margin; A95-A97 inherited unmeasured.')
    write(TARGET/'candidate.json',record)
    proof = dict(status=record['status'],candidate=str(TARGET),candidate_sha256=sha(TARGET/'candidate.json'),
        parent_candidate_sha256=record['parent_candidate_sha256'],changed_files=list(changes),tests_started=False,adopted=False,
        added_declared_ff_bits=0,new_sram_bits=0,new_pipeline_edges=0,
        measured_evidence_sha256={str(RUN/name):sha(RUN/name) for name in [
            'source_manifest.json','result/timing_only.json','result/synth/opt/report.json',
            'result/synth/opt/critical_paths.json','result/synth/opt/timing.rpt']},
        source_arguments=[
            'A94 completed original course PPA at290.2494331066MHz, minimum3.4453125ns, total35798.972677998um2 including7943.911838 SRAM; IPC/full correctness absent at preparation. This source change follows the new held-report identity path, not obsolete WB-address bottleneck. Known high-cap/slew cell after held-live is consistent with expanded source85bit saved grant, but optimized net alias was not recovered, so exact source-to-cell association remains inference.',
            'Original saved_grant priority/expression is unchanged. The exact full {ROBquery,saved_report_payload} or identity-only {ROBquery,ROBtag} bits are unchanged. Every existing control-tree output equals saved_grant combinationally; slice i contains LOW=i*16, BITS=min(16,WIDTH-LOW). ceil(WIDTH/16) contiguous nonoverlapping slices cover0..WIDTH-1 exactly, so every output remains saved_grant AND original identity bit for any input, including no candidate/held/normal and all supported field widths. No new validity mask or change to values/layout.',
            'Current HEAD_LOAD_PACKET_ACTIVE dependency order remains repaired; new WORDS declared after REPORT_IDENTITY_WIDTH. Mode0 retains original inner full/identity-wide mask block verbatim; mode1 uses same existing control-tree primitive and exact full/partial slice. The entire LSQ suffix after candidate block and all priority/hold/error/format/query-state logic is byte-identical. No changes to PRF/ROB/RS/cache/completion/rename/common helper/storage/ports/capacities. Defaultcore/backend/LSQ0 and top1; inactive HEAD_LOAD_IDENTITY_ACTIVE has originalzero candidate.',
            'Hypothesis: divide85bit mask fanout into6<=16bit sinks through priced retained control tree, shortening excessive grant-driver delay at small combinational cost. ABC may fold/share gates differently; fanout/new criticality/area and total gain unproven. No FF/SRAM/edge/false-path/constraint change. Preserve actual same ready/admission/GEN/MMIO/ISA behavior for all inputs. Source equality is not a substitute for full correctness tests.',
            'No HDL/lint/formal/simulation/synthesis/STA/unit job started for A98. Original A94 performance phase continues independently and frozen source/report/tool artifacts are untouched; A94 metrics cannot be borrowed by A98. Inherited A95/A96/A97 are unmeasured. Next coherent batch first reported after supported work; full target and RV32IM/19correctness/M/GEN/recovery/MMIO/parameter evidence required before adoption.'
        ],goal_complete=False)
    write(REVIEW,proof)
    print({key:proof[key] for key in ['status','candidate','candidate_sha256','changed_files','tests_started']})


if __name__ == '__main__':
    main()
