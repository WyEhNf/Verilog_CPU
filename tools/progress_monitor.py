#!/usr/bin/env python3
"""Real-time test progress window (Tkinter).

Attaches to running regression logs and shows per-test status, overall
progress and a log tail.  Polls the log files incrementally; nothing is
executed by this tool itself.

Usage:
    python tools/progress_monitor.py --manifest tests/manifest \
        --logs .join01.log,.join02.log --title "JOIN Regression"

Log line contract (join mode):
    PASS: JOIN-01 ...                          -> join01 phase passed
    INFO: loading image <root>\<name>.data     -> test <name> started
    PASS: JOIN-02 image=<name> return=<r> cycles=<c> instret=<i>
    FAIL: <anything with image=<name> ...>
    <name> failed / image failed: <name>       -> test <name> failed
    PASS: JOIN-02 all 18 images halted ...     -> all tests done
The window stays open on completion so failures remain visible.
"""

import argparse
import os
import re
import time

import tkinter as tk
from tkinter import ttk

COL_PENDING = "#b0b0b0"
COL_RUNNING = "#d9a520"
COL_PASS = "#2e9e46"
COL_FAIL = "#d0342c"
COL_DONE = "#2e6fd0"

# test name -> dict(status, expected, actual, cycles, instret, log)
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_PASS = "pass"
STATUS_FAIL = "fail"


