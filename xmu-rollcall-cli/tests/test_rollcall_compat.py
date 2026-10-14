import math
from unittest.mock import Mock, patch
import os
import json

# CLI imports config.py, which otherwise probes the real user's config folder.
os.environ["XMU_ROLLCALL_CONFIG_DIR"] = os.path.join(os.path.dirname(__file__), ".test-config")

import pytest
import requests

from xmu_rollcall import verify, rollcall_handler


def response(status, data=None):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


@pytest.mark.parametrize("data", [
    {"rollcalls": [{"id": 7, "number_code": "9999"}, {"id": 42, "number_code": "0031"}]},
    {"data": {"rollcalls": [{"rollcall_id": "42", "number_code": "0031"}]}},
    [{"id": 42, "number_code": "0031"}],
])
def test_timetable_matches_target_and_preserves_leading_zero(data):
    assert verify.find_timetable_number_code(data, 42) == "0031"


@pytest.mark.parametrize("data", [None, {"rollcalls": None}, {"rollcalls": "bad"},
    {"rollcalls": [{"id": 7, "number_code": "9999"}]},
    {"rollcalls": [{"id": 42, "number_code": None}]}])
def test_missing_or_unrelated_codes_are_not_submitted(data):
    session = Mock(headers={})
    session.get.side_effect = [response(200, {"number_code": None}), response(200, data)]
    assert not verify.send_code(session, 42, 8, "2026-10-10T07:00:00Z")
    session.put.assert_not_called()


def test_new_endpoint_fallback_uses_course_and_utc_date():
    session = Mock(headers={"X-Test": "test"})
    session.get.side_effect = [response(200, {"number_code": None}),
        response(200, {"rollcalls": [{"id": 42, "number_code": "0031"}]})]
    session.put.return_value = response(200)
    with patch.object(verify.time, "sleep"):
        assert verify.send_code(session, 42, 8, "2026-10-11T00:30:00+08:00")
    call = session.get.call_args
    assert call.args[0].endswith("/api/timetable_rollcalls")
    assert dict(call.kwargs["params"]) == {"course_ids": "8", "rollcall_date": "2026-10-10"}
    assert session.put.call_args.kwargs["json"]["numberCode"] == "0031"


def test_legacy_endpoint_still_works_without_course_metadata():
    session = Mock(headers={})
    session.get.return_value = response(200, {"number_code": "0031"})
    session.put.return_value = response(200)
    with patch.object(verify.time, "sleep"):
        assert verify.send_code(session, 42)
    assert session.get.call_count == 1


def test_malformed_legacy_response_falls_back():
    session = Mock(headers={})
    bad = response(200)
    bad.json.side_effect = ValueError("invalid JSON")
    session.get.side_effect = [bad, response(200, {"rollcalls": [{"id": 42, "number_code": "0031"}]})]
    session.put.return_value = response(200)
    with patch.object(verify.time, "sleep"):
        assert verify.send_code(session, 42, 8)


@pytest.mark.parametrize("distance", [None, True, "bad", float("nan"), float("inf"), -1])
def test_radar_missing_or_invalid_distance_does_not_crash(distance):
    session = Mock(headers={})
    session.put.return_value = response(400, {"distance": distance})
    assert not verify.send_radar(session, 42)
    assert session.put.call_count == 1


def test_radar_accepts_success_before_json_parsing():
    session = Mock(headers={})
    session.put.return_value = response(200)
    session.put.return_value.json.side_effect = ValueError("empty body")
    assert verify.send_radar(session, 42)
    session.put.return_value.json.assert_not_called()


@pytest.mark.parametrize("status", [401, 403])
def test_radar_denied_does_not_retry(status):
    session = Mock(headers={})
    session.put.return_value = response(status, {"distance": 100})
    assert not verify.send_radar(session, 42)
    assert session.put.call_count == 1


def test_radar_network_failure_does_not_leak_exception_details(capsys):
    session = Mock(headers={})
    session.put.side_effect = requests.Timeout("PRIVATE_VALUE")
    assert not verify.send_radar(session, 42)
    assert "PRIVATE_VALUE" not in capsys.readouterr().out


def test_radar_non_json_failure_does_not_crash():
    session = Mock(headers={})
    session.put.return_value = response(502)
    session.put.return_value.json.side_effect = ValueError("invalid JSON")
    assert not verify.send_radar(session, 42)


