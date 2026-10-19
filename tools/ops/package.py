"""Build distributions or qualify installed artifacts in isolated offline Python.

Adapted from the recorded installed-wheel and isolated-runtime test owners.
"""

from tools.ops.container_guard import require_container

require_container()

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

from tools.dependencies.wheels import regular_file


def execute(arguments, *, cwd):
    subprocess.run(arguments, cwd=cwd, check=True, timeout=120)


def build():
    output = Path("/output")
    if any(output.iterdir()):
        raise ValueError("Cannot build package: output directory must be empty; retain or move previous artifacts explicitly.")
    with tempfile.TemporaryDirectory() as temporary:
        source = Path(temporary) / "source"
        source.mkdir()
        for name in ("pyproject.toml", "README.md", "MANIFEST.in"):
            shutil.copyfile(Path("/workspace") / name, source / name)
        shutil.copytree(Path("/workspace/src"), source / "src")
        shutil.copytree(Path("/workspace/docs"), source / "docs")
        execute(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                "import setuptools.build_meta as backend; backend.build_wheel('/output'); backend.build_sdist('/output')",
            ],
            cwd=source,
        )
    artifacts = sorted(output.iterdir())
    if len(artifacts) != 2 or len(list(output.glob("*.whl"))) != 1 or len(list(output.glob("*.tar.gz"))) != 1:
        raise ValueError("Cannot publish package: expected one wheel and one sdist.")
    manifest = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in artifacts}
    (output / "sha256.json").write_text(json.dumps(manifest, indent=2) + "\n")


def check():
    with tempfile.TemporaryDirectory() as temporary:
        captured = Path(temporary) / "artifacts"
        captured.mkdir()
        for source in Path("/artifacts").iterdir():
            with regular_file(source, 0) as reader, (captured / source.name).open("xb") as writer:
                shutil.copyfileobj(reader, writer)
        _check_captured_artifacts(captured)


