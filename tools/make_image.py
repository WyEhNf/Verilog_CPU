#!/usr/bin/env python3
"""Build a freestanding RV32I/RV32IM program and emit an @address byte image."""

import argparse
import hashlib
import json
import os
import shlex
import struct
import subprocess
import sys

MEMORY_SIZE = 1 << 20
HALT_WORD = 0x0FF00513
HALT_BYTES = struct.pack("<I", HALT_WORD)
PT_LOAD = 1
PF_X = 1
EM_RISCV = 243


class BuildError(Exception):
    pass


def run(command, output=None):
    print("+ " + " ".join(shlex.quote(str(item)) for item in command))
    try:
        return subprocess.run(command, check=True, stdout=output)
    except OSError as exc:
        raise BuildError("cannot execute {}: {}".format(command[0], exc))
    except subprocess.CalledProcessError as exc:
        raise BuildError("command failed with status {}".format(exc.returncode))


def parse_elf(path):
    with open(path, "rb") as stream:
        blob = stream.read()
    if len(blob) < 52 or blob[:4] != b"\x7fELF" or blob[4:6] != b"\x01\x01":
        raise BuildError("{} is not a little-endian ELF32".format(path))
    fields = struct.unpack_from("<16sHHIIIIIHHHHHH", blob, 0)
    _, _, machine, _, entry, phoff, _, _, _, phentsize, phnum, _, _, _ = fields
    if machine != EM_RISCV:
        raise BuildError("{} is not an RISC-V ELF".format(path))
    if phentsize < 32 or phoff + phentsize * phnum > len(blob):
        raise BuildError("invalid ELF program headers")
    segments = []
    for index in range(phnum):
        offset = phoff + index * phentsize
        p_type, p_offset, p_vaddr, p_paddr, p_filesz, p_memsz, p_flags, p_align = struct.unpack_from(
            "<IIIIIIII", blob, offset)
        if p_type != PT_LOAD:
            continue
        address = p_paddr
        end = address + p_memsz
        if p_filesz > p_memsz or p_offset + p_filesz > len(blob):
            raise BuildError("invalid ELF load segment {}".format(index))
        if end < address or end > MEMORY_SIZE:
            raise BuildError("ELF segment exceeds 1 MiB: 0x{:08x}".format(end))
        segments.append({
            "address": address,
            "file_size": p_filesz,
            "memory_size": p_memsz,
            "flags": p_flags,
            "align": p_align,
            "data": blob[p_offset:p_offset + p_filesz],
        })
    segments.sort(key=lambda item: item["address"])
    previous_end = 0
    for segment in segments:
        if segment["address"] < previous_end:
            raise BuildError("overlapping ELF load segments")
        previous_end = segment["address"] + segment["memory_size"]
    if entry >= MEMORY_SIZE:
        raise BuildError("entry is outside 1 MiB")
    if not any(item["address"] <= entry < item["address"] + item["memory_size"] and item["flags"] & PF_X
               for item in segments):
        raise BuildError("entry is not in an executable segment")
    return {"entry": entry, "segments": segments}


def halt_address(info):
    for segment in info["segments"]:
        if not (segment["flags"] & PF_X):
            continue
        index = segment["data"].find(HALT_BYTES)
        if index >= 0 and (segment["address"] + index) % 4 == 0:
            return segment["address"] + index
    return None


def write_image(path, info):
    with open(path, "w", encoding="ascii") as stream:
        for segment in info["segments"]:
            if not segment["file_size"]:
                continue
            stream.write("@{:08X}\n".format(segment["address"]))
            data = segment["data"]
            for offset in range(0, len(data), 16):
                stream.write("{}\n".format(" ".join("{:02X}".format(value) for value in data[offset:offset + 16])))


def parse_image(path):
    memory = {}
    address = None
    with open(path, "r", encoding="ascii") as stream:
        for line_number, line in enumerate(stream, 1):
            tokens = line.split()
            if not tokens:
                continue
            if tokens[0].startswith("@"):
                if len(tokens) != 1:
                    raise BuildError("image line {} has data after address".format(line_number))
                try:
                    address = int(tokens[0][1:], 16)
                except ValueError:
                    raise BuildError("invalid image address on line {}".format(line_number))
                continue
            if address is None:
                raise BuildError("image data precedes an address")
            for token in tokens:
                if len(token) != 2:
                    raise BuildError("image token is not a byte on line {}".format(line_number))
                value = int(token, 16)
                if address >= MEMORY_SIZE:
                    raise BuildError("image exceeds 1 MiB")
                memory[address] = value
                address += 1
    return memory