def parse_manifest(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            fields = [x.strip() for x in s.split(",")]
            rows.append((fields[0], fields[1]))
    return rows


class ProgressMonitor:
    def __init__(self, root, title, manifest, logs, join01, mode="join"):
        self.root = root
        self.logs = logs
        self.offsets = {p: 0 for p in logs}
        self.mode = mode
        self.tests = {}
        order = []
        if mode == "yosys":
            for stage in ("read_verilog", "hierarchy", "chparam", "procs",
                          "opt 1", "fsm", "opt 2", "memory_dff", "techmap",
                          "opt 3", "abc", "opt 4", "stat/write"):
                self.tests[stage] = {"status": STATUS_PENDING, "expected": "",
                                     "actual": "", "cycles": "", "instret": ""}
                order.append(stage)
            self.stage_extra = {s: "" for s in order}
        else:
            if join01:
                self.tests["JOIN-01"] = {"status": STATUS_PENDING, "expected": "-",
                                         "actual": "", "cycles": "", "instret": ""}
                order.append("JOIN-01")
            for name, expected in manifest:
                self.tests[name] = {"status": STATUS_PENDING, "expected": expected,
                                    "actual": "", "cycles": "", "instret": ""}
                order.append(name)
        self.order = order
        self.done = False
        self.start_time = time.time()
        self.tail_lines = []
        self.stage_idx = 0

        root.title(title)
        root.geometry("940x640")
        root.configure(bg="#1e1f24")

        header = tk.Label(root, text=title, font=("Segoe UI", 15, "bold"),
                          bg="#1e1f24", fg="#e8e8ea")
        header.pack(anchor="w", padx=14, pady=(12, 2))
        self.status_label = tk.Label(root, text="", font=("Segoe UI", 10),
                                     bg="#1e1f24", fg="#9fa1a8")
        self.status_label.pack(anchor="w", padx=14)

        bar_frame = tk.Frame(root, bg="#1e1f24")
        bar_frame.pack(fill="x", padx=14, pady=(8, 4))
        self.bar = ttk.Progressbar(bar_frame, maximum=100, length=600)
        self.bar.pack(side="left", fill="x", expand=True)
        self.pct_label = tk.Label(bar_frame, text="0%", font=("Segoe UI", 10),
                                  bg="#1e1f24", fg="#e8e8ea", width=6)
        self.pct_label.pack(side="left", padx=(8, 0))

        cols = ("name", "status", "expected", "actual", "cycles", "instret")
        table_frame = tk.Frame(root, bg="#1e1f24")
        table_frame.pack(fill="both", expand=True, padx=14, pady=6)
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings",
                                 height=14)
        for cid, text, width in (("name", "Test", 180), ("status", "Status", 90),
                                 ("expected", "Expected", 80), ("actual", "Actual", 80),
                                 ("cycles", "Cycles", 100), ("instret", "Instret", 80)):
            self.tree.heading(cid, text=text)
            self.tree.column(cid, width=width, anchor="w")
        self.tree.tag_configure(STATUS_PENDING, foreground=COL_PENDING)
        self.tree.tag_configure(STATUS_RUNNING, foreground=COL_RUNNING)
        self.tree.tag_configure(STATUS_PASS, foreground=COL_PASS)
        self.tree.tag_configure(STATUS_FAIL, foreground=COL_FAIL)
        vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for name in self.order:
            self.tree.insert("", "end", iid=name, values=(name, "pending", "-", "", "", ""))

        tail_label = tk.Label(root, text="log tail", font=("Segoe UI", 9, "bold"),
                              bg="#1e1f24", fg="#9fa1a8")
        tail_label.pack(anchor="w", padx=14)
        self.tail = tk.Text(root, height=7, bg="#141519", fg="#b8bac2",
                            font=("Consolas", 9), state="disabled", relief="flat")
        self.tail.pack(fill="x", padx=14, pady=(0, 12))

        self._refresh_table()
        root.after(1000, self._tick)

    def _read_new_lines(self):
        new_lines = []
        for path in self.logs:
            if not os.path.exists(path):
                continue
            size = os.path.getsize(path)
            if size < self.offsets[path]:  # log rotated/truncated
                self.offsets[path] = 0
            with open(path, encoding="utf-8", errors="replace") as f:
                f.seek(self.offsets[path])
                data = f.read()
                self.offsets[path] = f.tell()
            new_lines.extend(data.splitlines())
        return new_lines

    def _apply_lines(self, lines):
        re_load = re.compile(r"loading image .*[/\\]([A-Za-z0-9_]+)\.data")
        re_pass = re.compile(r"PASS: JOIN-02 image=(\w+) return=(\d+) "
                             r"cycles=(\d+) instret=(\d+)")
        re_fail = re.compile(r"image=(\w+)")
        for line in lines:
            self.tail_lines.append(line)
            s = line.strip()
            if self.mode == "yosys":
                self._apply_yosys_line(s)
                continue
            if s.startswith("PASS: JOIN-01"):
                self._set("JOIN-01", STATUS_PASS, actual=s)
                continue
            m = re_load.search(s)
            if m and m.group(1) in self.tests:
                self._set(m.group(1), STATUS_RUNNING)
                continue
            m = re_pass.search(s)
            if m and m.group(1) in self.tests:
                self._set(m.group(1), STATUS_PASS, actual=m.group(2),
                          cycles=m.group(3), instret=m.group(4))
                continue
            if ("FAIL" in s or "failed" in s) and "loading image" not in s:
                m = re_fail.search(s)
                name = m.group(1) if m else None
                if name in self.tests:
                    self._set(name, STATUS_FAIL)
                elif self.tests.get("JOIN-01", {}).get("status") == STATUS_RUNNING:
                    self._set("JOIN-01", STATUS_FAIL)
            if re.match(r"PASS: JOIN-02 all \d+ images halted", s):
                self.done = True
        self.tail_lines = self.tail_lines[-80:]

    def _apply_yosys_line(self, s):
        # yosys verbose log: "N. Executing <pass> pass." and per-file
        # "Executing Verilog-2005 frontend: <path>" lines during read_verilog.
        m_frontend = re.search(r"Verilog-2005 frontend: (.+?)[\s']", s)
        if m_frontend:
            self.stage_idx = 0
            self._set("read_verilog", STATUS_RUNNING)
            self.stage_extra["read_verilog"] = m_frontend.group(1)
            return
        m_pass = re.match(r"\d+\.\d*\.?\s*Executing ([A-Za-z0-9_]+) pass", s)
        if m_pass:
            pass_name = m_pass.group(1).lower()
            stage_map = {"hierarchy": 1, "chparam": 2, "proc": 3, "opt": None,
                         "fsm": 5, "memory_dff": 7, "techmap": 8,
                         "abc": 10, "stat": 12, "write_verilog": 12}
            opt_slots = [4, 6, 9, 11]
            if pass_name == "opt":
                idx = next(i for i in opt_slots
                           if self.tests[self.order[i]]["status"] == STATUS_PENDING)
            else:
                idx = stage_map.get(pass_name)
            if idx is None:
                return
            # Mark everything before idx as passed, idx as running.
            for i, name in enumerate(self.order):
                t = self.tests[name]
                if i < idx and t["status"] == STATUS_PENDING:
                    t["status"] = STATUS_PASS
                elif i == idx and t["status"] == STATUS_PENDING:
                    t["status"] = STATUS_RUNNING
            self.stage_idx = idx
            return
        if "End of script" in s:
            for name in self.order:
                if self.tests[name]["status"] == STATUS_PENDING:
                    self.tests[name]["status"] = STATUS_PASS
            self.done = True
        if s.startswith("ERROR:"):
            name = self.order[self.stage_idx] if self.stage_idx < len(self.order) else None
            if name and self.tests[name]["status"] != STATUS_PASS:
                self.tests[name]["status"] = STATUS_FAIL
            self.done = True

    def _set(self, name, status, actual=None, cycles=None, instret=None):
        t = self.tests[name]
        if status == STATUS_PASS:
            t["status"] = status
            if actual is not None:
                t["actual"] = actual
            if cycles is not None:
                t["cycles"] = cycles
            if instret is not None:
                t["instret"] = instret
        elif t["status"] != STATUS_PASS:  # a later fail does not un-pass
            t["status"] = status

    def _refresh_table(self):
        for name in self.order:
            t = self.tests[name]
            status_text = {"pending": "pending", "running": "RUNNING",
                           "pass": "PASS", "fail": "FAIL"}[t["status"]]
            detail = self.stage_extra.get(name, "") if self.mode == "yosys" else t["expected"]
            self.tree.item(name, values=(name, status_text, detail,
                                         t["actual"], t["cycles"], t["instret"]),
                           tags=(t["status"],))
            if t["status"] == STATUS_RUNNING:
                self.tree.see(name)

    def _tick(self):
        self._apply_lines(self._read_new_lines())
        self._refresh_table()

        finished = sum(1 for t in self.tests.values()
                       if t["status"] in (STATUS_PASS, STATUS_FAIL))
        total = len(self.tests)
        pct = int(100.0 * finished / total) if total else 0
        self.bar["value"] = pct
        self.pct_label["text"] = f"{pct}%"
        elapsed = int(time.time() - self.start_time)
        npass = sum(1 for t in self.tests.values() if t["status"] == STATUS_PASS)
        nfail = sum(1 for t in self.tests.values() if t["status"] == STATUS_FAIL)
        state = "DONE" if self.done else "running"
        self.status_label["text"] = (f"{state} | {finished}/{total} finished | "
                                     f"pass {npass} | fail {nfail} | "
                                     f"elapsed {elapsed//60}m{elapsed%60:02d}s")
        tail_text = "\n".join(self.tail_lines[-7:])
        self.tail.configure(state="normal")
        self.tail.delete("1.0", "end")
        self.tail.insert("1.0", tail_text)
        self.tail.configure(state="disabled")
        self.root.after(1000, self._tick)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default="",
                    help="manifest CSV (join mode)")
    ap.add_argument("--logs", required=True,
                    help="comma-separated log files to watch")
    ap.add_argument("--title", default="Test Progress")
    ap.add_argument("--join01", action="store_true",
                    help="include a JOIN-01 phase row")
    ap.add_argument("--mode", choices=["join", "yosys"], default="join")
    args = ap.parse_args()

    manifest = parse_manifest(args.manifest) if args.manifest else []
    root = tk.Tk()
    ProgressMonitor(root, args.title, manifest,
                    [p.strip() for p in args.logs.split(",") if p.strip()],
                    args.join01, args.mode)
    root.mainloop()


if __name__ == "__main__":
    main()
