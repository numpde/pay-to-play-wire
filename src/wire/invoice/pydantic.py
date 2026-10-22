"""Optional invoice field integration; authenticate with verify_invoice explicitly."""

from typing import Annotated

from wire._pydantic import ArtifactSchema

from .jws import SignedInvoice

SignedInvoiceValue = Annotated[SignedInvoice, ArtifactSchema(SignedInvoice)]
