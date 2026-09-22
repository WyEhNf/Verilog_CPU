#!/usr/bin/env python3
"""Convert a flattened Yosys JSON netlist to structural STA Verilog.

Yosys' Verilog backend reconstructs ``$mem_v2`` cells as behavioral arrays,
which OpenSTA intentionally does not parse.  This converter keeps every
standard-cell instance intact and replaces each generic memory with a unique
black-box module having the exact fixed port widths of that instance.  The
result is suitable for timing the implemented standard-cell paths while the
memory paths remain explicit (and therefore auditable) timing boundaries.
"""

import argparse
import json
import re
from pathlib import Path


SIMPLE_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")


def ident(name):
    if SIMPLE_IDENT.fullmatch(name):
        return name
    return "\\{} ".format(name)


def bit_expr(bit):
    if isinstance(bit, int):
        return "n{}".format(bit)
    if bit in ("0", "1"):
        return "1'b{}".format(bit)
    return "1'bx"


def vector_expr(bits):
    if len(bits) == 1:
        return bit_expr(bits[0])
    return "{{{}}}".format(", ".join(bit_expr(bit) for bit in reversed(bits)))


def decl(direction, name, width):
    vector = " [{}:0]".format(width - 1) if width > 1 else ""
    return "  {}{} {};".format(direction, vector, ident(name))


