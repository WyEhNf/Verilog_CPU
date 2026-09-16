// External, read-only adapter for RISC-V-CPU-Simulator.
//
// This file intentionally uses only the reference model's public headers and
// public evaluate/arbitrate/latch ports.  It must never be copied into or used
// to modify the reference repository.

#include "sim/simulator.h"
#include "sim/module_io.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

namespace {

constexpr std::uint64_t kDefaultMaxCycles = 200000000ULL;

struct Options {
  const char *input = nullptr;
  const char *output = nullptr;
  std::uint64_t max_cycles = kDefaultMaxCycles;
};

void usage(const char *program) {
  std::fprintf(stderr,
               "usage: %s --input IMAGE --output TRACE.jsonl "
               "[--max-cycles N]\n",
               program);
}

bool parse_u64(const char *text, std::uint64_t &value) {
  char *end = nullptr;
  const unsigned long long parsed = std::strtoull(text, &end, 0);
  if (text == end || *end != '\0')
    return false;
  value = static_cast<std::uint64_t>(parsed);
  return true;
}

bool parse_options(int argc, char **argv, Options &options) {
  for (int index = 1; index < argc; ++index) {
    if (std::strcmp(argv[index], "--input") == 0 && index + 1 < argc) {
      options.input = argv[++index];
    } else if (std::strcmp(argv[index], "--output") == 0 &&
               index + 1 < argc) {
      options.output = argv[++index];
    } else if (std::strcmp(argv[index], "--max-cycles") == 0 &&
               index + 1 < argc) {
      if (!parse_u64(argv[++index], options.max_cycles))
        return false;
    } else {
      return false;
    }
  }
  return options.input != nullptr && options.output != nullptr &&
         options.max_cycles != 0;
}

unsigned store_bytes(sim::MF operation) {
  if (operation == sim::SB)
    return 1;
  if (operation == sim::SH)
    return 2;
  return 4;
}

// JSON has arbitrary-size integer syntax.  Emit the 128-bit line-aligned store
// payload as decimal so Python's JSON parser can consume it without a string
// extension to the CommitRecord schema.
std::string decimal_u128(unsigned __int128 value) {
  if (value == 0)
    return "0";
  char reversed[40];
  std::size_t count = 0;
  while (value != 0) {
    reversed[count++] = static_cast<char>('0' + value % 10);
    value /= 10;
  }
  std::string result;
  result.reserve(count);
  while (count != 0)
    result.push_back(reversed[--count]);
  return result;
}

void emit_commit(FILE *stream, std::uint64_t cycle,
                 const sim::CommitOutput &commit) {
  const bool halt = commit.terminate;
  const bool store = commit.store;
  const unsigned bytes = store ? store_bytes(commit.ins.mem) : 0;
  const unsigned line_offset = commit.address & 15u;
  const std::uint32_t store_mask =
      store ? (((1u << bytes) - 1u) << line_offset) : 0u;
  const unsigned __int128 store_data =
      store ? (static_cast<unsigned __int128>(commit.value)
               << (line_offset * 8u))
            : 0;

  // TERM is a simulator control sentinel, not an architectural ADDI.  Match
  // the RTL HALT CommitRecord by suppressing rd writeback and reporting the
  // pre-sentinel a0 value.
  const unsigned rd = static_cast<unsigned>(commit.ins.rd);
  const bool rd_we = !halt && commit.write_reg;
  const std::uint32_t value =
      halt ? commit.termination_value : commit.value;
  const std::string store_data_text = decimal_u128(store_data);

  std::fprintf(
      stream,
      "{\"cycle\":%llu,\"lane\":0,\"valid\":true,\"pc\":%u,"
      "\"inst\":%u,\"rd\":%u,\"rd_we\":%s,\"value\":%u,"
      "\"is_store\":%s,\"store_addr\":%u,\"store_mask\":%u,"
      "\"store_data\":%s,\"halted\":%s,\"return_value\":%u}\n",
      static_cast<unsigned long long>(cycle), commit.pc, commit.ins.raw, rd,
      rd_we ? "true" : "false", value, store ? "true" : "false",
      store ? commit.address : 0u, store_mask, store_data_text.c_str(),
      halt ? "true" : "false", halt ? commit.termination_value : 0u);
}

sim::CycleWires evaluate_cycle(const sim::Simulator &cpu,
                               const sim::u8 order[sim::Simulator::MODULE_COUNT]) {
  sim::CycleWires wires{};
  for (sim::u8 index = 0; index < sim::Simulator::MODULE_COUNT; ++index) {
    cpu.evaluate_module(static_cast<sim::Simulator::Module>(order[index]),
                        wires);
  }
  wires.cdb = cpu.cdb.evaluate(wires.execute, wires.memory);
  cpu.resolve_control_wires(wires);
  return wires;
}

void latch_cycle(sim::Simulator &cpu, const sim::CycleWires &wires,
                 const sim::u8 order[sim::Simulator::MODULE_COUNT]) {
  for (sim::u8 index = 0; index < sim::Simulator::MODULE_COUNT; ++index) {
    cpu.latch_module(static_cast<sim::Simulator::Module>(order[index]), wires);
  }
  ++cpu.clk;
}

} // namespace

