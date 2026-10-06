#!/usr/bin/env python3
"""Local web GUI for configuring and observing the RV32IM CPU simulation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from collections import deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUI_DIR = ROOT / "gui"
BUILD_DIR = ROOT / "build" / "gui"
OSS_BIN = ROOT / ".deps" / "oss-cad-suite-install" / "oss-cad-suite" / "bin"
OSS_ROOT = OSS_BIN.parent
TOOLCHAIN_BIN = (ROOT / ".deps" / "riscv-toolchain-install" /
                 "xpack-riscv-none-elf-gcc-15.2.0-1" / "bin")

PARAMETERS = {
    "FE_WIDTH": {"label": "前端宽度", "values": [1, 2, 4], "group": "宽度"},
    "BE_WIDTH": {"label": "后端宽度", "values": [1, 2, 4], "group": "宽度"},
    "PHYS_REGS": {"label": "物理寄存器", "min": 33, "max": 256, "group": "队列"},
    "ROB_ENTRIES": {"label": "ROB 项数", "values": [2, 4, 8, 16, 32, 64, 128], "group": "队列"},
    "RS_ENTRIES": {"label": "RS 项数", "min": 1, "max": 64, "group": "队列"},
    "LSQ_ENTRIES": {"label": "LSQ 项数", "min": 1, "max": 64, "group": "队列"},
    "ENABLE_CACHE_STATS": {"label": "缓存统计", "values": [0, 1], "group": "存储"},
    "ENABLE_CACHES": {"label": "I/D Cache", "values": [0, 1], "group": "存储"},
    "ENABLE_PREDICTOR": {"label": "分支预测器", "values": [0, 1], "group": "前端"},
    "FETCH_QUEUE_DEPTH": {"label": "取指队列深度", "values": [1, 2, 4, 8, 16, 32, 64], "group": "前端"},
    "MUL_IMPL": {"label": "乘法器实现", "values": [0, 1, 2], "group": "执行"},
    "SHIFT_IMPL": {"label": "移位器实现", "values": [0, 1], "group": "执行"},
    "PHYS_TAG_IMPL": {"label": "物理标签实现", "values": [0, 1], "group": "后端"},
    "CHECKPOINT_IMPL": {"label": "检查点实现", "values": [0, 1], "group": "后端"},
    "COMPLETION_BYPASS": {"label": "完成旁路", "values": [0, 1], "group": "后端"},
    "SERIAL_BACKEND": {"label": "串行后端", "values": [0, 1], "group": "后端"},
    "GENERATION_WIDTH": {"label": "代际位宽", "min": 1, "max": 16, "group": "后端"},
    "COMPLETION_DEPTH": {"label": "完成队列深度", "min": 1, "max": 64, "group": "队列"},
}

AREA_PROFILE = {
    "FE_WIDTH": 1, "BE_WIDTH": 1, "PHYS_REGS": 33, "ROB_ENTRIES": 2,
    "RS_ENTRIES": 1, "LSQ_ENTRIES": 1, "ENABLE_CACHE_STATS": 0,
    "ENABLE_CACHES": 0, "ENABLE_PREDICTOR": 0, "FETCH_QUEUE_DEPTH": 1,
    "MUL_IMPL": 2, "SHIFT_IMPL": 1, "PHYS_TAG_IMPL": 1,
    "CHECKPOINT_IMPL": 1, "COMPLETION_BYPASS": 1, "SERIAL_BACKEND": 1,
    "GENERATION_WIDTH": 3, "COMPLETION_DEPTH": 1,
}

PROFILES = {
    "area": {
        "label": "面积优先 · 1423.33 µm²",
        "description": "当前最终面积配置，单指令串行后端。",
        "params": AREA_PROFILE,
        "area": 1423.32876,
    },
    "ooo1": {
        "label": "乱序单发射",
        "description": "完整重命名、ROB、RS、LSQ 与完成网络。",
        "params": {**AREA_PROFILE, "PHYS_REGS": 48, "ROB_ENTRIES": 16,
                   "RS_ENTRIES": 4, "LSQ_ENTRIES": 4, "ENABLE_CACHES": 1,
                   "ENABLE_PREDICTOR": 1, "FETCH_QUEUE_DEPTH": 16,
                   "MUL_IMPL": 0, "SHIFT_IMPL": 0, "PHYS_TAG_IMPL": 0,
                   "CHECKPOINT_IMPL": 0, "COMPLETION_BYPASS": 0,
                   "SERIAL_BACKEND": 0, "GENERATION_WIDTH": 8,
                   "COMPLETION_DEPTH": 4},
    },
    "ooo2": {
        "label": "乱序双发射",
        "description": "2 路取指、发射、执行与提交。",
        "params": {**AREA_PROFILE, "FE_WIDTH": 2, "BE_WIDTH": 2,
                   "PHYS_REGS": 64, "ROB_ENTRIES": 32, "RS_ENTRIES": 8,
                   "LSQ_ENTRIES": 8, "ENABLE_CACHES": 1,
                   "ENABLE_PREDICTOR": 1, "FETCH_QUEUE_DEPTH": 16,
                   "MUL_IMPL": 0, "SHIFT_IMPL": 0, "PHYS_TAG_IMPL": 0,
                   "CHECKPOINT_IMPL": 0, "COMPLETION_BYPASS": 0,
                   "SERIAL_BACKEND": 0, "GENERATION_WIDTH": 8,
                   "COMPLETION_DEPTH": 8},
    },
    "ooo4": {
        "label": "乱序四发射",
        "description": "4 路配置，用于展示完整参数化扩展能力。",
        "params": {**AREA_PROFILE, "FE_WIDTH": 4, "BE_WIDTH": 4,
                   "PHYS_REGS": 96, "ROB_ENTRIES": 64, "RS_ENTRIES": 16,
                   "LSQ_ENTRIES": 16, "ENABLE_CACHES": 1,
                   "ENABLE_PREDICTOR": 1, "FETCH_QUEUE_DEPTH": 16,
                   "MUL_IMPL": 0, "SHIFT_IMPL": 0, "PHYS_TAG_IMPL": 0,
                   "CHECKPOINT_IMPL": 0, "COMPLETION_BYPASS": 0,
                   "SERIAL_BACKEND": 0, "GENERATION_WIDTH": 8,
                   "COMPLETION_DEPTH": 16},
    },
}


def load_tests():
    tests = []
    manifest = ROOT / "tests" / "join03_manifest.csv"
    with manifest.open(encoding="utf-8") as stream:
        rows = csv.reader(line for line in stream if not line.lstrip().startswith("#"))
        for name, source, arch, expected, max_cycles, mnemonics in rows:
            tests.append({
                "id": "join03:" + name, "name": name, "suite": "核心演示",
                "description": {
                    "accumulate": "循环、分支与整数累加",
                    "vvadd": "向量逐项加法与访存",
                    "vmul": "RV32M 乘法器路径",
                    "m_isa_smoke": "M 扩展乘除法全指令冒烟测试",
                }.get(name, source),
                "source": source, "arch": arch, "expected": int(expected),
                "max_cycles": int(max_cycles), "mnemonics": mnemonics,
                "image": f"build/images/{name}-{arch}/{name}.image",
                "buildable": True, "long": False,
            })
    external = ROOT / "tests" / "manifest"
    with external.open(encoding="utf-8") as stream:
        rows = csv.reader(line for line in stream if line.strip() and not line.lstrip().startswith("#"))
        for row in rows:
            name, expected, max_cycles, is_long = [item.strip() for item in row]
            if name == "pi":
                continue
            tests.append({
                "id": "legacy:" + name, "name": name, "suite": "完整程序",
                "description": "已有软件测试镜像" + (" · 长测试" if is_long == "1" else ""),
                "arch": "rv32im", "expected": int(expected),
                "max_cycles": int(max_cycles), "mnemonics": "",
                "image": f"RISC-V-CPU-Simulator/testcases/{name}.data",
                "buildable": False, "long": is_long == "1",
            })
    return tests


TESTS = load_tests()
TEST_BY_ID = {item["id"]: item for item in TESTS}


class SimulationManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.condition = threading.Condition(self.lock)
        self.events = deque(maxlen=20000)
        self.next_event_id = 1
        self.run_id = 0
        self.status = "idle"
        self.process = None
        self.stop_requested = False
        self.current = None

    def emit(self, event_type, **data):
        with self.condition:
            event = {"id": self.next_event_id, "type": event_type,
                     "time": time.time(), **data}
            self.next_event_id += 1
            self.events.append(event)
            self.condition.notify_all()
            return event

    def snapshot(self):
        with self.lock:
            return {"status": self.status, "run_id": self.run_id,
                    "current": self.current, "last_event_id": self.next_event_id - 1}

    def events_since(self, since, timeout=1.5):
        deadline = time.monotonic() + timeout
        with self.condition:
            while self.next_event_id - 1 <= since and time.monotonic() < deadline:
                self.condition.wait(deadline - time.monotonic())
            return [event for event in self.events if event["id"] > since]

    def start(self, payload):
        with self.lock:
            if self.status in ("building", "running", "stopping"):
                raise ValueError("已有仿真正在运行")
            test_id = str(payload.get("test", "join03:accumulate"))
            if test_id not in TEST_BY_ID:
                raise ValueError("未知测试用例")
            params = validate_params(payload.get("params", {}))
            trace_interval = checked_int(payload.get("trace_interval", 25), 1, 10000,
                                         "TRACE_INTERVAL")
            delay_ms = checked_int(payload.get("delay_ms", 10), 0, 1000, "delay_ms")
            self.run_id += 1
            run_id = self.run_id
            self.status = "building"
            self.stop_requested = False
            self.current = {"test": test_id, "params": params,
                            "trace_interval": trace_interval, "delay_ms": delay_ms}
            self.events.clear()
            self.emit("status", status="building", message="正在准备仿真…", run_id=run_id)
            thread = threading.Thread(target=self._worker,
                                      args=(run_id, TEST_BY_ID[test_id], params,
                                            trace_interval, delay_ms), daemon=True)
            thread.start()
            return self.snapshot()

    def stop(self):
        with self.lock:
            if self.status not in ("building", "running"):
                return self.snapshot()
            self.stop_requested = True
            self.status = "stopping"
            proc = self.process
            self.emit("status", status="stopping", message="正在停止仿真…")
        if proc and proc.poll() is None:
            proc.terminate()
        return self.snapshot()

    def _set_process(self, proc):
        with self.lock:
            self.process = proc
            if self.stop_requested and proc.poll() is None:
                proc.terminate()

    def _run_stream(self, command, protocol=False, delay_ms=0):
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        proc = subprocess.Popen(command, cwd=str(ROOT), env=tool_environment(),
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                bufsize=1, creationflags=creationflags)
        self._set_process(proc)
        assert proc.stdout is not None
        for raw in proc.stdout:
            line = raw.rstrip("\r\n")
            if protocol and line.startswith("GUI|"):
                event = parse_protocol(line)
                self.emit(event.pop("type"), **event)
                if delay_ms:
                    time.sleep(delay_ms / 1000.0)
            elif line:
                self.emit("log", level="sim" if protocol else "build", message=line)
            with self.lock:
                if self.stop_requested and proc.poll() is None:
                    proc.terminate()
        code = proc.wait()
        with self.lock:
            self.process = None
        return code

    def _worker(self, run_id, test, params, trace_interval, delay_ms):
        try:
            image = ROOT / test["image"]
            if not image.is_file():
                if not test.get("buildable"):
                    raise RuntimeError("测试镜像不存在: " + str(image))
                self.emit("status", status="building", message="正在编译测试程序…")
                image.parent.mkdir(parents=True, exist_ok=True)
                prefix = TOOLCHAIN_BIN / "riscv-none-elf-"
                command = [sys.executable, str(ROOT / "tools" / "make_image.py"),
                           str(ROOT / test["source"]), "--arch", test["arch"],
                           "--out-dir", str(image.parent),
                           "--cc", str(prefix) + "gcc.exe",
                           "--objdump", str(prefix) + "objdump.exe",
                           "--objcopy", str(prefix) + "objcopy.exe",
                           "--readelf", str(prefix) + "readelf.exe"]
                if self._run_stream(command) != 0:
                    raise RuntimeError("测试程序编译失败")
            with self.lock:
                if self.stop_requested:
                    raise InterruptedError()

            BUILD_DIR.mkdir(parents=True, exist_ok=True)
            digest = hashlib.sha256(json.dumps(params, sort_keys=True).encode()).hexdigest()[:12]
            simulation = BUILD_DIR / ("cpu_gui_" + digest + ".vvp")
            sources = [ROOT / ".deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv",
                       ROOT / "tb" / "models" / "rv32im_memory_model.v",
                       ROOT / "tb" / "gui" / "cpu_core_gui_tb.v"]
            rtl_inputs = list((ROOT / "rtl").rglob("*.v"))
            rtl_inputs.extend((ROOT / "rtl").rglob("*.vh"))
            rtl_mtime = max(path.stat().st_mtime for path in
                            [ROOT / "rtl" / "filelist.f", *sources, *rtl_inputs])
            if not simulation.is_file() or simulation.stat().st_mtime < rtl_mtime:
                self.emit("status", status="building", message="正在编译参数化 RTL…")
                command = [str(OSS_BIN / "iverilog.exe"), "-g2012", "-Wall",
                           "-I", "rtl", "-s", "cpu_core_gui_tb", "-o", str(simulation)]
                for name, value in params.items():
                    command.extend(["-P", f"cpu_core_gui_tb.{name}={value}"])
                command.extend(["-c", "rtl/filelist.f",
                                ".deps/RISC-V-CPU-2026/scripts/ram/sram_fakeram.sv",
                                "tb/models/rv32im_memory_model.v",
                                "tb/gui/cpu_core_gui_tb.v"])
                if self._run_stream(command) != 0:
                    raise RuntimeError("RTL 编译失败")
            else:
                self.emit("log", level="build", message="复用已编译的参数配置 " + digest)

            with self.lock:
                if self.stop_requested:
                    raise InterruptedError()
                self.status = "running"
            self.emit("status", status="running", message="仿真运行中", run_id=run_id)
            command = [str(OSS_BIN / "vvp.exe"), "-N", str(simulation),
                       "+IMAGE=" + image.as_posix(), "+TEST=" + test["name"],
                       "+EXPECTED=" + str(test["expected"]),
                       "+MAX_CYCLES=" + str(test["max_cycles"]),
                       "+MAX_NO_RETIRE_CYCLES=100000",
                       "+TRACE_INTERVAL=" + str(trace_interval)]
            code = self._run_stream(command, protocol=True, delay_ms=delay_ms)
            with self.lock:
                stopped = self.stop_requested
                if self.run_id != run_id:
                    return
                if stopped:
                    self.status = "stopped"
                elif code == 0:
                    # The result event is authoritative; this status closes the stream.
                    self.status = "passed"
                else:
                    self.status = "failed"
            self.emit("status", status=self.status,
                      message="仿真已停止" if stopped else
                              ("测试通过" if code == 0 else f"仿真退出码 {code}"))
        except InterruptedError:
            with self.lock:
                self.status = "stopped"
            self.emit("status", status="stopped", message="仿真已停止")
        except Exception as exc:
            with self.lock:
                self.status = "failed"
            self.emit("error", message=str(exc))
            self.emit("status", status="failed", message="运行失败")


def checked_int(value, minimum, maximum, label):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{label} 必须是整数")
    if result < minimum or result > maximum:
        raise ValueError(f"{label} 必须在 {minimum}..{maximum} 之间")
    return result


def validate_params(raw):
    merged = {**AREA_PROFILE, **(raw if isinstance(raw, dict) else {})}
    result = {}
    for name, spec in PARAMETERS.items():
        if "values" in spec:
            value = checked_int(merged.get(name), min(spec["values"]), max(spec["values"]), name)
            if value not in spec["values"]:
                raise ValueError(f"{name} 只支持 {spec['values']}")
        else:
            value = checked_int(merged.get(name), spec["min"], spec["max"], name)
        result[name] = value
    if result["SERIAL_BACKEND"] and (result["FE_WIDTH"] != 1 or result["BE_WIDTH"] != 1):
        raise ValueError("串行后端要求 FE_WIDTH=1 且 BE_WIDTH=1")
    if result["ROB_ENTRIES"] & (result["ROB_ENTRIES"] - 1):
        raise ValueError("ROB_ENTRIES 必须是 2 的幂")
    return result


DECIMAL_FIELDS = {
    "cycle", "instret", "lane", "rd", "we", "store", "epoch", "stage",
    "op", "rs1", "rs2", "rob_occ", "rob_head", "rob_tail", "rs_occ",
    "lsq_occ", "free_phys", "branch_pending", "mdu_issue", "mdu_busy",
    "completion_occ", "frontend_stall", "if_req", "if_resp", "d_req",
    "d_resp", "load", "size", "error", "return", "expected", "fe", "be",
    "phys", "rob", "rs", "lsq", "caches", "predictor", "fq", "mul",
    "shift", "phys_tag", "checkpoint", "completion_bypass", "serial",
    "generation", "completion", "cycles",
}


def parse_protocol(line):
    parts = line.split("|")
    event = {"type": parts[1] if len(parts) > 1 else "log"}
    for token in parts[2:]:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        if key in DECIMAL_FIELDS:
            try:
                event[key] = int(value, 10)
            except ValueError:
                event[key] = value
        else:
            event[key] = value
    return event


def tool_environment():
    env = os.environ.copy()
    env["PATH"] = (str(OSS_BIN) + os.pathsep + str(OSS_ROOT / "lib") +
                   os.pathsep + str(TOOLCHAIN_BIN) + os.pathsep + env.get("PATH", ""))
    env["YOSYSHQ_ROOT"] = str(OSS_ROOT) + os.sep
    env["SSL_CERT_FILE"] = str(OSS_ROOT / "etc" / "cacert.pem")
    return env


MANAGER = SimulationManager()


class Handler(BaseHTTPRequestHandler):
    server_version = "RV32IM-GUI/1.0"

    def log_message(self, fmt, *args):
        if self.path.startswith("/api/events"):
            return
        super().log_message(fmt, *args)

    def json_response(self, data, status=HTTPStatus.OK):
        blob = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(blob)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(blob)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/config":
            self.json_response({"parameters": PARAMETERS, "profiles": PROFILES,
                                "tests": TESTS, "status": MANAGER.snapshot(),
                                "frozen": ["Pi 长测试", "LH/LHU/SH 半字链路"]})
            return
        if parsed.path == "/api/status":
            self.json_response(MANAGER.snapshot())
            return
        if parsed.path == "/api/events":
            query = urllib.parse.parse_qs(parsed.query)
            try:
                since = int(query.get("since", ["0"])[0])
            except ValueError:
                since = 0
            events = MANAGER.events_since(since)
            self.json_response({"events": events, "status": MANAGER.snapshot()})
            return
        path = "index.html" if parsed.path in ("", "/") else parsed.path.lstrip("/")
        target = (GUI_DIR / path).resolve()
        try:
            target.relative_to(GUI_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if not target.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content_types = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
        blob = target.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_types.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            if self.path == "/api/run":
                self.json_response(MANAGER.start(payload), HTTPStatus.ACCEPTED)
            elif self.path == "/api/stop":
                self.json_response(MANAGER.stop(), HTTPStatus.ACCEPTED)
            else:
                self.send_error(HTTPStatus.NOT_FOUND)
        except (ValueError, json.JSONDecodeError) as exc:
            self.json_response({"error": str(exc)}, HTTPStatus.BAD_REQUEST)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{server.server_address[1]}/"
    print("RV32IM GUI: " + url)
    print("Press Ctrl+C to stop.")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        MANAGER.stop()
        server.server_close()


if __name__ == "__main__":
    main()
