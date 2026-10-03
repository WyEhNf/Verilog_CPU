"""Small sequential RV32IM oracle for deterministic additional CPU regressions.

This is independent of the RTL and assembler. It decodes assembled bytes, rejects
uninitialized operands, misalignment, unsupported instructions, and out-of-range
memory. It is a finite-test reference, not a full ISA or memory-system proof.
"""

from collections import Counter
import hashlib
import json

MASK = 0xffffffff
SPEC_URLS = [
    'https://docs.riscv.org/reference/isa/v20260120/unpriv/rv32.html',
    'https://docs.riscv.org/reference/isa/v20260120/unpriv/m-st-ext.html',
]
R_OPS = ['add', 'sll', 'slt', 'sltu', 'xor', 'srl', 'or', 'and']
M_OPS = ['mul', 'mulh', 'mulhsu', 'mulhu', 'div', 'divu', 'rem', 'remu']
I_OPS = ['addi', 'slli', 'slti', 'sltiu', 'xori', 'srli', 'ori', 'andi']
BRANCHES = {0: 'beq', 1: 'bne', 4: 'blt', 5: 'bge', 6: 'bltu', 7: 'bgeu'}
LOADS = {0: 'lb', 1: 'lh', 2: 'lw', 4: 'lbu', 5: 'lhu'}
STORES = {0: 'sb', 1: 'sh', 2: 'sw'}
REQUIRED_OPS = set(R_OPS + M_OPS + I_OPS + ['sub', 'sra', 'srai', 'lui', 'auipc',
                                         'jal', 'jalr'] + list(BRANCHES.values())
                   + list(LOADS.values()) + list(STORES.values()))


def signed(value, bits=32):
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def m_result(op, a, b):
    sa, sb = signed(a), signed(b)
    if op == 'mul': return (a * b) & MASK
    if op == 'mulh': return ((sa * sb) >> 32) & MASK
    if op == 'mulhsu': return ((sa * b) >> 32) & MASK
    if op == 'mulhu': return ((a * b) >> 32) & MASK
    if op == 'divu': return MASK if b == 0 else a // b
    if op == 'remu': return a if b == 0 else a % b
    if b == 0: return MASK if op == 'div' else a
    quotient = abs(sa) // abs(sb)
    if (sa < 0) != (sb < 0): quotient = -quotient
    return (quotient if op == 'div' else sa - quotient * sb) & MASK