int main(int argc, char **argv) {
  Options options;
  if (!parse_options(argc, argv, options)) {
    usage(argv[0]);
    return 2;
  }

  FILE *input = std::fopen(options.input, "rb");
  if (input == nullptr) {
    std::fprintf(stderr, "reference_trace: cannot open image: %s\n",
                 options.input);
    return 2;
  }
  FILE *output = std::fopen(options.output, "wb");
  if (output == nullptr) {
    std::fprintf(stderr, "reference_trace: cannot open output: %s\n",
                 options.output);
    std::fclose(input);
    return 2;
  }

  sim::Simulator cpu;
  cpu.init_stream(input);
  std::fclose(input);

  std::uint64_t records = 0;
  while (!cpu.done() && cpu.clk < options.max_cycles) {
    sim::u8 order[sim::Simulator::MODULE_COUNT];
    const sim::u8 rotation =
        static_cast<sim::u8>(cpu.clk % sim::Simulator::MODULE_COUNT);
    for (sim::u8 index = 0; index < sim::Simulator::MODULE_COUNT; ++index) {
      order[index] =
          static_cast<sim::u8>((index + rotation) % sim::Simulator::MODULE_COUNT);
    }

    // Capture the public commit wire after evaluate/arbitration and before any
    // state owner sees the latch edge, exactly as specified by the reference
    // model's CycleWires contract.
    const sim::CycleWires wires = evaluate_cycle(cpu, order);
    if (wires.commit.valid) {
      emit_commit(output, static_cast<std::uint64_t>(cpu.clk) + 1, wires.commit);
      ++records;
    }
    latch_cycle(cpu, wires, order);
  }

  const bool write_failed = std::ferror(output) != 0;
  std::fclose(output);
  if (write_failed) {
    std::fprintf(stderr, "reference_trace: failed while writing %s\n",
                 options.output);
    return 2;
  }
  if (!cpu.done()) {
    std::fprintf(stderr, "reference_trace: exceeded %llu cycles\n",
                 static_cast<unsigned long long>(options.max_cycles));
    return 1;
  }
  if (cpu.failed()) {
    std::fprintf(stderr,
                 "reference_trace: simulator fault pc=0x%08x inst=0x%08x\n",
                 cpu.fault_pc, cpu.fault_raw);
    return 1;
  }

  std::fprintf(stderr,
               "reference_trace: PASS records=%llu cycles=%llu return=%u\n",
               static_cast<unsigned long long>(records),
               static_cast<unsigned long long>(cpu.clk), cpu.out);
  return 0;
}
