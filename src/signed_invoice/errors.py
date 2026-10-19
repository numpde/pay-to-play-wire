"""Protocol rejection shared by document and scalar validation."""


class InvoiceError(ValueError):
    """A supplied invoice value, document, envelope or signature is invalid."""
