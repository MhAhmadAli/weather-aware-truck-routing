from datetime import datetime, timedelta, timezone
from unittest import mock

from django.test import SimpleTestCase

from routing import clients
from routing.clients import HourlyWeather, Place, RawRoute
from routing.errors import ExternalServiceError, PlanningError
from routing.geo import cumulative_miles
from routing.planner import (
    Checkpoint,
    RouteOption,
    explain,
    find_route_options,
    plan_trip,
    rank_key,
    score_route,
    truck_timeline,
)
from routing.risk import Risk

DEPARTURE = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)
NOW = DEPARTURE - timedelta(hours=1)


def make_option(label: str, risks: list[Risk], step_mi: float = 10, duration_s: float = 3600) -> RouteOption:
    checkpoints = [Checkpoint(i * step_mi, (0.0, 0.0), DEPARTURE, risk=r) for i, r in enumerate(risks)]
    option = RouteOption(label, "", [], step_mi * (len(risks) - 1), duration_s, checkpoints)
    score_route(option)
    return option


def make_raw(points: list[tuple[float, float]], mph: float) -> RawRoute:
    miles = cumulative_miles(points)[-1]
    return RawRoute(points, [miles], [miles / mph * 3600], "Test Hwy")


class ScoringTests(SimpleTestCase):
    def test_segment_takes_worse_endpoint_risk(self) -> None:
        option = make_option("A", [Risk.LOW, Risk.HIGH, Risk.LOW])
        self.assertEqual(option.miles_by_risk[Risk.HIGH], 20)
        self.assertEqual(option.miles_by_risk[Risk.LOW], 0)
        self.assertAlmostEqual(option.avg_risk, 2.0)

    def test_ranking_priority(self) -> None:
        no_travel = make_option("A", [Risk.LOW, Risk.NO_TRAVEL, Risk.LOW, Risk.LOW, Risk.LOW])
        severe = make_option("B", [Risk.SEVERE, Risk.LOW, Risk.LOW, Risk.LOW, Risk.LOW])
        high_fast = make_option("C", [Risk.HIGH, Risk.HIGH, Risk.HIGH, Risk.LOW, Risk.LOW], duration_s=100)
        high_slow = make_option("D", [Risk.HIGH, Risk.HIGH, Risk.HIGH, Risk.LOW, Risk.LOW], duration_s=200)
        ranked = sorted([no_travel, severe, high_slow, high_fast], key=rank_key)
        self.assertEqual([o.label for o in ranked], ["C", "D", "B", "A"])

    def test_reason_never_compares_values_that_display_the_same(self) -> None:
        faster = make_option("A", [Risk.LOW, Risk.LOW], duration_s=3600)
        slower_by_seconds = make_option("B", [Risk.LOW, Risk.LOW], duration_s=3620)
        self.assertEqual(rank_key(faster), rank_key(slower_by_seconds))
        self.assertEqual(explain(faster, slower_by_seconds), "Routes A and B are tied on every criterion.")

        slower_by_minutes = make_option("C", [Risk.LOW, Risk.LOW], duration_s=3900)
        self.assertIn("1h 00m vs 1h 05m", explain(faster, slower_by_minutes))

    def test_truck_speed_cap(self) -> None:
        raw = RawRoute([], [1.0, 1.0], [30.0, 100.0], "")
        _, cum_s = truck_timeline(raw)
        self.assertAlmostEqual(cum_s[1], 3600 / 65)
        self.assertAlmostEqual(cum_s[2] - cum_s[1], 100.0)


