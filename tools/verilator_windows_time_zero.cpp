// Verilator 5.020 FAQ documents this fallback for hosts without weak symbols.
// The unchanged course sim.cpp advances VerilatedContext every half-cycle;
// this fallback is consulted only when its time is zero.
double sc_time_stamp() { return 0.0; }
