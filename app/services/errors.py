
class ServiceOverloadedError(Exception):
    """The extraction service cannot admit another job."""


class ExtractionTimeoutError(Exception):
    """The HTTP wait budget for extraction expired."""
