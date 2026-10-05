"""Inspect existing mapped DFF input cones; no synthesis or hardware test."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from manage_frozen_baseline_programs import read, sha, write

RUN = Path('F:/CPU2026CourseRuns/ER1_A16R2_tier3_20261005')
OUT = Path('F:/CPU2026Proofs/ER1_A16R2_mapped_payload_owner_state_20261005.json')


def main():
    assert not OUT.exists()
    netlist_path = RUN/'result/synth/opt/design.json'
    design = read(netlist_path)
    area = read(RUN/'result/synth/opt/area.json')
    stats = read(RUN/'result/synth/opt/stat.json')
    cells = design['modules']['student_top']['cells']
    drivers = {}
    for name, cell in cells.items():
        for port, direction in cell['port_directions'].items():
            if direction == 'output':
                for bit in cell['connections'][port]:
                    if isinstance(bit, int):
                        assert bit not in drivers, (bit, name)
                        drivers[bit] = name

    @lru_cache(maxsize=None)
    def nearest_write_owner(bit, remaining):
        name = drivers.get(bit)
        if name is None:
            return None, ()
        cell = cells[name]
        if cell['type'] == 'rv32_frequency_inversion':
            # This hierarchy boundary is an actual priced inverter. Only a
            # write_tree name is an owner candidate; other distribution trees
            # do not establish register write ownership.
            if '.write_tree.' in name:
                return 0, (name.split('.write_tree.',1)[0],)
            return None, ()
        if remaining <= 0 or 'DFF' in cell['type'] or 'fakeram' in cell['type'].lower():
            return None, ()
        candidates = []
        for port, direction in cell['port_directions'].items():
            if direction == 'input':
                for pin in cell['connections'][port]:
                    if isinstance(pin, int):
                        distance, owners = nearest_write_owner(pin,remaining-1)
                        if distance is not None:
                            candidates.append((distance+1,owners))
        if not candidates:
            return None, ()
        best = min(distance for distance,_ in candidates)
        return best, tuple(sorted({owner for distance,owners in candidates if distance==best for owner in owners}))

    count_by_owner = Counter()
    distances = Counter()
    ambiguous, missing = [], []
    examples = defaultdict(list)
    common_dffs = 0
    for name, cell in cells.items():
        if cell['type'] != 'DFFHQNx1_ASAP7_75t_R':
            continue
        if 'rv32_asap7_fanout.v:' not in cell['attributes'].get('src',''):
            continue
        common_dffs += 1
        assert len(cell['connections']['D']) == 1
        distance, owners = nearest_write_owner(cell['connections']['D'][0], 4)
        if len(owners) == 1:
            owner = owners[0]
            count_by_owner[owner] += 1
            distances[distance] += 1
            if len(examples[owner]) < 2:
                examples[owner].append(dict(cell=name,write_control_distance=distance))
        elif owners:
            ambiguous.append(dict(cell=name,distance=distance,owners=owners))
        else:
            missing.append(name)
    assert sum(count_by_owner.values())+len(ambiguous)+len(missing) == common_dffs
    all_dffs = stats['design']['num_cells_by_type']['DFFHQNx1_ASAP7_75t_R']
    assert sum(v for k,v in stats['design']['num_cells_by_type'].items() if 'DFF' in k.upper()) == all_dffs
    dff_area = area['sequential_area_um2']/all_dffs
    owners = [dict(owner=name,mapped_dff_count=count,mapped_dff_only_area_um2=count*dff_area,examples=examples[name])
              for name,count in count_by_owner.most_common()]
    proof = dict(status='EXISTING_MAPPED_INPUT_CONE_ATTRIBUTION_HEURISTIC_NOT_NEW_TEST',
        recorded_at=datetime.now(timezone.utc).isoformat(),run=str(RUN),
        source_manifest_sha256=sha(RUN/'source_manifest.json'),mapped_design_sha256=sha(netlist_path),
        official_area_report_sha256=sha(RUN/'result/synth/opt/area.json'),
        all_design_mapped_dffs=all_dffs,mapped_dff_cell_area_um2=dff_area,
        top_common_word_bank_dffs=common_dffs,attributed_dffs=sum(count_by_owner.values()),
        ambiguous_count=len(ambiguous),missing_count=len(missing),write_control_distances=dict(distances),
        owners=owners,ambiguous_examples=ambiguous[:20],missing_examples=missing[:20],
        attribution_limitations=[
            'This attributes common word-bank DFFs to the single nearest named write_tree inverter in a bounded D-input combinational cone. Data-input logic can contain other write controls; nearest is a heuristic, not full enable-mux structural equivalence.',
            'Ambiguous/missing registers are explicitly not attributed. This does not partition all comb logic, identify a whole MDU area, or prove a suggested state removal is legal.',
            'Reported owner areas count existing mapped DFFs only, using the sole mapped DFF cell type and exact official sequential area/count; they do not include muxes, distribution trees or downstream logic.',
            'No simulator, HDL build, synthesis, STA, equivalence check or performance benchmark was executed. Original A16R2/A21 snapshots were read only.'
        ],tests_started=False)
    write(OUT,proof)
    print({key:proof[key] for key in ('status','top_common_word_bank_dffs','attributed_dffs','ambiguous_count','missing_count')})
    print('largest_register_owner_candidates',owners[:12])


if __name__ == '__main__':
    main()
