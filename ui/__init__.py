"""NEL browser interface package with the current UI enhancements applied."""

from . import server as server
from . import enhancements as _enhancements

_enhancements.apply(server)

__all__ = ["server"]
