# clock.py
# ------------------------------------------------------------
# The Pi has no real-time clock. After boot the time is restored from the
# last value saved by fake-hwclock, which can be hours or days old after a
# hard power cut, until NTP has synchronised.
#
# The kernel tracks whether the clock is synchronised. adjtimex() with
# modes=0 only reads that state, needs no privileges and works inside a
# container, because the clock is shared with the host.
# ------------------------------------------------------------

import ctypes
import ctypes.util

TIME_ERROR = 5  # adjtimex() return value: clock not synchronised

# struct timex is ~208 bytes on 64-bit Linux; a zeroed, oversized buffer is
# enough because modes=0 (the first field) means "read only".
_TIMEX_SIZE = 512

_libc = ctypes.CDLL(ctypes.util.find_library("c") or "libc.so.6", use_errno=True)


def is_clock_synchronized() -> bool:
    buf = ctypes.create_string_buffer(_TIMEX_SIZE)
    state = _libc.adjtimex(buf)
    if state < 0:
        # Unknown; do not block data collection on a failing syscall.
        return True
    return state != TIME_ERROR
