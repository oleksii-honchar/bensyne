"""Filesystem birth time (crtime) via statx(2) — DEC-A2 age fallback.

Linux-only. Any failure (non-Linux host, statx unavailable, filesystem without
crtime, bad path) degrades to None — callers must treat None as "age unknown",
never as an error.
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
from pathlib import Path

# statx(2) constants (linux/stat.h)
AT_FDCWD = -100
AT_EMPTY_PATH = 0x1000
STX_BTIME = 0x800
# syscall numbers where a libc statx wrapper may be absent
_SYS_STATX = {"x86_64": 332, "aarch64": 291}


class _StatxTimestamp(ctypes.Structure):
    _fields_ = [
        ("tv_sec", ctypes.c_int64),
        ("tv_nsec", ctypes.c_uint32),
        ("__reserved", ctypes.c_int32),
    ]


class _Statx(ctypes.Structure):
    _fields_ = [
        ("stx_mask", ctypes.c_uint32),
        ("stx_blksize", ctypes.c_uint32),
        ("stx_attributes", ctypes.c_uint64),
        ("stx_nlink", ctypes.c_uint32),
        ("stx_uid", ctypes.c_uint32),
        ("stx_gid", ctypes.c_uint32),
        ("stx_mode", ctypes.c_uint16),
        ("__spare0", ctypes.c_uint16),
        ("stx_ino", ctypes.c_uint64),
        ("stx_size", ctypes.c_uint64),
        ("stx_blocks", ctypes.c_uint64),
        ("stx_attributes_mask", ctypes.c_uint64),
        ("stx_atime", _StatxTimestamp),
        ("stx_btime", _StatxTimestamp),
        ("stx_ctime", _StatxTimestamp),
        ("stx_mtime", _StatxTimestamp),
        ("stx_rdev_major", ctypes.c_uint32),
        ("stx_rdev_minor", ctypes.c_uint32),
        ("stx_dev_major", ctypes.c_uint32),
        ("stx_dev_minor", ctypes.c_uint32),
        ("stx_mnt_id", ctypes.c_uint64),
        ("stx_dio_mem_align", ctypes.c_uint32),
        ("stx_dio_offset_align", ctypes.c_uint32),
        ("__spare3", ctypes.c_uint64 * 12),
    ]


def get_birth_time(path: str | Path) -> float | None:
    """Return the birth time (crtime) of path as an epoch float, or None.

    Never raises: any failure (non-Linux platform, missing statx, filesystem
    without crtime, invalid path) returns None.
    """
    if sys.platform != "linux":
        return None
    try:
        target = os.fspath(path)
        buf = _Statx()
        libc = ctypes.CDLL(None, use_errno=True)
        if hasattr(libc, "statx"):
            ret = libc.statx(
                AT_FDCWD, target, AT_EMPTY_PATH, STX_BTIME, ctypes.byref(buf)
            )
        else:
            syscall_no = _SYS_STATX.get(platform.machine())
            if syscall_no is None:
                return None
            ret = libc.syscall(
                ctypes.c_long(syscall_no),
                AT_FDCWD,
                target,
                ctypes.c_uint(AT_EMPTY_PATH),
                ctypes.c_uint(STX_BTIME),
                ctypes.byref(buf),
            )
        if ret != 0 or not (buf.stx_mask & STX_BTIME):
            return None
        return float(buf.stx_btime.tv_sec) + buf.stx_btime.tv_nsec / 1e9
    except (OSError, ValueError, AttributeError):
        return None
