"""Resolve generated names for protected and ordinary Verilator output."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET


class OrdinaryNames(dict):
    def __missing__(self, key):
        return key


def load_names(directory, prefix):
    directory = Path(directory)
    path = directory / (prefix + "__idmap.xml")
    if path.is_file():
        return {node.attrib["to"]: node.attrib["from"]
                for node in ET.parse(path).iter("map")}
    # Ordinary output keeps the RTL identifiers. Obtain specialized module
    # names from the generated symbol table; the callers still validate every
    # object, field and evaluation boundary before applying a scheduling cache.
    symbols = (directory / (prefix + "__Syms.h")).read_text()
    names = OrdinaryNames()
    for name in re.findall(r'#include "' + re.escape(prefix)
                           + r'_(rv32m_mdu_iterative__\w+)\.h"', symbols):
        names[name] = name
    return names
