from django.test import SimpleTestCase

from routing.risk import Risk, assess, classify_rain, classify_snow, classify_wind, risk_score


class ThresholdTests(SimpleTestCase):
    def assert_bands(self, classify, cases: list[tuple[float, Risk]]) -> None:
        for value, expected in cases:
            with self.subTest(value=value):
                self.assertEqual(classify(value), expected)

    def test_wind_bands(self) -> None:
        self.assert_bands(classify_wind, [
            (24.9, Risk.LOW), (25, Risk.MODERATE), (34.9, Risk.MODERATE), (35, Risk.HIGH),
            (44.9, Risk.HIGH), (45, Risk.SEVERE), (54.9, Risk.SEVERE), (55, Risk.NO_TRAVEL),
        ])

    def test_rain_bands(self) -> None:
        self.assert_bands(classify_rain, [
            (0.09, Risk.LOW), (0.10, Risk.MODERATE), (0.24, Risk.MODERATE), (0.25, Risk.HIGH),
            (0.49, Risk.HIGH), (0.50, Risk.SEVERE), (1.00, Risk.SEVERE), (1.01, Risk.NO_TRAVEL),
        ])

    def test_snow_bands(self) -> None:
        self.assert_bands(classify_snow, [
            (0.49, Risk.LOW), (0.5, Risk.MODERATE), (1.0, Risk.HIGH), (1.99, Risk.HIGH),
            (2.0, Risk.SEVERE), (3.0, Risk.SEVERE), (3.01, Risk.NO_TRAVEL),
        ])


class LoadRuleTests(SimpleTestCase):
    def test_55_mph_is_no_travel_for_any_load(self) -> None:
        self.assertEqual(assess(55, 0, 0, load_lb=1_000).level, Risk.NO_TRAVEL)

    def test_45_to_54_mph_over_30k_lb_is_no_travel(self) -> None:
        self.assertEqual(assess(50, 0, 0, load_lb=30_001).level, Risk.NO_TRAVEL)
        self.assertEqual(assess(50, 0, 0, load_lb=30_000).level, Risk.SEVERE)

    def test_35_to_44_mph_over_40k_lb_is_severe(self) -> None:
        heavy = assess(40, 0, 0, load_lb=40_001)
        self.assertEqual(heavy.level, Risk.SEVERE)
        self.assertEqual(heavy.factors, ("Wind + load",))
        self.assertEqual(assess(40, 0, 0, load_lb=40_000).level, Risk.HIGH)

    def test_worst_condition_wins_and_ties_are_listed(self) -> None:
        result = assess(10, 0.3, 1.5, load_lb=0)
        self.assertEqual(result.level, Risk.HIGH)
        self.assertEqual(result.factors, ("Rain", "Snow"))

    def test_low_has_no_factors(self) -> None:
        self.assertEqual(assess(5, 0, 0, load_lb=80_000).factors, ())


class RiskScoreTests(SimpleTestCase):
    def test_score_rises_within_the_low_band(self) -> None:
        self.assertEqual(risk_score(0, 0, 0, load_lb=0), 0.0)
        self.assertAlmostEqual(risk_score(20, 0, 0, load_lb=0), 0.8)
        self.assertAlmostEqual(risk_score(0, 0.05, 0, load_lb=0), 0.5)

    def test_whole_part_always_matches_the_level(self) -> None:
        cases = [(30, 0, 0, 0), (0, 1.0, 0, 0), (0, 0, 3.0, 0), (50, 0, 0, 35_000), (40, 0, 0, 45_000), (60, 0, 0, 0)]
        for wind, rain, snow, load in cases:
            with self.subTest(wind=wind, rain=rain, snow=snow, load=load):
                level = assess(wind, rain, snow, load).level
                self.assertEqual(int(risk_score(wind, rain, snow, load)), level)
