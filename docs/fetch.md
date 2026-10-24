# A-04 Fetch frontend

`rv32_fetch_frontend` owns the fetch PC, frontend epoch, and a parameterized
Fetch Queue. It accepts one line response at a time from the I-cache and emits
only a contiguous valid prefix of up to `FE_WIDTH` `FetchPacket` entries. The
packet uses the frozen `{epoch, btb_hit, pred_kind, pred_target, pred_taken,
inst, pc}` field order from `rv32im_defs.vh`.

Prediction metadata is supplied per instruction with the I-cache response;
this keeps the frontend unit independently testable while allowing the A-02
predictor to be connected at the integration boundary. The first predicted
taken instruction truncates the bundle and becomes the next fetch PC. A line
tail emits only the words remaining in that line.

`redirect_valid_i` has priority over normal queue activity: it clears queued
old-epoch packets, installs the supplied PC/epoch, and permits stale responses
to be discarded. `stop_i`, `error_i`, a HALT instruction (`0x0ff00513`), and an
error response freeze new fetch requests. Queue output payloads remain stable
while a valid lane is not ready, and only a contiguous ready prefix is
dequeued.

Verification entry `make a04` runs Icarus unit tests at `FE_WIDTH=1/2/4`, then
Verilator lint and Yosys hierarchy/proc/memory checks.