def digest(path):
    hasher = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--extra-source", action="append", default=[],
                        help="additional C or assembly source (repeatable)")
    parser.add_argument("--include", action="append", default=[],
                        help="additional include directory (repeatable)")
    parser.add_argument("--define", action="append", default=[],
                        help="preprocessor definition (repeatable)")
    parser.add_argument("--arch", choices=("rv32i", "rv32im"), default="rv32i")
    parser.add_argument("--abi", default="ilp32")
    parser.add_argument("--out-dir", default=None)
    parser.add_argument("--cc", default=None)
    parser.add_argument("--objdump", default=None)
    parser.add_argument("--objcopy", default=None)
    parser.add_argument("--readelf", default=None)
    parser.add_argument("--linker-script", default=None,
                        help="linker script (defaults to tools/link.ld)")
    args = parser.parse_args(argv)
    if args.abi != "ilp32":
        raise BuildError("only ilp32 is supported")
    sources = [os.path.abspath(args.source)] + [os.path.abspath(item) for item in args.extra_source]
    for source in sources:
        if not os.path.isfile(source):
            raise BuildError("source does not exist: {}".format(source))
    source = sources[0]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    stem = os.path.splitext(os.path.basename(source))[0]
    out_dir = os.path.abspath(args.out_dir or os.path.join(root, "build", "images", stem + "-" + args.arch))
    os.makedirs(out_dir, exist_ok=True)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    linker_script = os.path.abspath(args.linker_script or os.path.join(script_dir, "link.ld"))
    if not os.path.isfile(linker_script):
        raise BuildError("linker script does not exist: {}".format(linker_script))
    prefix = os.environ.get("RISCV_PREFIX", "riscv-none-elf-")
    cc = args.cc or os.environ.get("RISCV_GCC", prefix + "gcc")
    objdump = args.objdump or os.environ.get("RISCV_OBJDUMP", prefix + "objdump")
    objcopy = args.objcopy or os.environ.get("RISCV_OBJCOPY", prefix + "objcopy")
    readelf = args.readelf or os.environ.get("RISCV_READELF", prefix + "readelf")
    source_objects = []
    startup_object = os.path.join(out_dir, "startup.o")
    runtime_object = os.path.join(out_dir, "runtime.o")
    elf = os.path.join(out_dir, stem + ".elf")
    binary = os.path.join(out_dir, stem + ".bin")
    dump = os.path.join(out_dir, stem + ".dump")
    readelf_file = os.path.join(out_dir, stem + ".readelf")
    map_file = os.path.join(out_dir, stem + ".map")
    image = os.path.join(out_dir, stem + ".image")
    manifest = os.path.join(out_dir, stem + ".manifest.json")
    common = ["-march=" + args.arch, "-mabi=" + args.abi, "-mno-relax", "-ffreestanding", "-fno-builtin",
              "-fno-stack-protector", "-fno-pic", "-fno-pie", "-fno-asynchronous-unwind-tables",
              "-fno-unwind-tables", "-ffunction-sections", "-fdata-sections"]
    common += ["-I" + os.path.abspath(item) for item in args.include]
    common += ["-D" + item for item in args.define]
    for index, item in enumerate(sources):
        object_stem = os.path.splitext(os.path.basename(item))[0]
        object_path = os.path.join(out_dir, "source-{:02d}-{}.o".format(index, object_stem))
        run([cc] + common + ["-O2", "-c", item, "-o", object_path])
        source_objects.append(object_path)
    run([cc] + common + ["-c", os.path.join(script_dir, "startup.S"), "-o", startup_object])
    run([cc] + common + ["-O2", "-c", os.path.join(script_dir, "runtime.c"), "-o", runtime_object])
    run([cc] + common + ["-nostdlib", "-nostartfiles", "-nodefaultlibs", "-Wl,-T," + linker_script,
                        "-Wl,-Map," + map_file, "-Wl,--gc-sections", "-Wl,--build-id=none",
                        "-Wl,--no-warn-rwx-segments", startup_object] + source_objects +
        [runtime_object, "-lgcc", "-o", elf])
    run([objcopy, "-O", "binary", "--gap-fill", "0", elf, binary])
    with open(dump, "w", encoding="utf-8") as stream:
        run([objdump, "-d", elf], output=stream)
    with open(readelf_file, "w", encoding="utf-8") as stream:
        run([readelf, "-h", "-l", "-S", elf], output=stream)
    info = parse_elf(elf)
    halt = halt_address(info)
    if info["entry"] != 0:
        raise BuildError("entry must be zero, got 0x{:08x}".format(info["entry"]))
    if halt is None:
        raise BuildError("HALT instruction 0x{:08x} is absent".format(HALT_WORD))
    write_image(image, info)
    image_bytes = parse_image(image)
    if image_bytes.get(halt) != HALT_BYTES[0]:
        raise BuildError("generated image failed HALT round-trip")
    files = {"source": source, "linker_script": linker_script,
             "startup_object": startup_object, "runtime_object": runtime_object,
             "elf": elf, "binary": binary, "dump": dump, "readelf": readelf_file, "map": map_file, "image": image}
    for index, object_path in enumerate(source_objects):
        files["source_object_{}".format(index)] = object_path
    manifest_data = {
        "format": "verilog-cpu-image-v1", "arch": args.arch, "abi": args.abi,
        "memory_size": MEMORY_SIZE, "entry": "0x{:08x}".format(info["entry"]),
        "halt_word": "0x{:08x}".format(HALT_WORD), "halt_address": "0x{:08x}".format(halt),
        "segments": [{"address": "0x{:08x}".format(s["address"]), "file_size": s["file_size"], "memory_size": s["memory_size"], "flags": s["flags"]}
                     for s in info["segments"]],
        "files": {key: {"path": os.path.basename(value), "sha256": digest(value)} for key, value in files.items()},
    }
    with open(manifest, "w", encoding="utf-8") as stream:
        json.dump(manifest_data, stream, indent=2, sort_keys=True)
        stream.write("\n")
    print("generated {}".format(image))
    print("entry=0x{:08x} halt=0x{:08x} segments={} high_water=0x{:08x}".format(
        info["entry"], halt, len(info["segments"]), max(s["address"] + s["memory_size"] for s in info["segments"])))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except BuildError as exc:
        print("error: {}".format(exc), file=sys.stderr)
        sys.exit(2)
