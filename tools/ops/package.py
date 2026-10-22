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
import tomllib
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
        inventory = {
            path.relative_to(source).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sorted(source.rglob("*"))
            if path.is_file()
        }
        (output / "source.json").write_text(json.dumps(inventory, indent=2) + "\n")
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
    if len(artifacts) != 3 or len(list(output.glob("*.whl"))) != 1 or len(list(output.glob("*.tar.gz"))) != 1:
        raise ValueError("Cannot publish package: expected one wheel, one sdist and source.json.")
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
        for path in sorted(captured.iterdir()):
            print("QUALIFIED_SHA256", hashlib.sha256(path.read_bytes()).hexdigest(), path.name, flush=True)


def _wheel_payload(wheel, expected):
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        if len(set(names)) != len(names):
            raise ValueError("Cannot verify package: wheel contains duplicate member paths.")
        metadata_prefix = "wire-" + wheel.name.split("-")[1] + ".dist-info/"
        payload = {name for name in names if not name.startswith(metadata_prefix)}
        if payload != expected:
            raise ValueError("Cannot verify package: wheel runtime inventory differs from captured source metadata.")
        return {name: archive.read(name) for name in payload}


def _source_payload(source, inventory):
    """Check packaging against source inputs captured before the backend ran."""
    if type(inventory) is not dict or not inventory:
        raise ValueError("Cannot verify package: source inventory must be a nonempty path-to-SHA256 mapping.")
    for name, digest in inventory.items():
        if (
            type(name) is not str
            or not name
            or Path(name).as_posix() != name
            or Path(name).is_absolute()
            or ".." in Path(name).parts
            or not (name in {"README.md", "pyproject.toml", "MANIFEST.in"} or name.startswith(("src/wire/", "docs/")))
            or type(digest) is not str
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("Cannot verify package: source inventory contains an unsafe path or invalid SHA256.")
    project = tomllib.loads((source / "pyproject.toml").read_text())["project"]
    if project["name"] != "wire":
        raise ValueError("Cannot verify package: source distribution must declare the wire project.")
    # These are backend metadata, not a second list of package runtime members.
    metadata = "src/" + project["name"].replace("-", "_") + ".egg-info/"
    generated = {
        "PKG-INFO",
        "setup.cfg",
        *(metadata + name for name in ("PKG-INFO", "SOURCES.txt", "dependency_links.txt", "requires.txt", "top_level.txt")),
    }
    observed = {path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()}
    if observed != set(inventory) | generated:
        raise ValueError(
            "Cannot verify package: sdist source inventory differs from captured pre-build inputs and backend metadata."
        )
    for name, digest in inventory.items():
        if hashlib.sha256((source / name).read_bytes()).hexdigest() != digest:
            raise ValueError("Cannot verify package: sdist source bytes differ from captured pre-build inputs.")
    return project, {name.removeprefix("src/") for name in inventory if name.startswith("src/wire/")}


def _check_captured_artifacts(artifacts):
    manifest = json.loads((artifacts / "sha256.json").read_bytes())
    if any(Path(name).name != name for name in manifest):
        raise ValueError("Cannot verify package: artifact manifest names must be direct filenames.")
    if set(path.name for path in artifacts.iterdir()) != {*manifest, "sha256.json"}:
        raise ValueError("Cannot verify package: artifact inventory differs from the recorded build.")
    for name, digest in manifest.items():
        path = artifacts / name
        if path.is_symlink() or not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Cannot verify package: current artifact bytes differ from the recorded build.")
    wheels = list(artifacts.glob("*.whl"))
    sdists = list(artifacts.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1 or set(manifest) != {wheels[0].name, sdists[0].name, "source.json"}:
        raise ValueError("Cannot verify package: exactly one wheel, one sdist and source.json are required.")
    inventory = json.loads((artifacts / "source.json").read_bytes())
    wheel, sdist = wheels[0], sdists[0]
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        with tarfile.open(sdist) as archive:
            members = archive.getmembers()
            if any(not (member.isdir() or member.isfile()) for member in members):
                raise ValueError("Cannot verify package: sdist members must be regular files or directories.")
            if len({member.name for member in members}) != len(members):
                raise ValueError("Cannot verify package: sdist contains duplicate member paths.")
            archive.extractall(root / "unpacked", filter="data")
        sources = list((root / "unpacked").iterdir())
        if len(sources) != 1 or not sources[0].is_dir():
            raise ValueError("Cannot verify package: sdist must contain exactly one source root.")
        source = sources[0]
        project, expected_payload = _source_payload(source, inventory)
        original = _wheel_payload(wheel, expected_payload)
        if any(data != (source / "src" / name).read_bytes() for name, data in original.items()):
            raise ValueError("Cannot verify package: wheel runtime bytes differ from the captured source distribution.")
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
        if _wheel_payload(rebuilt[0], expected_payload) != original:
            raise ValueError("Cannot verify package: sdist rebuilt wheel has different runtime contents.")
        code = """
import importlib.metadata
import importlib.resources
import importlib.util
import json
import sys
from pathlib import Path
import wire
import wire.invoice as invoice
from wire.invoice import InvoiceError, JsonNumber, SignedInvoice, decode_invoice, encode_invoice, invoice_hash, sign_invoice, verify_invoice
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
import base64
distribution = importlib.metadata.distribution('wire')
project = json.loads(sys.argv[1])
profile = json.loads(sys.argv[2])
assert distribution.version == project['version']
expected_requires = project['dependencies'] + [
    requirement + '; extra == "' + extra + '"'
    for extra, requirements in project.get('optional-dependencies', {}).items() for requirement in requirements
]
assert distribution.requires == expected_requires
assert distribution.metadata.get_all('Provides-Extra') == list(project.get('optional-dependencies', {}))
assert distribution.metadata['Requires-Python'] == project['requires-python']
assert Path(wire.__file__).resolve().is_relative_to(Path(sys.prefix))
assert Path(invoice.__file__).resolve().is_relative_to(Path(sys.prefix))
for development_module in ('tools', 'tests', 'signed_invoice', 'signed_voucher'):
    assert importlib.util.find_spec(development_module) is None, f"Installed runtime can import development module {development_module!r}."
assert 'eth_account' not in sys.modules, 'Invoice imports eagerly loaded Ethereum support.'
assert 'pydantic' not in sys.modules, 'Invoice imports eagerly loaded the optional Pydantic adapter.'
if not profile:
    assert importlib.util.find_spec('pydantic') is None, 'Base installation unexpectedly includes Pydantic.'
if 'voucher' not in profile:
    assert importlib.util.find_spec('eth_account') is None, 'Installation without voucher unexpectedly includes Ethereum support.'
vectors = json.loads(importlib.resources.files('wire').joinpath('vectors/invoice.json').read_bytes())
json.loads(importlib.resources.files('wire').joinpath('vectors/voucher.json').read_bytes())
for obsolete in ('validate_payment_route', 'require_merchant_id', 'require_identifier',
                 'require_evm_address', 'require_uint256', 'require_deadline', 'NATIVE_ASSET',
                 'invoice_signing_message', 'sign_invoice_detached', 'encode_envelope', 'decode_envelope'):
    assert not hasattr(invoice, obsolete)
for case in vectors['cases']:
    raw = case['payloadUtf8'].encode()
    artifact = SignedInvoice(**case['invoice'])
    fields = decode_invoice(raw)
    assert invoice.require_public_key(fields['provider']) == fields['provider']
    assert invoice.require_public_key(fields['beneficiary']) == fields['beneficiary']
    assert invoice.require_asset(fields['payment']['asset']) == fields['payment']['asset']
    assert invoice.require_amount(fields['payment']['amount']) == fields['payment']['amount']
    assert invoice.require_best_before(fields['bestBefore']) == fields['bestBefore']
    assert raw == encode_invoice(fields)
    assert raw == artifact.payload_bytes
    assert case['compact'] == artifact.compact
    assert case['invoiceHash'] == invoice_hash(artifact)
    key = Ed25519PublicKey.from_public_bytes(base64.urlsafe_b64decode(fields['provider'] + '='))
    assert fields == verify_invoice(artifact, public_key=key)
    assert artifact == SignedInvoice.from_json(artifact.to_json())
    assert artifact == SignedInvoice.from_compact(artifact.compact)
    for service in (None, [], True, 'text', JsonNumber('1.234567890123456789e99999')):
        changed = dict(fields, bestBefore=0, service=service)
        assert service == decode_invoice(encode_invoice(changed))['service']
    other = Ed25519PrivateKey.generate()
    fresh = dict(fields, provider=base64.urlsafe_b64encode(other.public_key().public_bytes_raw()).rstrip(b'=').decode())
    fresh_raw = encode_invoice(fresh)
    assert fresh == verify_invoice(sign_invoice(fresh_raw, other), public_key=other.public_key())
    signature = base64.urlsafe_b64encode(other.sign(artifact.signing_input)).rstrip(b'=').decode()
    forged = SignedInvoice(artifact.protected, artifact.payload, signature)
    try:
        verify_invoice(forged, public_key=other.public_key())
    except InvoiceError:
        pass
    else:
        raise AssertionError('A different trusted key authenticated the named provider.')
    try:
        encode_invoice(dict(fields, version=2))
    except InvoiceError:
        pass
    else:
        raise AssertionError('A legacy version member was accepted.')
print('Installed core: origin, metadata, JWS vectors, full identity and provider binding passed.', profile)
"""
        optional_code = """
import importlib.resources
import json
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError
from wire.invoice import SignedInvoice
from wire.invoice.pydantic import SignedInvoiceValue
class Response(BaseModel):
    model_config = ConfigDict(strict=True, extra='forbid')
    invoice: SignedInvoiceValue
adapter = TypeAdapter(SignedInvoiceValue)
schema = adapter.json_schema()
assert schema['additionalProperties'] is False
assert set(schema['required']) == {'protected', 'payload', 'signature'}
vectors = json.loads(importlib.resources.files('wire').joinpath('vectors/invoice.json').read_bytes())
for case in vectors['cases']:
    artifact = SignedInvoice(**case['invoice'])
    response = Response(invoice=artifact)
    assert type(response.invoice) is SignedInvoice
    assert response.model_dump() == {'invoice': artifact.to_dict()}
    assert response == Response.model_validate_json(response.model_dump_json())
    assert adapter.validate_json(artifact.to_json()) == artifact
    try:
        adapter.validate_python(dict(artifact.to_dict(), signature='AA'))
    except ValidationError:
        pass
    else:
        raise AssertionError('Installed optional adapter accepted a malformed signature segment.')
print('Installed optional Pydantic adapter: strict core artifacts, JSON, schema and serialization passed.')
"""
        voucher_code = """
import importlib.resources
import json
from pathlib import Path
import sys
import wire.voucher as voucher
from wire.voucher import SignedVoucher, VoucherDomain, build_voucher_typed_data, sign_voucher, verify_voucher
assert Path(voucher.__file__).resolve().is_relative_to(Path(sys.prefix))
vectors = json.loads(importlib.resources.files('wire').joinpath('vectors/voucher.json').read_bytes())
domain = VoucherDomain(int(vectors['domain']['chainId']), bytes.fromhex(vectors['domain']['verifyingContract'][2:]))
for case in vectors['cases']:
    data = build_voucher_typed_data(domain=domain, customer=bytes.fromhex(vectors['customer'][2:]),
        channel_id=int(vectors['channelId']), cumulative_total=int(case['cumulativeTotal']), invoice_hash=bytes.fromhex(case['invoiceHash'][2:]))
    artifact = sign_voucher(data, bytes.fromhex(vectors['testPrivateKey'][2:]))
    assert artifact.typed_data == data
    assert case['digest'] == '0x' + artifact.digest.hex()
    assert artifact == SignedVoucher.from_json(artifact.to_json())
    assert verify_voucher(artifact, expected_domain=domain, expected_signer=bytes.fromhex(vectors['testSigner'][2:])) is None
    try:
        verify_voucher(artifact, expected_domain=domain, expected_signer=bytes(20))
    except ValueError:
        pass
    else:
        raise AssertionError('An unregistered key authenticated a voucher.')
    try:
        verify_voucher(artifact, expected_domain=VoucherDomain(domain.chain_id + 1, domain.verifying_contract),
            expected_signer=bytes.fromhex(vectors['testSigner'][2:]))
    except ValueError:
        pass
    else:
        raise AssertionError('A different trusted domain authenticated a voucher.')
print('Installed voucher: contract digest vectors, transport and explicit signer/domain verification passed.')
"""
        for candidate in (wheel, rebuilt[0]):
            for profile in ((), ("pydantic",), ("voucher",), ("pydantic", "voucher")):
                # Fresh environments prove each consumer dependency boundary for
                # both artifacts; no earlier profile can conceal missing closure.
                with tempfile.TemporaryDirectory(dir="/runtime") as environment:
                    runtime_root = Path(environment) / "environment"
                    execute([sys.executable, "-I", "-m", "venv", str(runtime_root)], cwd=root)
                    runtime = str(runtime_root / "bin/python")
                    locks = ("runtime", *profile)
                    extras = "[" + ",".join(profile) + "]" if profile else ""
                    requirement = (
                        f"wire{extras} @ {candidate.as_uri()}#sha256={hashlib.sha256(candidate.read_bytes()).hexdigest()}"
                    )
                    execute(
                        [
                            runtime,
                            "-I",
                            "-m",
                            "pip",
                            "install",
                            "--no-index",
                            "--no-cache-dir",
                            "--no-compile",
                            "--disable-pip-version-check",
                            "--only-binary=:all:",
                            "--require-hashes",
                            "--find-links",
                            "/dependencies",
                            *(argument for lock in locks for argument in ("-r", f"/input/{lock}.lock")),
                            requirement,
                        ],
                        cwd=root,
                    )
                    execute([runtime, "-I", "-m", "pip", "--no-cache-dir", "check"], cwd=root)
                    execute([runtime, "-I", "-B", "-c", code, json.dumps(project), json.dumps(profile)], cwd=root)
                    if "pydantic" in profile:
                        execute([runtime, "-I", "-B", "-c", optional_code], cwd=root)
                    if "voucher" in profile:
                        execute([runtime, "-I", "-B", "-c", voucher_code], cwd=root)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "check"))
    arguments = parser.parse_args()
    if arguments.action == "build":
        build()
    else:
        check()