def _check_captured_artifacts(artifacts):
    manifest = json.loads((artifacts / "sha256.json").read_bytes())
    if set(path.name for path in artifacts.iterdir()) != {*manifest, "sha256.json"}:
        raise ValueError("Cannot verify package: artifact inventory differs from the recorded build.")
    for name, digest in manifest.items():
        path = artifacts / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Cannot verify package: current artifact bytes differ from the recorded build.")
    wheels = list(artifacts.glob("*.whl"))
    sdists = list(artifacts.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise ValueError("Cannot verify package: exactly one wheel and one sdist are required.")
    wheel, sdist = wheels[0], sdists[0]
    expected_payload = {
        "signed_invoice/__init__.py",
        "signed_invoice/codec.py",
        "signed_invoice/errors.py",
        "signed_invoice/fields.py",
        "signed_invoice/payment.py",
        "signed_invoice/vectors/invoice.json",
    }
    with zipfile.ZipFile(wheel) as archive:
        payload = {name for name in archive.namelist() if ".dist-info/" not in name}
        if payload != expected_payload:
            raise ValueError("Cannot verify package: wheel contains an unexpected runtime payload.")
        original = {name: archive.read(name) for name in payload}
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with tarfile.open(sdist) as archive:
            members = archive.getmembers()
            if any(not (member.isdir() or member.isfile()) for member in members):
                raise ValueError("Cannot verify package: sdist members must be regular files or directories.")
            archive.extractall(root / "unpacked", filter="data")
        sources = list((root / "unpacked").iterdir())
        if len(sources) != 1 or not sources[0].is_dir():
            raise ValueError("Cannot verify package: sdist must contain exactly one source root.")
        source = sources[0]
        expected_source = {
            "MANIFEST.in",
            "README.md",
            "pyproject.toml",
            "PKG-INFO",
            "setup.cfg",
            "docs/index.md",
            "src/signed_invoice.egg-info/PKG-INFO",
            "src/signed_invoice.egg-info/SOURCES.txt",
            "src/signed_invoice.egg-info/dependency_links.txt",
            "src/signed_invoice.egg-info/requires.txt",
            "src/signed_invoice.egg-info/top_level.txt",
            *("src/" + name for name in expected_payload),
        }
        if {str(path.relative_to(source)) for path in source.rglob("*") if path.is_file()} != expected_source:
            raise ValueError("Cannot verify package: sdist contents differ from the declared source distribution.")
        execute(
            [
                sys.executable,
                "-I",
                "-m",
                "pip",
                "wheel",
                "--no-index",
                "--no-deps",
                "--no-build-isolation",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--wheel-dir",
                str(root / "rebuilt"),
                str(source),
            ],
            cwd=root,
        )
        rebuilt = list((root / "rebuilt").glob("*.whl"))
        if len(rebuilt) != 1:
            raise ValueError("Cannot verify package: rebuilding the sdist must produce exactly one wheel.")
        with zipfile.ZipFile(rebuilt[0]) as archive:
            payload = {name for name in archive.namelist() if ".dist-info/" not in name}
            if payload != expected_payload or any(archive.read(name) != data for name, data in original.items()):
                raise ValueError("Cannot verify package: sdist rebuilt wheel has different runtime contents.")
        runtime_root = Path("/runtime/environment")
        execute([sys.executable, "-I", "-m", "venv", str(runtime_root)], cwd=root)
        runtime = str(runtime_root / "bin/python")
        execute(
            [
                runtime,
                "-I",
                "-m",
                "pip",
                "install",
                "--no-index",
                "--no-cache-dir",
                "--disable-pip-version-check",
                "--only-binary=:all:",
                "--require-hashes",
                "--find-links",
                "/dependencies",
                "-r",
                "/input/runtime.lock",
            ],
            cwd=root,
        )
        code = """
import importlib.metadata
import importlib.resources
import importlib.util
import json
from pathlib import Path
import signed_invoice
from signed_invoice import decode_invoice, encode_invoice, invoice_hash, sign_invoice, verify_invoice, validate_payment_route
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
distribution = importlib.metadata.distribution('signed-invoice')
assert distribution.version == '0.1.0'
assert distribution.requires == ['cryptography==50.0.2']
assert distribution.metadata['Requires-Python'] == '>=3.12'
assert Path(signed_invoice.__file__).resolve().is_relative_to(Path(__import__('sys').prefix))
for forbidden in ('tools', 'tests', 'p2p_invoice', 'agent_mail', 'agent_mail_p2p'):
    assert importlib.util.find_spec(forbidden) is None, forbidden
vectors = json.loads(importlib.resources.files('signed_invoice').joinpath('vectors/invoice.json').read_bytes())
domain = vectors['invoicePrefixUtf8'].encode()
key = Ed25519PrivateKey.generate()
for case in vectors['cases']:
    raw = case['invoiceUtf8'].encode()
    fields = decode_invoice(raw)
    assert signed_invoice.require_merchant_id(fields['merchantId']) == fields['merchantId']
    assert signed_invoice.require_identifier(fields['invoiceId']) == fields['invoiceId']
    assert signed_invoice.require_evm_address(fields['customer']) == fields['customer']
    assert signed_invoice.require_asset(fields['asset']) == fields['asset']
    assert signed_invoice.require_uint256(fields['amount'], positive=True) == fields['amount']
    assert signed_invoice.require_deadline(fields['acceptBy']) == fields['acceptBy']
    assert raw == encode_invoice(fields)
    assert case['invoiceHash'] == invoice_hash(raw, domain=domain)
    assert raw == verify_invoice(sign_invoice(raw, key, domain=domain), domain=domain,
                                merchant_id=fields['merchantId'], merchant_key_id=fields['merchantKeyId'], public_key=key.public_key())
    validate_payment_route(raw, chain_id=fields['chainId'], payment_contract=fields['paymentContract'], asset=fields['asset'])
print('Installed distribution origin, metadata, resources and crypto round trip passed.')
"""
        for candidate in (wheel, rebuilt[0]):
            execute(
                [
                    runtime,
                    "-I",
                    "-m",
                    "pip",
                    "install",
                    "--force-reinstall",
                    "--no-index",
                    "--no-deps",
                    "--no-compile",
                    "--disable-pip-version-check",
                    "--no-cache-dir",
                    str(candidate),
                ],
                cwd=root,
            )
            execute([runtime, "-I", "-m", "pip", "--no-cache-dir", "check"], cwd=root)
            execute([runtime, "-I", "-B", "-c", code], cwd=root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check"))
    arguments = parser.parse_args()
    if arguments.action == "build":
        build()
    else:
        check()
