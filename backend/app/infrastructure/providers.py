"""Load operator-selected, packaged adapters; never accept paths from HTTP input."""
from importlib import import_module
import re


def load_adapter(reference, settings, methods):
    if not isinstance(reference, str) or not re.fullmatch(
        r'[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*', reference, flags=re.ASCII
    ):
        raise ValueError('Adapter is not configured')
    module, name = reference.split(':')
    adapter = getattr(import_module(module), name)(settings)
    if any(not callable(getattr(adapter, method, None)) for method in methods):
        raise ValueError('Adapter does not implement the required interface')
    return adapter
