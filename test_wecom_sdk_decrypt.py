from __future__ import annotations

import argparse
import base64
import ctypes
import json
import sys
from pathlib import Path

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


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
    lib.DecryptData.argtypes = [ctypes.c_char_p, ctypes.c_char_p, SLICE_PTR]
    lib.DecryptData.restype = ctypes.c_int
    return lib


def load_private_key(private_key_path: str):
    key_bytes = Path(private_key_path).read_bytes()
    return serialization.load_pem_private_key(key_bytes, password=None)


def decrypt_random_key(private_key_path: str, encrypted_random_key: str, publickey_ver: int) -> str:
    if int(publickey_ver) != 1:
        raise RuntimeError(f"unsupported publickey_ver: {publickey_ver}")

    private_key = load_private_key(private_key_path)
    cipher_bytes = base64.b64decode(encrypted_random_key)
    paddings = [
        ("PKCS1v15", padding.PKCS1v15()),
        (
            "OAEP-SHA1",
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA1()),
                algorithm=hashes.SHA1(),
                label=None,
            ),
        ),
        (
            "OAEP-SHA256",
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None,
            ),
        ),
    ]

    last_error = None
    for name, rsa_padding in paddings:
        try:
            plain = private_key.decrypt(cipher_bytes, rsa_padding)
            random_key = plain.decode("utf-8")
            print(f"decrypt_random_key success with {name}")
            return random_key
        except Exception as exc:
            last_error = exc

    raise RuntimeError(f"failed to decrypt random key: {last_error}")


def get_slice_text(lib, slice_ptr: SLICE_PTR) -> str:
    raw = lib.GetContentFromSlice(slice_ptr)
    return raw.decode("utf-8") if raw else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Minimal WeCom Finance SDK decrypt test")
    parser.add_argument("--lib-path", default="/home/ubuntu/wecom-sdk/C_sdk/libWeWorkFinanceSdk_C.so")
    parser.add_argument("--private-key-path", default="/home/ubuntu/wecom_private_key.pem")
    parser.add_argument("--corp-id", required=True)
    parser.add_argument("--secret", required=True)
    parser.add_argument("--seq", type=int, default=0)
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    lib = configure_sdk(args.lib_path)
    sdk_ptr = None
    chat_slice = None
    decrypt_slice = None

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

        chat_slice = lib.NewSlice()
        print(f"NewSlice(chat) ptr={chat_slice!r}")
        if not chat_slice:
            print("NewSlice for GetChatData returned null")
            return 4

        get_ret = lib.GetChatData(
            sdk_ptr,
            args.seq,
            args.limit,
            None,
            None,
            args.timeout,
            chat_slice,
        )
        print(f"GetChatData ret={get_ret}")
        if get_ret != 0:
            return get_ret or 5

        chat_text = get_slice_text(lib, chat_slice)
        print("GetChatData raw:")
        print(chat_text or "<empty>")
        payload = json.loads(chat_text or "{}")
        chatdata = payload.get("chatdata") or []
        if not chatdata:
            print("chatdata is empty")
            return 6

        first = chatdata[0]
        print("First chatdata record:")
        print(json.dumps(first, ensure_ascii=False, indent=2))

        publickey_ver = int(first.get("publickey_ver", 0))
        print(f"publickey_ver={publickey_ver}")

        random_key = decrypt_random_key(
            args.private_key_path,
            first["encrypt_random_key"],
            publickey_ver,
        )
        print(f"random_key_length={len(random_key)}")

        decrypt_slice = lib.NewSlice()
        print(f"NewSlice(decrypt) ptr={decrypt_slice!r}")
        if not decrypt_slice:
            print("NewSlice for DecryptData returned null")
            return 7

        print("Calling DecryptData...")
        decrypt_ret = lib.DecryptData(
            random_key.encode("utf-8"),
            first["encrypt_chat_msg"].encode("utf-8"),
            decrypt_slice,
        )
        print(f"DecryptData ret={decrypt_ret}")
        if decrypt_ret != 0:
            return decrypt_ret or 8

        plain_text = get_slice_text(lib, decrypt_slice)
        print("DecryptData raw:")
        print(plain_text or "<empty>")

        plain_json = json.loads(plain_text or "{}")
        print("DecryptData parsed JSON:")
        print(json.dumps(plain_json, ensure_ascii=False, indent=2))
        return 0
    finally:
        if decrypt_slice:
            lib.FreeSlice(decrypt_slice)
            print("FreeSlice(decrypt) done")
        if chat_slice:
            lib.FreeSlice(chat_slice)
            print("FreeSlice(chat) done")
        if sdk_ptr:
            lib.DestroySdk(sdk_ptr)
            print("DestroySdk done")


if __name__ == "__main__":
    sys.exit(main())
