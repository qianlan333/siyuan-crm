from __future__ import annotations

import argparse
import ctypes
import json
import sys
from pathlib import Path


SDK_PTR = ctypes.c_void_p
SLICE_PTR = ctypes.c_void_p


def configure_sdk(lib_path: str):
    if not Path(lib_path).exists():
        raise FileNotFoundError(f"SDK library not found: {lib_path}")

    lib = ctypes.CDLL(lib_path)
    lib.NewSdk.argtypes = []
    lib.NewSdk.restype = SDK_PTR
    lib.Init.argtypes = [SDK_PTR, ctypes.c_char_p, ctypes.c_char_p]
    lib.Init.restype = ctypes.c_int
    lib.DestroySdk.argtypes = [SDK_PTR]
    lib.DestroySdk.restype = None
    lib.NewSlice.argtypes = []
    lib.NewSlice.restype = SLICE_PTR
    lib.FreeSlice.argtypes = [SLICE_PTR]
    lib.FreeSlice.restype = None
    lib.GetChatData.argtypes = [
        SDK_PTR,
        ctypes.c_ulonglong,
        ctypes.c_uint,
        ctypes.c_char_p,
        ctypes.c_char_p,
        ctypes.c_int,
        SLICE_PTR,
    ]
    lib.GetChatData.restype = ctypes.c_int
    lib.GetContentFromSlice.argtypes = [SLICE_PTR]
    lib.GetContentFromSlice.restype = ctypes.c_char_p
    return lib


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal WeCom Finance SDK smoke test")
    parser.add_argument("--lib-path", default="/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so")
    parser.add_argument("--corp-id", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--seq", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    sdk_ptr = None
    slice_ptr = None
    lib = configure_sdk(args.lib_path)

    try:
        sdk_ptr = lib.NewSdk()
        print(f"NewSdk ptr={sdk_ptr!r}")
        if not sdk_ptr:
            print("NewSdk returned null")
            return 2

        init_ret = lib.Init(sdk_ptr, args.corp_id.encode("utf-8"), args.secret.encode("utf-8"))
        print(f"Init ret={init_ret}")
        if init_ret != 0:
            return init_ret or 3

        slice_ptr = lib.NewSlice()
        print(f"NewSlice ptr={slice_ptr!r}")
        if not slice_ptr:
            print("NewSlice returned null")
            return 4

        ret = lib.GetChatData(
            sdk_ptr,
            args.seq,
            args.limit,
            None,
            None,
            args.timeout,
            slice_ptr,
        )
        print(f"GetChatData ret={ret}")

        raw = lib.GetContentFromSlice(slice_ptr)
        raw_text = raw.decode("utf-8") if raw else ""
        print("GetChatData raw:")
        print(raw_text or "<empty>")

        if raw_text:
            try:
                parsed = json.loads(raw_text)
                print("GetChatData parsed:")
                print(json.dumps(parsed, ensure_ascii=False, indent=2))
            except json.JSONDecodeError:
                print("GetChatData raw is not valid JSON")

        return ret
    finally:
        if slice_ptr:
            lib.FreeSlice(slice_ptr)
            print("FreeSlice done")
        if sdk_ptr:
            lib.DestroySdk(sdk_ptr)
            print("DestroySdk done")


if __name__ == "__main__":
    sys.exit(main())
