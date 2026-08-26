# B-08 LSQ and Memory Ordering

`rv32_lsq` allocates load/store entries in program order and gives every entry
an `{generation, slot, kind, valid}` LSQ tag. Address and store-data wakeups
are tag-qualified, so a response from a flushed or reused slot cannot update a
new instruction.

Loads scan older stores by byte. An older unknown address blocks the load; an
overlapping store with unknown data blocks only the overlap. Ready stores
forward the nearest value per byte. Uncovered bytes are requested from the
D-cache and merged with the forwarded bytes before applying `LB/LBU/LH/LHU/LW`
sign/zero extension.

Stores may calculate their address and data speculatively, but a D-cache store
request is emitted only after the matching ROB commit handshake and only for
the LSQ head. A matching D-cache acknowledgement is then held on
`store_ack_*` until the ROB accepts it. Load and store completion outputs are
held stable while their ready input is low.

The request payload follows the shared `MemoryRequest` fields: operation,
address, size, signedness, byte mask, line write data, ROB tag, and LSQ tag.
Responses carry an LSQ tag, optional 128-bit line data (or a 32-bit word
fallback), and an error bit. The LSQ retains the error alongside a completed
load or acknowledged store until the corresponding ready/valid handshake, so
the backend can report it precisely at ROB retirement.
