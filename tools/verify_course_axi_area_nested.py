"""Verify nested Yosys statistics without changing frozen tools or physical pricing.

In the installed Yosys JSON format, design.num_cells counts recursively expanded
physical leaves; design.num_submodules and the functional entries in its type
dictionary retain only the top module's direct instances. Reconcile these two
scopes explicitly. Every reachable nested module is still recursively expanded,
including all actual SRAM. The original verifier's other checks are unchanged.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import verify_course_axi_area as original


def expand_stat_census(statistics, top='student_top'):
    modules = {name.removeprefix('\\'): row for name, row in statistics['modules'].items()}
    assert len(modules) == len(statistics['modules']) and top in modules, 'Ambiguous or missing statistics top'
    memo = {}

    def counts(row):
        raw = row['num_cells_by_type']
        assert all(type(v) is int and v > 0 for v in raw.values()), 'Invalid cell multiplicity'
        return Counter(raw)

    def expand(kind, ancestors=()):
        assert kind not in ancestors, 'Recursive statistics hierarchy'
        if kind in memo:
            return memo[kind]
        row = modules[kind]
        assert row['num_memories'] == row['num_memory_bits'] == row['num_processes'] == 0, 'Unmapped module objects'
        leaves, hierarchy, direct_modules = Counter(), Counter(), Counter()
        direct_leaves = 0
        for child, count in counts(row).items():
            normalized = child.removeprefix('\\')
            if normalized not in modules:
                leaves[child] += count
                direct_leaves += count
            else:
                direct_modules[child] += count
                hierarchy[child] += count
                subleaves, submodules, _ = expand(normalized, ancestors+(kind,))
                leaves.update({n:v*count for n,v in subleaves.items()})
                hierarchy.update({n:v*count for n,v in submodules.items()})
        assert direct_leaves == row['num_cells'], 'Module leaf total mismatch'
        assert sum(direct_modules.values()) == row['num_submodules'], 'Module direct-instance total mismatch'
        memo[kind] = leaves, hierarchy, direct_modules
        return memo[kind]

    leaves, hierarchy, top_direct = expand(top)
    assert set(memo) == set(modules), 'Unreachable functional statistics module'
    design = statistics['design']
    assert counts(design) == leaves+top_direct, 'Global leaf/top-direct type census mismatch'
    assert sum(leaves.values()) == design['num_cells'], 'Global expanded leaf total mismatch'
    assert sum(top_direct.values()) == design['num_submodules'], 'Global top-direct instance total mismatch'
    assert design['num_memories'] == design['num_memory_bits'] == design['num_processes'] == 0, 'Unmapped design objects'
    return leaves, hierarchy


def verify(directory, require_current=False, source_root=None):
    # Replace one in-memory callback in this independent invocation. Never edit
    # the original verifier: existing hash-bound evidence continues to use it.
    prior, prior_root = original.expand_stat_census, original.ROOT
    original.expand_stat_census = expand_stat_census
    if source_root is not None:
        original.ROOT = Path(source_root).resolve()
    try:
        result = original.verify(directory, require_current)
    finally:
        original.expand_stat_census, original.ROOT = prior, prior_root
    result.update(base_verifier=str(Path(original.__file__).resolve()),
                  base_verifier_sha256=original.sha256(original.__file__),
                  verifier_sha256=original.sha256(__file__),
                  checked_source_root=str(Path(source_root).resolve()) if source_root is not None else str(prior_root),
                  stat_census_method='Recursive complete physical leaves and all hierarchy; exact Yosys global leaf plus top-direct module census',
                  hierarchical_stat_scope_correction=True)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory', type=Path)
    p.add_argument('--require-current', action='store_true')
    p.add_argument('--source-root', type=Path)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    assert not a.out.exists(), 'Preserve earlier audit evidence'
    result = verify(a.directory, a.require_current, a.source_root)
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('status','area','leaf_instances','sram_instances','functional_hierarchy_instances','changed_current_inputs')}, indent=2))


if __name__ == '__main__':
    main()