def test_radar_actual_location_does_not_require_distance():
    session = Mock(headers={})
    session.put.return_value = response(200)
    assert verify.send_radar(session, 42, (24.45, 118.12))
    assert session.put.call_count == 1
    body = session.put.call_args.kwargs["json"]
    assert body["latitude"] == 24.45 and body["longitude"] == 118.12


def test_radar_actual_location_failure_is_not_followed_by_solver_probes():
    session = Mock(headers={})
    session.put.return_value = response(400, {"distance": 100})
    assert not verify.send_radar(session, 42, (24.45, 118.12))
    assert session.put.call_count == 1


@pytest.mark.parametrize("args", [["--latitude", "24"], ["--longitude", "118"],
                                 ["--latitude", "91", "--longitude", "118"]])
def test_cli_rejects_unpaired_or_invalid_coordinates_before_loading_account(args):
    from click.testing import CliRunner
    from xmu_rollcall.cli import cli
    with patch("xmu_rollcall.cli.load_config") as load:
        result = CliRunner().invoke(cli, ["start"] + args)
    assert result.exit_code == 2
    load.assert_not_called()


def test_cli_passes_actual_coordinates_to_monitor():
    from click.testing import CliRunner
    from xmu_rollcall.cli import cli
    account = {"id": 1, "name": "Test", "username": "test", "password": "test"}
    config = {"accounts": [account], "current_account_id": 1}
    with patch("xmu_rollcall.cli.load_config", return_value=config), \
            patch("xmu_rollcall.cli.start_monitor") as monitor:
        result = CliRunner().invoke(cli, ["start", "--latitude", "24.45", "--longitude", "118.12"])
    assert result.exit_code == 0
    monitor.assert_called_once_with(account, (24.45, 118.12), None)


def test_plain_start_loads_five_default_points_from_any_directory(tmp_path, monkeypatch):
    from click.testing import CliRunner
    from xmu_rollcall.cli import cli, DEFAULT_RADAR_POINTS_FILE
    account = {"id": 1, "name": "Test", "username": "test", "password": "test"}
    config = {"accounts": [account], "current_account_id": 1}
    expected = json.loads(DEFAULT_RADAR_POINTS_FILE.read_text(encoding="utf-8"))["points"]
    monkeypatch.chdir(tmp_path)
    with patch("xmu_rollcall.cli.load_config", return_value=config), \
            patch("xmu_rollcall.cli.start_monitor") as monitor:
        result = CliRunner().invoke(cli, ["start"])
    assert result.exit_code == 0, result.output
    monitor.assert_called_once_with(account, None, expected)
    assert len(expected) == 5
    assert [p["name"] for p in expected] == ["学武楼", "坤銮楼", "文宣楼",
        "西部片区2号楼（学信楼）", "西部片区4号楼（启信楼）"]


def test_legacy_radar_solver_uses_one_device_and_session_headers():
    session = Mock(headers={"X-Test": "test"})
    # Distances computed from the same local projection as the existing solver.
    lat0, lon0 = 24.45, 118.1
    def xy(lat, lon):
        return (math.radians(lon - lon0) * 6371000 * math.cos(math.radians(lat0)),
                math.radians(lat - lat0) * 6371000)
    target = xy(24.45, 118.12)
    distances = [math.dist(xy(lat, lon), target) for lat, lon in [(24.3, 118), (24.6, 118.2)]]
    session.put.side_effect = [response(400, {"distance": str(distances[0])}),
                              response(400, {"distance": distances[1]}), response(200)]
    assert verify.send_radar(session, 42)
    calls = session.put.call_args_list
    assert len({c.kwargs["json"]["deviceId"] for c in calls}) == 1
    assert all(c.kwargs["headers"] == session.headers and c.kwargs["timeout"] == 10 for c in calls)


def test_handler_passes_course_metadata_to_number_api():
    rollcall = dict(course_id=8, course_title="Test course", created_by_name="Test", department_name="Test",
        is_expired=False, is_number=True, is_radar=False, rollcall_id=42, rollcall_status="in_progress",
        rollcall_time="2026-10-10T07:00:00Z", scored=False, status="absent")
    session = Mock()
    with patch.object(rollcall_handler, "send_code", return_value=True) as send:
        assert rollcall_handler.handle_rollcalls({"rollcalls": [rollcall]}, session) == [True]
    send.assert_called_once_with(session, 42, 8, "2026-10-10T07:00:00Z", result={})


