#!/usr/bin/env python3
"""Focused H-03 checks for sparse image syntax and generated artifacts."""

import json
import os
import sys

from make_image import BuildError, MEMORY_SIZE, parse_image


def main():
    image = os.path.abspath(sys.argv[1])
    manifest = os.path.splitext(image)[0] + ".manifest.json"
    data = parse_image(image)
    if not data:
        raise BuildError("generated image is empty")
    if min(data) < 0 or max(data) >= MEMORY_SIZE:
        raise BuildError("generated image exceeds memory")
    with open(manifest, "r", encoding="utf-8") as stream:
        info = json.load(stream)
    if info["entry"] != "0x00000000":
        raise BuildError("manifest entry is not zero")
    if info["memory_size"] != MEMORY_SIZE:
        raise BuildError("manifest memory size mismatch")
    if info["halt_word"] != "0x0ff00513":
        raise BuildError("manifest HALT mismatch")
    external = os.path.abspath(os.path.join(os.path.dirname(os.path.dirname(image)), "..", "RISC-V-CPU-Simulator", "testcases", "naive.data"))
    if os.path.isfile(external):
        external_data = parse_image(external)
        if 0 not in external_data or 0x1000 not in external_data:
            raise BuildError("external sparse image lost a discontinuous segment")
    print("PASS: H-03 sparse image and manifest validation")


if __name__ == "__main__":
    try:
        main()
    except (BuildError, OSError, ValueError, json.JSONDecodeError) as exc:
        print("FAIL: {}".format(exc), file=sys.stderr)
        sys.exit(1)
