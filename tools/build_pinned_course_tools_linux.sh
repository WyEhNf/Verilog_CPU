#!/usr/bin/env bash
# Build the course-pinned hardware tools natively on Linux x86-64, without the
# course AppImage, Docker or root. Revisions are those of the upstream
# Dockerfile at framework 302f0cf3:
#   Yosys 70a11c6b (bundled ABC 8e401543), OpenSTA f89887b5, CUDD f54f5333,
#   Verilator v5.020, ASAP7 7.5-track r28 f970bd3c (five RVT TT NLDM libraries).
#
#   tools/build_pinned_course_tools_linux.sh <deps|yosys|asap7|sta|verilator|all> [prefix]
#
# `deps` installs bison, flex, Tcl, SWIG, Eigen, autotools, 7z and ccache into
# a private micromamba environment under the prefix. Host requirements: g++
# with C++17, make, cmake, git, curl, tar and zlib headers.
# The four tool builds are independent and may run in parallel after `deps`.
set -euo pipefail
part=${1:?Specify deps, yosys, asap7, sta, verilator or all}
T=${2:-$HOME/cpu2026-tools}
E=$T/mamba/envs/dev
JOBS=${JOBS:-$(nproc)}
mkdir -p "$T/src" "$T/bin"
export PATH=$E/bin:$T/bin:$PATH
export PKG_CONFIG_PATH=$E/lib/pkgconfig

fetch() { # directory url commit
    mkdir -p "$T/src/$1"; cd "$T/src/$1"
    if [ ! -d .git ]; then git init -q; git remote add origin "$2"; fi
    if [ "$(git rev-parse HEAD 2>/dev/null)" != "$3" ]; then
        git fetch -q --depth 1 origin "$3"; git checkout -q --detach FETCH_HEAD
    fi
}

build() {
case $1 in
deps)
    [ -x "$T/bin/micromamba" ] || (cd "$T" && curl -sL https://micro.mamba.pm/api/micromamba/linux-64/latest | tar -xj bin/micromamba)
    MAMBA_ROOT_PREFIX=$T/mamba "$T/bin/micromamba" create -y -q -n dev -c conda-forge \
        bison flex "tk=8.6" readline libffi swig eigen autoconf automake libtool p7zip zlib help2man ccache
    ln -sf "$E/bin/ccache" "$T/bin/ccache"
    # Yosys includes FlexLexer.h from the default search path.
    mkdir -p "$T/flexinc" && cp "$E/include/FlexLexer.h" "$T/flexinc/"
    ;;
yosys)
    fetch yosys https://github.com/YosysHQ/yosys.git 70a11c6bf0e8dd669f56c7da3587f78b405138e2
    git submodule update --init --recursive --depth 1
    [ -f Makefile.conf ] || make config-gcc
    export CPATH=$T/flexinc
    opts="PREFIX=$T/yosys ENABLE_TCL=0 ENABLE_READLINE=0 ENABLE_PLUGINS=0 ENABLE_ZLIB=1"
    make -j"$JOBS" $opts && make install $opts
    "$T/yosys/bin/yosys" -V
    ;;
asap7)
    mkdir -p "$T/asap7/lib"
    base=https://raw.githubusercontent.com/The-OpenROAD-Project/asap7sc7p5t_28/f970bd3c3292b79ae4d022a3ec80533534614066
    for name in AO_RVT_TT_nldm_211120 INVBUF_RVT_TT_nldm_220122 OA_RVT_TT_nldm_211120 \
                SEQ_RVT_TT_nldm_220123 SIMPLE_RVT_TT_nldm_211120; do
        curl -fL --retry 3 "$base/LIB/NLDM/asap7sc7p5t_$name.lib.7z" -o "$T/asap7/cells.7z"
        7z e -y -o"$T/asap7/lib" "$T/asap7/cells.7z" >/dev/null
    done
    rm -f "$T/asap7/cells.7z"
    (cd "$T/asap7" && sha256sum lib/*.lib | tee SHA256SUMS)
    ;;
sta)
    fetch cudd https://github.com/ivmai/cudd.git f54f533303640afd5dbe47a05ebeabb3066f2a25
    autoreconf -fi && ./configure --prefix="$T/cudd" --enable-shared=no && make -j"$JOBS" && make install
    fetch opensta https://github.com/The-OpenROAD-Project/OpenSTA.git f89887b59600cd3a2a10c3de31bda4235d904cdf
    cmake -S . -B build -DCMAKE_BUILD_TYPE=Release -DCUDD_DIR="$T/cudd" -DCMAKE_INSTALL_PREFIX="$T/opensta" \
        -DUSE_TCL_READLINE=OFF -DBUILD_TESTS=OFF -DCMAKE_PREFIX_PATH="$E" \
        -DTCL_LIBRARY="$E/lib/libtcl8.6.so" -DTCL_HEADER="$E/include/tcl.h" -DTCL_INCLUDE_PATH="$E/include" \
        -DCMAKE_INSTALL_RPATH="$E/lib" -DCMAKE_BUILD_RPATH="$E/lib"
    cmake --build build -j"$JOBS" && cmake --install build
    "$T/opensta/bin/sta" -version
    ;;
verilator)
    mkdir -p "$T/src/verilator"; cd "$T/src/verilator"
    [ -d .git ] || git clone -q --depth 1 --branch v5.020 https://github.com/verilator/verilator.git .
    unset VERILATOR_ROOT
    autoconf && ./configure --prefix="$T/verilator" CPPFLAGS="-I$E/include" && make -j"$JOBS" && make install
    "$T/verilator/bin/verilator" --version
    ;;
*)
    echo "unknown part: $1" >&2; exit 2 ;;
esac
}

if [ "$part" = all ]; then
    for step in deps yosys asap7 sta verilator; do (build "$step"); done
    cat <<EOF

Use the tools with (the repository path must not contain spaces):
  export PATH=$T/bin:\$PATH CPU2026_REAL_VERILATOR=$T/verilator/bin/verilator
  make synth APPIMAGE= YOSYS=$T/yosys/bin/yosys ABC=$T/yosys/bin/yosys-abc STA=$T/opensta/bin/sta ASAP7_LIB=$T/asap7/lib
  make build APPIMAGE= CPU2026_PGO=0
EOF
else
    build "$part"
fi
