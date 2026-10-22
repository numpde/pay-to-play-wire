"""Installed public acceptance inputs; no live receipt or historical authority is implied."""

import json
from importlib.resources import files

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def vector():
    return json.loads(files("wire").joinpath("vectors/acceptance.json").read_bytes())


def receipt_key():
    return Ed25519PrivateKey.from_private_bytes(bytes.fromhex(vector()["testPrivateKey"]))


def document():
    return json.loads(vector()["cases"][0]["payloadUtf8"])
