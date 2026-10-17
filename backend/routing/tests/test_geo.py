from django.test import SimpleTestCase

from routing.geo import cumulative_miles, interpolate, sample_along


class SampleAlongTests(SimpleTestCase):
    def test_samples_every_interval_and_includes_destination(self) -> None:
        points = [(0.0, 0.0), (0.0, 1.0)]
        total = cumulative_miles(points)[-1]
        samples = sample_along(points, 25)
        self.assertEqual([m for m, _ in samples[:3]], [0, 25, 50])
        self.assertAlmostEqual(samples[-1][0], total)
        self.assertEqual(len(samples), 4)
        self.assertAlmostEqual(samples[1][1][1], 25 / total)

    def test_tiny_leftover_is_folded_into_destination(self) -> None:
        points = [(0.0, 0.0), (0.0, 1.0)]
        total = cumulative_miles(points)[-1]
        interval = total / 2.001
        samples = sample_along(points, interval)
        miles = [m for m, _ in samples]
        self.assertEqual(miles[:2], [0, interval])
        self.assertEqual(len(miles), 3)
        self.assertAlmostEqual(miles[-1], total)

    def test_interpolate_clamps_outside_range(self) -> None:
        self.assertEqual(interpolate([0, 10], [5, 15], -1), 5)
        self.assertEqual(interpolate([0, 10], [5, 15], 11), 15)
        self.assertEqual(interpolate([0, 10], [5, 15], 5), 10)
