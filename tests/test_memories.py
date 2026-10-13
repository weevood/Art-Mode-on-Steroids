"""Pure selection regression tests (no TV or Raspberry required)."""
import unittest
from datetime import date
from art_engine import priority


class AnniversaryPriorityTests(unittest.TestCase):
    def test_exact_anniversary(self):
        self.assertEqual(priority(date(2019, 10, 13), date(2026, 10, 13)), (0, 0))

    def test_year_boundary(self):
        self.assertEqual(priority(date(2020, 12, 31), date(2026, 1, 1)), (1, 1))
        self.assertEqual(priority(date(2020, 1, 1), date(2026, 12, 31)), (1, 1))

    def test_leap_day(self):
        self.assertEqual(priority(date(2020, 2, 29), date(2026, 2, 28)), (0, 0))

    def test_future_photo_not_prioritized(self):
        self.assertEqual(priority(date(2027, 10, 13), date(2026, 10, 13))[0], 6)

    def test_missing_date(self):
        self.assertEqual(priority(None, date(2026, 10, 13))[0], 6)

    def test_near_date(self):
        self.assertEqual(priority(date(2020, 10, 10), date(2026, 10, 13)), (2, 3))


if __name__ == "__main__":
    unittest.main()
