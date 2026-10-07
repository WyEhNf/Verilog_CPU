"""Keep full tool logs while putting failures before truncated OJ output."""
from collections import Counter
from pathlib import Path
import re
import subprocess
import sys


def run_logged(command, environment, path, phase):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as log:
        status = subprocess.call(command, env=environment, stdout=log,
                                 stderr=subprocess.STDOUT)
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"[build] {phase}: status={status}; full log={path}",
          file=sys.stderr, flush=True)
    if status:
        errors = [line for line in lines if re.search(
            r"%Error|(?:fatal )?error:|undefined reference|\*\*\*", line)]
        if errors:
            print("[build] Failure diagnostics:", file=sys.stderr)
            print("\n".join(errors[:12]), file=sys.stderr)
        print("[build] Tool log tail:", file=sys.stderr)
        print("\n".join(lines[-30:])[-6000:], file=sys.stderr, flush=True)
    else:
        warnings = Counter(re.findall(r"%Warning-([A-Z0-9_]+):", "\n".join(lines)))
        if warnings:
            print("[build] Verilator warning counts: " + ", ".join(
                f"{name}={count}" for name, count in sorted(warnings.items())),
                file=sys.stderr, flush=True)
        compiler_warnings = [line for line in lines if "warning:" in line]
        if compiler_warnings:
            print("\n".join(compiler_warnings[:12]), file=sys.stderr, flush=True)
    return status