def execute(code, max_steps=200000):
    regs, memory, pc = [0] + [None] * 31, {}, 0
    coverage, events = Counter(), Counter()
    trace = hashlib.sha256()

    def reg(index):
        value = regs[index]
        if value is None: raise ValueError(f'uninitialized x{index} at pc={pc:x}')
        return value

    for step in range(1, max_steps + 1):
        if pc % 4 or not 0 <= pc <= len(code) - 4:
            raise ValueError(f'invalid instruction fetch {pc:x}')
        inst = int.from_bytes(code[pc:pc + 4], 'little')
        opcode, rd = inst & 127, (inst >> 7) & 31
        f3, rs1, rs2, f7 = (inst >> 12) & 7, (inst >> 15) & 31, (inst >> 20) & 31, inst >> 25
        imm = signed(inst >> 20, 12)
        next_pc, value, store, exit_value = (pc + 4) & MASK, None, None, None
        if opcode == 0x37:
            op, value = 'lui', inst & 0xfffff000
        elif opcode == 0x17:
            op, value = 'auipc', pc + (inst & 0xfffff000)
        elif opcode == 0x33:
            a, b = reg(rs1), reg(rs2)
            if f7 == 1:
                op = M_OPS[f3]
                value = m_result(op, a, b)
                if f3 >= 4 and b == 0: events['division_by_zero'] += 1
                if f3 in (4, 6) and a == 0x80000000 and b == MASK:
                    events['signed_division_overflow'] += 1
            else:
                if f7 not in (0, 32) or (f7 == 32 and f3 not in (0, 5)):
                    raise ValueError(f'unsupported R encoding {inst:08x}')
                op = ('sub' if f3 == 0 else 'sra') if f7 == 32 else R_OPS[f3]
                value = {'add': lambda: a + b, 'sub': lambda: a - b,
                         'sll': lambda: a << (b & 31), 'srl': lambda: a >> (b & 31),
                         'sra': lambda: signed(a) >> (b & 31),
                         'slt': lambda: int(signed(a) < signed(b)),
                         'sltu': lambda: int(a < b), 'xor': lambda: a ^ b,
                         'or': lambda: a | b, 'and': lambda: a & b}[op]()
                if f3 in (1, 5) and b >= 32: events['shift_amount_masked'] += 1
        elif opcode == 0x13:
            a, op = reg(rs1), I_OPS[f3]
            if f3 in (1, 5):
                if (f3 == 1 and f7 != 0) or (f3 == 5 and f7 not in (0, 32)):
                    raise ValueError(f'unsupported shift encoding {inst:08x}')
                if f3 == 1: value = a << rs2
                elif f7 == 32: op, value = 'srai', signed(a) >> rs2
                else: value = a >> rs2
            else:
                value = {0: lambda: a + imm, 2: lambda: int(signed(a) < imm),
                         3: lambda: int(a < (imm & MASK)), 4: lambda: a ^ imm,
                         6: lambda: a | imm, 7: lambda: a & imm}[f3]()
        elif opcode == 0x63:
            op, a, b = BRANCHES[f3], reg(rs1), reg(rs2)
            offset = signed(((inst >> 31) << 12) | (((inst >> 7) & 1) << 11)
                            | (((inst >> 25) & 63) << 5) | (((inst >> 8) & 15) << 1), 13)
            take = {0: a == b, 1: a != b, 4: signed(a) < signed(b),
                    5: signed(a) >= signed(b), 6: a < b, 7: a >= b}[f3]
            events[op + ('_taken' if take else '_not_taken')] += 1
            if take: next_pc = (pc + offset) & MASK
        elif opcode == 0x6f:
            op, value = 'jal', pc + 4
            offset = signed(((inst >> 31) << 20) | (((inst >> 12) & 255) << 12)
                            | (((inst >> 20) & 1) << 11) | (((inst >> 21) & 1023) << 1), 21)
            next_pc = (pc + offset) & MASK
        elif opcode == 0x67 and f3 == 0:
            op, value = 'jalr', pc + 4
            target = (reg(rs1) + imm) & MASK
            if target & 1: events['jalr_low_bit_cleared'] += 1
            if rd == rs1: events['jalr_rd_equals_rs1'] += 1
            next_pc = target & ~1
        elif opcode in (0x03, 0x23):
            load = opcode == 0x03
            op = (LOADS if load else STORES)[f3]
            width = 1 << (f3 & 3)
            if not load: imm = signed(((inst >> 25) << 5) | ((inst >> 7) & 31), 12)
            addr = (reg(rs1) + imm) & MASK
            if addr % width: raise ValueError(f'misaligned {op} at {addr:x}')
            if not load and addr == 0x80000000 and width == 4:
                exit_value = reg(rs2)
                store = [addr, width, exit_value]
            else:
                if not len(code) <= addr <= 0x10000000 - width:
                    raise ValueError(f'RAM/code boundary violation {op} at {addr:x}')
                if load:
                    if any(addr + n not in memory for n in range(width)):
                        raise ValueError(f'uninitialized memory load at {addr:x}')
                    value = sum(memory[addr + n] << (8 * n) for n in range(width))
                    if f3 < 4: value = signed(value, width * 8)
                else:
                    data = reg(rs2)
                    store = [addr, width, data & ((1 << (width * 8)) - 1)]
                    for n in range(width): memory[addr + n] = (data >> (8 * n)) & 255
                events[f'{op}_lane{addr & 3}'] += 1
        else:
            raise ValueError(f'unsupported instruction {inst:08x} at {pc:x}')
        coverage[op] += 1
        if value is not None:
            value &= MASK
            if rd: regs[rd] = value
            else: events['discard_x0_write'] += 1
        trace.update(json.dumps([pc, inst, rd if value is not None else None,
                                 value, store], separators=(',', ':')).encode('ascii'))
        if exit_value is not None:
            return dict(expected_u32=exit_value, instructions_through_exit_store=step,
                        coverage=dict(coverage), events=dict(events), trace_sha256=trace.hexdigest())
        pc = next_pc
    raise ValueError('reference instruction limit exceeded')
