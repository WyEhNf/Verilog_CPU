#!/usr/bin/env bash
set -euo pipefail

# This script runs under Windows MSYS2 and produces native PE executables.
case "$(uname -s)" in MINGW*|MSYS*) ;; *) echo 'Windows build only' >&2; exit 2 ;; esac
part=${1:?Specify yosys, verilator or opensta}
base=/f/CPU2026CourseTools/win54fc150
sta_source="$base/src/opensta-sparse"
export PATH=/mingw64/bin:/usr/bin:/c/Git/cmd:$PATH
export TMPDIR=/f/CPU2026Temp
export LC_ALL=C.UTF-8
mkdir -p "$base/state"
verify() {
    test "$(git -C "$base/src/$1" rev-parse HEAD)" = "$2"
}
build_cudd() {
    verify cudd f54f533303640afd5dbe47a05ebeabb3066f2a25
    cd "$base/src/cudd"
    autoreconf -fi
    ./configure --host=x86_64-w64-mingw32 --prefix="$base/cudd" --enable-shared=no
    make -j2
    make install
    touch "$base/state/cudd.complete"
}

case "$part" in
    yosys)
        verify yosys 70a11c6bf0e8dd669f56c7da3587f78b405138e2
        test "$(git -C "$base/src/yosys/abc" rev-parse HEAD)" = 8e401543d3ecf65e3a3631c7a271793a4d356cb0
        cd "$base/src/yosys"
        printf 'CONFIG := msys2-64\nPREFIX := %s\nTCL_VERSION := tcl8.6\nCXXFLAGS += -IF:/CPU2026CourseTools/win54fc150/build-headers\nABCMKARGS += -f /e/Verilog_cpu/tools/abc_link_windows.mk\n' "$(cygpath -m "$base/yosys")" > Makefile.conf
        make -j2
        make install
        "$base/yosys/bin/yosys.exe" -V
        "$base/yosys/bin/yosys-abc.exe" -c version
        touch "$base/state/yosys.complete"
        ;;
    verilator)
        verify verilator 5c5314b39cd888f427807d626e1502cbf222c292
        cd "$base/src/verilator"
        mkdir -p "$base/build-headers"
        cp /usr/include/FlexLexer.h "$base/build-headers/"
        autoconf
        ./configure --host=x86_64-w64-mingw32 --prefix="$base/verilator" \
            CPPFLAGS="-I$(cygpath -m "$base/build-headers")"
        make -j2
        make install
        "$base/verilator/bin/verilator_bin.exe" --version
        touch "$base/state/verilator.complete"
        ;;
    cudd)
        build_cudd
        ;;
    opensta)
        verify opensta-sparse f89887b59600cd3a2a10c3de31bda4235d904cdf
        if [ ! -f "$base/state/cudd.complete" ]; then build_cudd; fi
        cmake -S "$(cygpath -m "$sta_source")" \
            -B "$(cygpath -m "$sta_source/build-windows")" -G Ninja \
            -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR="$(cygpath -m "$base/cudd")" \
            -DCMAKE_INSTALL_PREFIX="$(cygpath -m "$base/opensta")" \
            -DCMAKE_PREFIX_PATH="$(cygpath -m /mingw64)" \
            -DTCL_INCLUDE_PATH="$(cygpath -m /mingw64/include)" \
            -DTCL_LIBRARY="$(cygpath -m /mingw64/lib/libtcl86.dll.a)" \
            -DTCL_TCLSH="$(cygpath -m /mingw64/bin/tclsh86.exe)" \
            -DFLEX_EXECUTABLE="$(cygpath -m /usr/bin/flex.exe)" \
            -DFLEX_INCLUDE_DIR="$(cygpath -m "$base/build-headers")" \
            -DBISON_EXECUTABLE="$(cygpath -m /usr/bin/bison.exe)" \
            -DSWIG_EXECUTABLE="$(cygpath -m /mingw64/bin/swig.exe)" \
            -DUSE_TCL_READLINE=OFF -DBUILD_TESTS=OFF
        /c/Users/admin/miniconda3/python.exe /e/Verilog_cpu/tools/fix_opensta_windows_generation.py
        cmake --build "$(cygpath -m "$sta_source/build-windows")" -j2
        cmake --install "$(cygpath -m "$sta_source/build-windows")"
        "$base/opensta/bin/sta.exe" -version
        touch "$base/state/opensta.complete"
        ;;
    *) echo 'Unknown tool component' >&2; exit 2 ;;
esac
echo "DONE native Windows $part"
