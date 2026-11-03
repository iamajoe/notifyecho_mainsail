from __future__ import annotations

from typing import Any


def load_component(config: Any) -> Any:
    # Imported lazily so importing the pure helper modules (settings, payload,
    # progress, client) never requires Moonraker to be importable.
    from .component import NotifyEcho

    return NotifyEcho(config)
