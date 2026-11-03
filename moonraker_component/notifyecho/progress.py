from __future__ import annotations

from typing import Iterable, List, Set


class ProgressTracker:
    """Tracks which progress milestones have already been emitted for a job.

    Kept free of Moonraker imports so the crossing logic is unit-testable.
    """

    def __init__(self, milestones: Iterable[int]) -> None:
        self._milestones: List[int] = []
        self._sent: Set[int] = set()
        self._last: float = 0.0
        self.set_milestones(milestones)

    def set_milestones(self, milestones: Iterable[int]) -> None:
        self._milestones = sorted({int(item) for item in milestones if 1 <= int(item) <= 100})
        self._sent = {item for item in self._sent if item in self._milestones}

    def reset(self) -> None:
        self._sent.clear()
        self._last = 0.0

    def prime(self, progress: float) -> None:
        """Mark milestones at or below the current progress as already sent.

        Used when the component starts mid-print, so it does not replay every
        milestone the print already passed.
        """
        value = _clamp(progress)
        for milestone in self._milestones:
            if milestone <= value * 100.0:
                self._sent.add(milestone)
        self._last = value

    def update(self, progress: float) -> List[int]:
        value = _clamp(progress)
        if value + 0.001 < self._last:
            # A progress reset normally means a new print began.
            self._sent.clear()
        self._last = value

        crossed: List[int] = []
        percent = value * 100.0
        for milestone in self._milestones:
            if milestone <= percent and milestone not in self._sent:
                self._sent.add(milestone)
                crossed.append(milestone)
        return crossed


def _clamp(progress: float) -> float:
    try:
        value = float(progress)
    except (TypeError, ValueError):
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
