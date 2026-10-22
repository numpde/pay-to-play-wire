"""Optional voucher field integration; authenticate with verify_voucher explicitly."""

from typing import Annotated

from wire._pydantic import ArtifactSchema

from .codec import SignedVoucher

SignedVoucherValue = Annotated[SignedVoucher, ArtifactSchema(SignedVoucher)]
