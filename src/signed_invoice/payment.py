"""Compare invoice denomination with a trusted settlement deployment observation."""

from .codec import InvoiceError, decode_invoice


def validate_payment_route(raw: bytes, *, chain_id: str, payment_contract: str, asset: str) -> None:
    """Require the signed chain, contract and asset to match the supplied observation.

    Call after issuer verification. The caller owns RPC reads, a coherent
    checkpoint, deployment/code qualification, immutable denomination and
    transport support. This function compares those supplied facts; it proves
    none of their origins and performs no payment or channel admission.

    Each invoice fixes one selected payment option. It cannot authorize another
    asset, chain or core merely because an offer advertised several currencies.
    """
    if any(type(value) is not str for value in (chain_id, payment_contract, asset)):
        raise TypeError("Payment route validation requires canonical string observations for chain, contract and asset.")
    fields = decode_invoice(raw)
    for field, observed in (("chainId", chain_id), ("paymentContract", payment_contract), ("asset", asset)):
        if fields[field] != observed:
            raise InvoiceError(f"Cannot validate invoice payment route: {field} differs from the trusted deployment observation.")
