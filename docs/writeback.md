# B-07 Completion, CDB, and Writeback

`rv32_completion_network` accepts five tagged completion sources in a fixed
priority order (ALU, MUL, DIV, load, branch) and stores accepted results in a
FIFO. Up to `BE_WIDTH` entries are presented on the CDB each cycle; entries
not granted by `cdb_ready_i` remain buffered and preserve their metadata.

The network mirrors each granted lane to ROB-ready/value and RS/LSQ wakeup
ports. PRF writes and wakeups are enabled only for register-producing,
non-store entries. Store metadata remains available to ROB/LSQ but never
consumes a PRF write port. Invalid target tags, stale complete tags, and
flushes are removed before arbitration.
