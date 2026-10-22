"""Acceptance field integration; authenticate with verify_acceptance explicitly."""

from typing import Annotated

from wire._pydantic import ArtifactSchema

from .jws import SignedAcceptance

SignedAcceptanceValue = Annotated[SignedAcceptance, ArtifactSchema(SignedAcceptance)]