def insert_buffer_trees(cell_records, ports, max_fanout, buffer_cell):
    """Bound data-pin fanout with balanced ASAP7 buffer trees."""
    if max_fanout <= 0:
        return {"inserted": 0, "buffered_nets": 0, "max_fanout": None,
                "cell": buffer_cell}

    all_bits = []
    for port in ports.values():
        all_bits.extend(bit for bit in port["bits"] if isinstance(bit, int))
    for _name, _type, cell in cell_records:
        for bits in cell.get("connections", {}).values():
            all_bits.extend(bit for bit in bits if isinstance(bit, int))
    next_bit = max(all_bits, default=1) + 1

    sinks = {}
    excluded_tokens = ("CLK", "CLOCK", "ARST", "SRST", "RESET")
    # Analyze only original cells.  Added buffers are wired explicitly below.
    for _cell_name, _cell_type, cell in list(cell_records):
        directions = cell.get("port_directions", {})
        for port_name, bits in cell.get("connections", {}).items():
            if directions.get(port_name) not in ("input", "inout"):
                continue
            upper_name = port_name.upper()
            if any(token in upper_name for token in excluded_tokens):
                continue
            for bit_index, bit in enumerate(bits):
                if isinstance(bit, int):
                    sinks.setdefault(bit, []).append((cell, port_name, bit_index))

    inserted = 0
    buffered_nets = 0
    for source_bit, refs in sorted(sinks.items()):
        if len(refs) <= max_fanout:
            continue
        buffered_nets += 1
        current_refs = refs
        while len(current_refs) > max_fanout:
            parent_refs = []
            for offset in range(0, len(current_refs), max_fanout):
                group = current_refs[offset:offset + max_fanout]
                output_bit = next_bit
                next_bit += 1
                buffer = {
                    "port_directions": {"A": "input", "Y": "output"},
                    "connections": {"A": [None], "Y": [output_bit]},
                }
                cell_records.append((
                    "$audit_buffer_{}".format(inserted), buffer_cell, buffer))
                inserted += 1
                for sink_cell, sink_port, sink_index in group:
                    sink_cell["connections"][sink_port][sink_index] = output_bit
                parent_refs.append((buffer, "A", 0))
            current_refs = parent_refs
        for sink_cell, sink_port, sink_index in current_refs:
            sink_cell["connections"][sink_port][sink_index] = source_bit

    return {
        "inserted": inserted,
        "buffered_nets": buffered_nets,
        "max_fanout": max_fanout,
        "cell": buffer_cell,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--top", default="cpu_core")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--cell-map", type=Path)
    parser.add_argument("--net-map", type=Path)
    parser.add_argument("--buffer-fanout", type=int, default=0)
    parser.add_argument("--buffer-cell", default="BUFx8_ASAP7_75t_R")
    args = parser.parse_args()

    data = json.loads(args.input.read_text(encoding="utf-8"))
    module = data["modules"][args.top]
    ports = module.get("ports", {})
    cells = module.get("cells", {})

    memory_defs = []
    memory_manifest = []
    generic_types = {}
    lines = ["// Generated from {}".format(args.input.as_posix())]

    # Emit fixed-interface memory declarations before the top module.
    memory_index = 0
    cell_records = []
    for cell_name, cell in cells.items():
        cell_type = cell["type"]
        if cell_type.startswith("$mem"):
            module_name = "audit_mem_{}".format(memory_index)
            memory_index += 1
            directions = cell.get("port_directions", {})
            connections = cell.get("connections", {})
            # Yosys keeps zero-width write ports on ROM-like $mem_v2 cells.
            # Empty concatenations are not legal Verilog, so omit those pins
            # from both the fixed black-box declaration and the instance.
            ordered_ports = [name for name, bits in connections.items() if bits]
            memory_defs.append("(* blackbox *) module {}({});".format(
                module_name, ", ".join(ident(name) for name in ordered_ports)))
            for port_name in ordered_ports:
                direction = directions.get(port_name, "inout")
                memory_defs.append(decl(direction, port_name, len(connections[port_name])))
            memory_defs.append("endmodule")
            memory_defs.append("")
            memory_manifest.append({
                "instance": cell_name,
                "module": module_name,
                "source_type": cell_type,
                "parameters": cell.get("parameters", {}),
                "ports": {
                    name: {
                        "direction": directions.get(name, "inout"),
                        "width": len(bits),
                    }
                    for name, bits in connections.items()
                },
            })
            cell_type = module_name
        elif cell_type.startswith("$"):
            generic_types[cell_type] = generic_types.get(cell_type, 0) + 1
        cell_records.append((cell_name, cell_type, cell))

    buffer_stats = insert_buffer_trees(
        cell_records, ports, args.buffer_fanout, args.buffer_cell)

    used_bits = set()
    for port in ports.values():
        used_bits.update(bit for bit in port["bits"] if isinstance(bit, int))
    for _cell_name, _cell_type, cell in cell_records:
        for bits in cell.get("connections", {}).values():
            used_bits.update(bit for bit in bits if isinstance(bit, int))

    lines.extend(memory_defs)
    lines.append("module {}({});".format(
        ident(args.top), ", ".join(ident(name) for name in ports)))
    for port_name, port in ports.items():
        lines.append(decl(port["direction"], port_name, len(port["bits"])))
    lines.append("")
    for bit in sorted(used_bits):
        lines.append("  wire n{};".format(bit))
    lines.append("")

    # Connect public vector bits to the canonical scalar nets used by cells.
    for port_name, port in ports.items():
        direction = port["direction"]
        for index, bit in enumerate(port["bits"]):
            if not isinstance(bit, int):
                continue
            public_bit = ident(port_name)
            if len(port["bits"]) > 1:
                public_bit += "[{}]".format(index)
            if direction == "input":
                lines.append("  assign n{} = {};".format(bit, public_bit))
            elif direction == "output":
                lines.append("  assign {} = n{};".format(public_bit, bit))
            else:
                lines.append("  tran (n{}, {});".format(bit, public_bit))
    lines.append("")

    for index, (_cell_name, cell_type, cell) in enumerate(cell_records):
        connections = cell.get("connections", {})
        lines.append("  {} u_{} (".format(ident(cell_type), index))
        rendered = []
        for port_name, bits in connections.items():
            if not bits:
                continue
            rendered.append("    .{}({})".format(ident(port_name), vector_expr(bits)))
        lines.append(",\n".join(rendered))
        lines.append("  );")
    lines.append("endmodule")
    lines.append("")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    manifest = {
        "format": "yosys-json-sta-boundaries-v1",
        "top": args.top,
        "standard_or_known_cells": len(cells) - len(memory_manifest) - sum(generic_types.values()),
        "memory_boundaries": len(memory_manifest),
        "unhandled_generic_cell_types": generic_types,
        "buffer_tree": buffer_stats,
        "memories": memory_manifest,
    }
    manifest_path = args.manifest or args.output.with_suffix(".memories.json")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    cell_map_path = args.cell_map or args.output.with_suffix(".cells.tsv")
    cell_map_path.write_text(
        "index\tsta_instance\tyosys_instance\tcell_type\n" +
        "".join(
            "{}\tu_{}\t{}\t{}\n".format(index, index, cell_name, cell_type)
            for index, (cell_name, cell_type, _cell) in enumerate(cell_records)
        ),
        encoding="utf-8",
    )
    net_map_path = args.net_map or args.output.with_suffix(".nets.tsv")
    net_map_lines = ["bit\tyosys_net\tindex\n"]
    for net_name, net in module.get("netnames", {}).items():
        for index, bit in enumerate(net.get("bits", [])):
            if isinstance(bit, int):
                net_map_lines.append("{}\t{}\t{}\n".format(bit, net_name, index))
    net_map_path.write_text("".join(net_map_lines), encoding="utf-8")
    print("wrote {} cells ({} inserted buffers), {} memory boundaries, generic={}".format(
        len(cell_records), buffer_stats["inserted"], len(memory_manifest), generic_types))


if __name__ == "__main__":
    main()