def fake_weather(points, start, end):
    """Wind of 50 mph near the destination (lon > 0.6), but only during the hour after departure."""
    hours = int((end - start).total_seconds() // 3600) + 1
    series = []
    for _, lon in points:
        wind = [0.0] * hours
        if lon > 0.6:
            index = int((DEPARTURE + timedelta(hours=1) - start).total_seconds() // 3600)
            if 0 <= index < hours:
                wind[index] = 50.0
        series.append(HourlyWeather(start, wind, [0.0] * hours, [0.0] * hours))
    return series


def fake_routes(waypoints, alternatives=0):
    if not alternatives:
        raise PlanningError("no detours in this test")
    direct = make_raw([(0.0, 0.0), (0.0, 1.0)], mph=50)
    longer = make_raw([(0.0, 0.0), (0.5, 0.5), (0.0, 1.0)], mph=50)
    return [direct, longer]


@mock.patch("routing.planner.clients.fetch_hourly_weather", side_effect=fake_weather)
@mock.patch("routing.planner.clients.fetch_routes", side_effect=fake_routes)
@mock.patch("routing.planner.clients.geocode", side_effect=lambda q: Place(q, 0.0, 0.0 if q == "O" else 1.0))
class PlanTripTests(SimpleTestCase):
    def test_weather_is_sampled_at_eta_and_safer_route_wins(self, *_mocks) -> None:
        plan = plan_trip("O", "D", DEPARTURE, load_lb=35_000, interval_mi=25, now=NOW)
        routes = {r["label"]: r for r in plan["routes"]}

        # Route A reaches the windy area during the windy hour: 50 mph with >30k lb is No Travel.
        self.assertGreater(routes["A"]["miles_by_risk"]["No Travel"], 0)
        # Route B gets there after the wind has passed.
        self.assertEqual(routes["B"]["max_risk"], Risk.LOW)
        self.assertEqual(plan["recommended"], "B")
        self.assertIn("fewest No Travel miles", plan["recommendation"]["reason"])

        etas = [datetime.fromisoformat(cp["eta"]) for cp in routes["A"]["checkpoints"]]
        self.assertEqual(etas[0], DEPARTURE)
        self.assertAlmostEqual((etas[2] - DEPARTURE).total_seconds(), 3600, delta=1)
        self.assertEqual([cp["mile"] for cp in routes["A"]["checkpoints"]][:3], [0, 25, 50])

        heatmap = plan["heatmap"]
        self.assertTrue(heatmap["cells"])
        self.assertEqual(datetime.fromisoformat(heatmap["start"]), DEPARTURE)
        self.assertEqual(len(heatmap["cells"][0]["risk"]), 49)

    def test_past_departure_is_rejected(self, geocode, *_mocks) -> None:
        with self.assertRaises(PlanningError):
            plan_trip("O", "D", NOW - timedelta(hours=2), load_lb=10_000, interval_mi=25, now=NOW)
        geocode.assert_not_called()

    def test_departure_after_forecast_end_is_rejected_before_any_api_call(self, geocode, *_mocks) -> None:
        with self.assertRaises(PlanningError):
            plan_trip("O", "D", NOW + timedelta(days=20), load_lb=10_000, interval_mi=25, now=NOW)
        geocode.assert_not_called()

    def test_same_origin_and_destination_is_rejected_before_any_api_call(self, geocode, *_mocks) -> None:
        with self.assertRaises(PlanningError):
            plan_trip("Denver", " denver ", DEPARTURE, load_lb=10_000, interval_mi=25, now=NOW)
        geocode.assert_not_called()

    def test_heatmap_is_cut_short_at_forecast_end(self, *_mocks) -> None:
        # Forecast ends 23:00 UTC on day 16; this trip leaves 3 hours before that and lasts about 2 hours.
        now = datetime(2026, 10, 18, 9, 0, tzinfo=timezone.utc)
        departure = datetime(2026, 11, 2, 20, 0, tzinfo=timezone.utc)
        plan = plan_trip("O", "D", departure, load_lb=10_000, interval_mi=25, now=now)
        self.assertEqual(plan["heatmap"]["hours"], 3)
        self.assertEqual(len(plan["heatmap"]["cells"][0]["risk"]), 4)


class FindRouteOptionsTests(SimpleTestCase):
    @mock.patch("routing.planner.clients.fetch_routes")
    def test_failed_detour_does_not_fail_the_plan(self, fetch_routes) -> None:
        direct = make_raw([(0.0, 0.0), (0.0, 1.0)], mph=50)
        fetch_routes.side_effect = [[direct], ExternalServiceError("HTTP 429")] + [ExternalServiceError("x")] * 3
        self.assertEqual(find_route_options((0.0, 0.0), (0.0, 1.0)), [direct])


class MalformedResponseTests(SimpleTestCase):
    def fake_response(self, payload: object) -> mock.Mock:
        return mock.Mock(status_code=200, json=mock.Mock(return_value=payload))

    def test_unexpected_shapes_become_external_service_errors(self) -> None:
        cases = [
            (lambda: clients.geocode("x"), [{"lat": "1"}]),
            (lambda: clients.fetch_routes([(0, 0), (0, 1)]), {"code": "Ok"}),
            (lambda: clients.fetch_routes([(0, 0), (0, 1)]), {"code": "Ok", "routes": []}),
            (lambda: clients.fetch_hourly_weather([(0, 0)], NOW, NOW), {"hourly": {"time": []}}),
        ]
        for call, payload in cases:
            with self.subTest(payload=payload), mock.patch("routing.clients.time.sleep"):
                with mock.patch("routing.clients.requests.get", return_value=self.fake_response(payload)):
                    with self.assertRaises(ExternalServiceError):
                        call()


class PlanViewTests(SimpleTestCase):
    def test_invalid_payload_returns_400(self) -> None:
        response = self.client.post("/api/plan/", {"origin": "A"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("destination", response.json())

    @mock.patch("routing.views.plan_trip", side_effect=PlanningError("bad trip"))
    def test_planning_error_returns_400_detail(self, _plan) -> None:
        payload = {"origin": "A", "destination": "B", "departure": DEPARTURE.isoformat(), "load_lb": 1000}
        response = self.client.post("/api/plan/", payload, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"detail": "bad trip"})
