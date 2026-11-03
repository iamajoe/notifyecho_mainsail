from __future__ import annotations

import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "moonraker_component"))

from notifyecho.progress import ProgressTracker  # noqa: E402


class ProgressTrackerTest(unittest.TestCase):
    def test_crosses_each_milestone_once(self) -> None:
        tracker = ProgressTracker([25, 50, 75, 90])

        self.assertEqual(tracker.update(0.24), [])
        self.assertEqual(tracker.update(0.25), [25])
        self.assertEqual(tracker.update(0.30), [])
        self.assertEqual(tracker.update(0.51), [50])

    def test_multiple_milestones_in_one_update(self) -> None:
        tracker = ProgressTracker([25, 50, 75, 90])

        self.assertEqual(tracker.update(0.80), [25, 50, 75])

    def test_prime_suppresses_past_milestones(self) -> None:
        tracker = ProgressTracker([25, 50, 75, 90])
        tracker.prime(0.60)

        self.assertEqual(tracker.update(0.61), [])
        self.assertEqual(tracker.update(0.76), [75])

    def test_reset_allows_milestones_again(self) -> None:
        tracker = ProgressTracker([25, 50])
        tracker.update(0.50)
        tracker.reset()

        self.assertEqual(tracker.update(0.25), [25])

    def test_progress_decrease_clears_sent(self) -> None:
        tracker = ProgressTracker([25, 50])
        tracker.update(0.50)
        tracker.update(0.10)

        self.assertEqual(tracker.update(0.25), [25])

    def test_out_of_range_progress_is_clamped(self) -> None:
        tracker = ProgressTracker([25, 50, 75, 90])

        self.assertEqual(tracker.update(-1), [])
        self.assertEqual(tracker.update(2.0), [25, 50, 75, 90])
        self.assertEqual(tracker.update(3.0), [])

    def test_changing_milestones_keeps_only_valid_sent_entries(self) -> None:
        tracker = ProgressTracker([25, 50])
        tracker.update(0.50)
        tracker.set_milestones([25, 75])

        self.assertEqual(tracker.update(0.50), [])
        self.assertEqual(tracker.update(0.80), [75])


if __name__ == "__main__":
    unittest.main()
