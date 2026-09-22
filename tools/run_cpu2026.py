#!/usr/bin/env python3
"""Build and run the six CPU-2026 benchmark test points on the RTL image runner."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


BENCHMARKS = (
    ("median", ("median_main.c", "median.c"), 2_000_000),
    ("multiply", ("multiply_main.c", "multiply.c"), 2_000_000),
    ("qsort", ("qsort_main.c",), 20_000_000),
    ("rsort", ("rsort.c",), 20_000_000),
    ("towers", ("towers_main.c",), 2_000_000),
    ("vvadd", ("vvadd_main.c",), 2_000_000),
)


class BenchmarkError(Exception):
    pass


def evaluation_memory(output, required_latency):
    match = re.search(r"EVAL_MEMORY: unified=(\d+) latency=(\d+) i_outstanding=(\d+) d_outstanding=(\d+) line_bytes=(\d+)", output)
    if not match:
        raise BenchmarkError("simulation omitted the compiled memory configuration; rebuild the runner")
    keys = ("unified", "latency_cycles", "i_outstanding", "d_outstanding", "line_bytes")
    config = dict(zip(keys, map(int, match.groups())))
    if config["unified"] != 1 or config["latency_cycles"] != required_latency:
        raise BenchmarkError("compiled memory configuration does not match requested evaluation: {}".format(config))
    return config


def run(command, cwd, capture=False):
    print("+ " + " ".join(str(item) for item in command), flush=True)
    completed = subprocess.run(
        command, cwd=str(cwd), text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.STDOUT if capture else None,
    )
    if capture and completed.stdout:
        print(completed.stdout, end="")
    if completed.returncode != 0:
        raise BenchmarkError("command failed with status {}: {}".format(
            completed.returncode, command[0]))
    return completed.stdout or ""


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark-root", default="CPU-2026-Benchmark")
    parser.add_argument("--cc", required=True)
    parser.add_argument("--objdump", required=True)
    parser.add_argument("--objcopy", required=True)
    parser.add_argument("--readelf", required=True)
    parser.add_argument("--vvp")
    parser.add_argument("--simulation")
    parser.add_argument("--executable")
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--preallocate", choices=("0", "1"), default="0")
    parser.add_argument("--report", default="build/cpu2026/report.json")
    parser.add_argument("--config", default="unspecified")
    parser.add_argument("--memory-latency", type=int, default=20,
                        help="Required compiled main-memory latency (performance scoring: 20)")
    args = parser.parse_args(argv)

    root = Path(__file__).resolve().parents[1]
    benchmark_root = (root / args.benchmark_root).resolve()
    if not benchmark_root.is_dir():
        raise BenchmarkError("benchmark root does not exist: {}".format(benchmark_root))
    if not args.build_only and not args.executable and not (args.vvp and args.simulation):
        raise BenchmarkError("execution needs --executable or --vvp plus --simulation")

    results = []
    for name, source_names, max_cycles in BENCHMARKS:
        benchmark_dir = benchmark_root / name
        sources = [benchmark_dir / item for item in source_names]
        for source in sources:
            if not source.is_file():
                raise BenchmarkError("missing source: {}".format(source))
        out_dir = root / "build" / "cpu2026" / name
        command = [
            sys.executable, str(root / "tools" / "make_image.py"), str(sources[0]),
            "--arch", "rv32im", "--out-dir", str(out_dir),
            "--include", str(benchmark_root / "common"),
            "--include", str(benchmark_dir),
            "--define", "PREALLOCATE=" + args.preallocate,
            "--define", "HOST_DEBUG=0",
            "--cc", args.cc, "--objdump", args.objdump,
            "--objcopy", args.objcopy, "--readelf", args.readelf,
        ]
        for source in sources[1:]:
            command.extend(("--extra-source", str(source)))
        run(command, root)

        image = out_dir / (sources[0].stem + ".image")
        result = {
            "name": name,
            "sources": [str(item.relative_to(root)) for item in sources],
            "image": str(image.relative_to(root)),
            "status": "built",
        }
        if not args.build_only:
            plusargs = [
                "+IMAGE=" + result["image"], "+TEST=cpu2026-" + name,
                "+EXPECTED=0", "+MAX_CYCLES=" + str(max_cycles),
                "+MAX_NO_RETIRE_CYCLES=1000000",
                "+CHECK_LSQ",
            ]
            execute = ([args.executable] if args.executable else
                       [args.vvp, "-N", args.simulation]) + plusargs
            output = run(execute, root, capture=True)
            result["memory"] = evaluation_memory(output, args.memory_latency)
            metrics = re.search(
                r"PASS: JOIN-02 image=cpu2026-{} return=0 cycles=(\d+) instret=(\d+)".format(
                    re.escape(name)), output)
            if not metrics:
                raise BenchmarkError("{} did not produce its architectural PASS marker".format(name))
            result["cycles"] = int(metrics.group(1))
            result["instret"] = int(metrics.group(2))
            result["ipc"] = result["instret"] / result["cycles"]
            result["status"] = "passed"
        results.append(result)

    report = {
        "format": "cpu2026-verilator-v1",
        "config": args.config,
        "preallocate": int(args.preallocate),
        "required_memory_latency_cycles": args.memory_latency,
        "results": results,
    }
    if not args.build_only:
        total_cycles = sum(item["cycles"] for item in results)
        total_instret = sum(item["instret"] for item in results)
        report["total_cycles"] = total_cycles
        report["total_instret"] = total_instret
        report["aggregate_ipc"] = total_instret / total_cycles

    report_path = root / args.report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("PASS: CPU-2026 {} benchmarks {}".format(
        len(results), "built" if args.build_only else
        "aggregate IPC {:.6f}".format(report["aggregate_ipc"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, BenchmarkError) as exc:
        print("FAIL: CPU-2026 {}".format(exc), file=sys.stderr)
        sys.exit(1)