POINTS = [
    {"name": "Test A", "latitude": 24.45, "longitude": 118.12},
    {"name": "Test B", "latitude": 24.46, "longitude": 118.13},
    {"name": "Test C", "latitude": 24.47, "longitude": 118.14},
]


def test_point_round_advances_without_distance_and_stops_on_success():
    session = Mock(headers={})
    session.put.side_effect = [response(400, {"message": "outside"}), response(200)]
    with patch.object(verify.time, "sleep") as sleep:
        assert verify.send_radar(session, 42, radar_points=POINTS)
    assert session.put.call_count == 2
    bodies = [call.kwargs["json"] for call in session.put.call_args_list]
    assert [body["latitude"] for body in bodies] == [24.45, 24.46]
    assert len({body["deviceId"] for body in bodies}) == 1
    sleep.assert_called_once_with(5)


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 502])
def test_point_round_stops_on_auth_rate_limit_or_server_failure(status):
    session = Mock(headers={})
    session.put.return_value = response(status)
    with patch.object(verify.time, "sleep") as sleep:
        assert not verify.send_radar(session, 42, radar_points=POINTS)
    assert session.put.call_count == 1
    sleep.assert_not_called()


def test_point_round_all_failures_remain_failures_and_are_spaced():
    session = Mock(headers={})
    session.put.return_value = response(400, {"distance": None})
    with patch.object(verify.time, "sleep") as sleep:
        assert not verify.send_radar(session, 42, radar_points=POINTS)
    assert session.put.call_count == 3
    assert [call.args for call in sleep.call_args_list] == [(5,), (5,), (5,)]


def test_points_file_skips_empty_entries_and_passes_configured_order(tmp_path):
    from click.testing import CliRunner
    from xmu_rollcall.cli import cli
    path = tmp_path / "points.json"
    path.write_text(json.dumps({"coordinate_system": "WGS84", "points": [
        {"name": "Empty", "latitude": None, "longitude": None}, *POINTS]}), encoding="utf-8-sig")
    account = {"id": 1, "name": "Test", "username": "test", "password": "test"}
    config = {"accounts": [account], "current_account_id": 1}
    with patch("xmu_rollcall.cli.load_config", return_value=config), \
            patch("xmu_rollcall.cli.start_monitor") as monitor:
        result = CliRunner().invoke(cli, ["start", "--radar-points", str(path)])
    assert result.exit_code == 0
    monitor.assert_called_once_with(account, None, POINTS)


@pytest.mark.parametrize("data", [
    {"coordinate_system": "GCJ02", "points": POINTS},
    {"coordinate_system": "WGS84", "points": [{"name": "Empty", "latitude": None, "longitude": None}]},
    {"coordinate_system": "WGS84", "points": [{"name": "Bad", "latitude": 24, "longitude": None}]},
    {"coordinate_system": "WGS84", "points": [{"name": "Bad", "latitude": 91, "longitude": 118}]},
    {"coordinate_system": "WGS84", "points": [{"name": "Bad", "latitude": True, "longitude": 118}]},
    {"coordinate_system": "WGS84", "points": [{"name": "Bad", "latitude": float("nan"), "longitude": 118}]},
])
def test_invalid_points_file_never_starts_monitor(data, tmp_path):
    from click.testing import CliRunner
    from xmu_rollcall.cli import cli
    path = tmp_path / "points.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with patch("xmu_rollcall.cli.load_config") as load:
        result = CliRunner().invoke(cli, ["start", "--radar-points", str(path)])
    assert result.exit_code == 2
    load.assert_not_called()


def test_cli_disallows_combining_points_and_single_location(tmp_path):
    from click.testing import CliRunner
    from xmu_rollcall.cli import cli
    path = tmp_path / "points.json"
    path.write_text("{}", encoding="utf-8")
    with patch("xmu_rollcall.cli.load_config") as load:
        result = CliRunner().invoke(cli, ["start", "--radar-points", str(path),
                                         "--latitude", "24", "--longitude", "118"])
    assert result.exit_code == 2
    load.assert_not_called()


def test_expired_radar_rollcall_is_not_submitted():
    rollcall = dict(course_title="Test course", created_by_name="Test", department_name="Test",
        is_expired=True, is_number=False, is_radar=True, rollcall_id=42, rollcall_status="ended",
        scored=False, status="absent")
    with patch.object(rollcall_handler, "send_radar") as send:
        rollcall_handler.handle_rollcalls({"rollcalls": [rollcall]}, Mock(), radar_points=POINTS)
    send.assert_not_called()
