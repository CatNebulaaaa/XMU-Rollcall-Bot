import os
from unittest.mock import Mock, patch

os.environ["XMU_ROLLCALL_CONFIG_DIR"] = os.path.join(os.path.dirname(__file__), ".test-config")

import pytest
from xmu_rollcall import verify, rollcall_handler


POINTS = [dict(name="Test A", latitude=24.45, longitude=118.12),
          dict(name="Test B", latitude=24.46, longitude=118.13)]


def response(data, status=400):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


def test_outside_range_response_is_read_and_next_point_can_succeed(capsys):
    session = Mock(headers={})
    first = response({"error": {"code": "out_of_range", "message": "PRIVATE_ACCOUNT_DATA"}})
    session.put.side_effect = [first, response(None, status=200)]
    result = {}
    with patch.object(verify.time, "sleep"):
        assert verify.send_radar(session, 42, radar_points=POINTS, result=result)
    first.json.assert_called_once()
    assert session.put.call_count == 2
    assert result['detail'] == "Answered successfully"
    output = capsys.readouterr().out
    assert "HTTP 400: outside signing range" in output
    assert "PRIVATE_ACCOUNT_DATA" not in output


@pytest.mark.parametrize("data, reason", [
    ({"error_code": "invalid_parameter"}, "missing or invalid request fields"),
    ({"message": "点名已结束"}, "rollcall ended or expired"),
    ({"errors": [{"code": "device_mismatch"}]}, "device verification rejected"),
    ({"detail": "already answered"}, "already answered"),
    ({"error": "invalid_location"}, "invalid or missing location"),
    ({"message": "token expired"}, "login or permission required"),
])
def test_known_non_location_rejection_stops_point_round(data, reason):
    session = Mock(headers={})
    session.put.return_value = response(data)
    result = {}
    with patch.object(verify.time, "sleep") as sleep:
        assert not verify.send_radar(session, 42, radar_points=POINTS, result=result)
    assert session.put.call_count == 1
    sleep.assert_not_called()
    assert result['detail'] == "HTTP 400: " + reason


def test_unknown_error_never_logs_raw_response_values(capsys):
    session = Mock(headers={})
    session.put.return_value = response({"message": "PRIVATE_NAME PRIVATE_COOKIE", "token": "PRIVATE_TOKEN"})
    result = {}
    assert not verify.send_radar(session, 42, location=(24.45, 118.12), result=result)
    output = capsys.readouterr().out
    assert "unrecognized server rejection" in output
    assert "PRIVATE_" not in output
    assert result['detail'] == "HTTP 400: unrecognized server rejection"


def test_non_json_rejection_is_preserved_without_logging_body(capsys):
    session = Mock(headers={})
    reply = response(None)
    reply.json.side_effect = ValueError("PRIVATE_BODY")
    session.put.return_value = reply
    result = {}
    assert not verify.send_radar(session, 42, location=(24.45, 118.12), result=result)
    assert result['detail'] == "HTTP 400: non-JSON response"
    assert "PRIVATE_BODY" not in capsys.readouterr().out


def test_handler_retains_radar_failure_reason_in_last_rollcall():
    item = dict(course_id=8, course_title="Test course", created_by_name="Test", department_name="Test",
        is_expired=False, is_number=False, is_radar=True, rollcall_id=42, rollcall_status="in_progress",
        rollcall_time="2026-10-15T11:56:00Z", scored=False, status="absent")
    session = Mock(headers={})
    session.put.return_value = response({"error_code": "out_of_range"})
    latest = {}
    with patch.object(verify.time, "sleep"):
        rollcall_handler.process_rollcalls({"rollcalls": [item]}, session, radar_points=POINTS, last_rollcall=latest)
    assert latest['result'] == "HTTP 400: outside signing range"
    rollcall_handler.process_rollcalls({"rollcalls": []}, session, last_rollcall=latest)
    assert latest['result'] == "HTTP 400: outside signing range"


@pytest.mark.parametrize("status, data", [
    (502, {"distance": 100}),
    (400, {"distance": 100, "error_code": "invalid_parameter"}),
])
def test_non_location_errors_do_not_trigger_legacy_solver_probes(status, data):
    session = Mock(headers={})
    session.put.return_value = response(data, status=status)
    assert not verify.send_radar(session, 42)
    assert session.put.call_count == 1
