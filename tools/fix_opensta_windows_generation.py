"""Select native Tcl explicitly in CMake's generated Ninja command on Windows."""
import os
from pathlib import Path

assert os.name == 'nt'
build = Path('F:/CPU2026CourseTools/win54fc150/src/opensta-sparse/build-windows/build.ninja')
original = build.read_text()
old = r'&& etc\TclEncode.tcl '
new = r'&& F:/c26/msys64/mingw64/bin/tclsh86.exe etc\TclEncode.tcl '
assert original.count(old) == 1
build.with_suffix('.ninja.cmake_original').write_text(original)
fixed = original.replace(old, new)
old_messages = '&& '+str(build.parent.parent/'etc/FindMessages.tcl')+' '
new_messages = '&& F:/c26/msys64/mingw64/bin/tclsh86.exe '+str(build.parent.parent/'etc/FindMessages.tcl')+' '
assert fixed.count(old_messages) == 1
build.write_text(fixed.replace(old_messages, new_messages))
print('Native Tcl selected; original OpenSTA source and Tcl encoder unchanged')
