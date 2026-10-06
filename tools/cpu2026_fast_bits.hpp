#pragma once
// Same ceil(log2(value)) as Verilator, including zero and one. No RTL changes.
#include "verilated.h"
static_assert(sizeof(IData)==4 && sizeof(QData)==8,
              "unsupported Verilator scalar sizes");
inline IData cpu26_clog2_i(IData value) {
#if defined(__GNUC__) || defined(__clang__)
    return value<2 ? 0 : IData(32-__builtin_clz(value-1));
#else
    return VL_CLOG2_I(value);
#endif
}
inline IData cpu26_clog2_q(QData value) {
#if defined(__GNUC__) || defined(__clang__)
    return value<2 ? 0 : IData(64-__builtin_clzll(value-1));
#else
    return VL_CLOG2_Q(value);
#endif
}
