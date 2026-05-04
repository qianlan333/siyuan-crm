from __future__ import annotations

import base64
import hashlib
import os
import socket
import struct
import time
import xml.etree.ElementTree as ET

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from flask import current_app

from .infra.settings import get_setting


class WeComCallbackError(RuntimeError):
    pass


BLOCK_SIZE = 32


def get_callback_config() -> dict[str, str]:
    return {
        "corp_id": get_setting("WECOM_CORP_ID") or current_app.config["WECOM_CORP_ID"],
        "token": get_setting("WECOM_CALLBACK_TOKEN") or current_app.config["WECOM_CALLBACK_TOKEN"],
        "aes_key": get_setting("WECOM_CALLBACK_AES_KEY") or current_app.config["WECOM_CALLBACK_AES_KEY"],
    }


def _aes_key_bytes(aes_key: str) -> bytes:
    if not aes_key:
        raise WeComCallbackError("WECOM_CALLBACK_AES_KEY is not configured")
    return base64.b64decode(f"{aes_key}=")


def _pkcs7_unpad(data: bytes) -> bytes:
    pad_len = data[-1]
    if pad_len < 1 or pad_len > BLOCK_SIZE:
        raise WeComCallbackError("invalid PKCS7 padding")
    return data[:-pad_len]


def _pkcs7_pad(data: bytes) -> bytes:
    pad_len = BLOCK_SIZE - (len(data) % BLOCK_SIZE)
    if pad_len == 0:
        pad_len = BLOCK_SIZE
    return data + bytes([pad_len]) * pad_len


def compute_signature(token: str, timestamp: str, nonce: str, encrypted: str) -> str:
    parts = sorted([token, timestamp, nonce, encrypted])
    return hashlib.sha1("".join(parts).encode("utf-8")).hexdigest()


def verify_signature(token: str, timestamp: str, nonce: str, encrypted: str, signature: str) -> None:
    expected = compute_signature(token, timestamp, nonce, encrypted)
    if expected != signature:
        raise WeComCallbackError("invalid callback signature")


def decrypt_message(encrypted: str, aes_key: str, corp_id: str) -> str:
    key = _aes_key_bytes(aes_key)
    iv = key[:16]
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    decryptor = cipher.decryptor()
    decrypted = decryptor.update(base64.b64decode(encrypted)) + decryptor.finalize()
    plain = _pkcs7_unpad(decrypted)
    xml_length = socket.ntohl(struct.unpack("I", plain[16:20])[0])
    xml_bytes = plain[20 : 20 + xml_length]
    received_corp_id = plain[20 + xml_length :].decode("utf-8")
    if corp_id and received_corp_id != corp_id:
        raise WeComCallbackError("callback corp_id mismatch")
    return xml_bytes.decode("utf-8")


def encrypt_message(message: str, aes_key: str, corp_id: str) -> str:
    key = _aes_key_bytes(aes_key)
    iv = key[:16]
    random_bytes = os.urandom(16)
    message_bytes = message.encode("utf-8")
    corp_id_bytes = corp_id.encode("utf-8")
    payload = random_bytes + struct.pack("I", socket.htonl(len(message_bytes))) + message_bytes + corp_id_bytes
    padded = _pkcs7_pad(payload)
    cipher = Cipher(algorithms.AES(key), modes.CBC(iv))
    encryptor = cipher.encryptor()
    encrypted = encryptor.update(padded) + encryptor.finalize()
    return base64.b64encode(encrypted).decode("utf-8")


def parse_callback_xml(xml_text: str) -> dict[str, str]:
    root = ET.fromstring(xml_text)
    return {child.tag: (child.text or "") for child in root}


def build_encrypted_reply(message: str, token: str, aes_key: str, corp_id: str, nonce: str | None = None) -> str:
    timestamp = str(int(time.time()))
    reply_nonce = nonce or os.urandom(8).hex()
    encrypted = encrypt_message(message, aes_key, corp_id)
    signature = compute_signature(token, timestamp, reply_nonce, encrypted)
    reply_xml = ET.Element("xml")
    for tag, value in {
        "Encrypt": encrypted,
        "MsgSignature": signature,
        "TimeStamp": timestamp,
        "Nonce": reply_nonce,
    }.items():
        node = ET.SubElement(reply_xml, tag)
        node.text = value
    return ET.tostring(reply_xml, encoding="utf-8").decode("utf-8")
