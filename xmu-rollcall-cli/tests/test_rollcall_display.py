import io
import itertools
import os
from contextlib import redirect_stdout
from unittest.mock import Mock, patch

os.environ["XMU_ROLLCALL_CONFIG_DIR"] = os.path.join(os.path.dirname(__file__), ".test-config")

import pytest
from xmu_rollcall import monitor, rollcall_handler, verify


def rollcall(identifier=42, **changes):
    item = dict(course_id=8, course_title="Test course", created_by_name="Test", department_name="Test",
        is_expired=False, is_number=True, is_radar=False, rollcall_id=identifier,
        rollcall_status="in_progress", rollcall_time="2026-10-14T07:00:00Z", scored=False, status="absent")
    item.update(changes)
    return item


def response(data=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = data
    return result


@pytest.mark.parametrize("status", [200, 400])
def test_retrieved_code_is_available_for_display_even_if_submission_fails(status):
    session = Mock(headers={})
    session.get.side_effect = [response({}), response({"rollcalls": [{"id": 42, "number_code": "0031"}]})]
    session.put.return_value = response(status=status)
    result = {}
    with patch.object(verify.time, "sleep"):
        assert verify.send_code(session, 42, 8, "2026-10-14T07:00:00Z", result=result) == (status == 200)
    assert result == {"number_code": "0031"}


def test_old_and_expired_records_cannot_replace_latest_code():
    latest = {}
    newest = rollcall(43, rollcall_time="2026-10-14T08:00:00Z")
    rollcall_handler.remember_rollcall(latest, newest, "Number rollcall", "Answered successfully", "0031")
    old = rollcall(42)
    rollcall_handler.remember_rollcall(latest, old, "Number rollcall", "Already answered")
    expired = rollcall(44, is_expired=True, rollcall_time="2026-10-14T09:00:00Z")
    rollcall_handler.handle_rollcalls({"rollcalls": [expired]}, Mock(), last_rollcall=latest)
    assert latest['rollcall_id'] == 43
    assert latest['number_code'] == "0031"


def test_dashboard_panel_keeps_fixed_rows_with_long_multiline_course_name():
    latest = dict(course_title="课" * 100 + "\nSecond line", rollcall_type="Number rollcall",
                  rollcall_time="2026-10-14T07:00:00Z", result="Answered successfully", number_code="0031")
    output = io.StringIO()
    with patch.object(monitor, "clear_screen"), patch.object(monitor, "get_terminal_width", return_value=80), redirect_stdout(output):
        monitor.print_dashboard("Test", 0, 5, last_rollcall=latest)
    lines = monitor.strip_ansi(output.getvalue()).splitlines()
    assert len(lines) == monitor.FOOTER_LINE
    assert lines[monitor.TIME_LINE - 1].startswith("Current Time:")
    assert lines[monitor.RUNTIME_LINE - 1].startswith("Running Time:")
    assert lines[monitor.QUERY_LINE - 1].startswith("Query Count:")
    assert lines[24] == "Number Code: 0031"
    assert lines[monitor.FOOTER_LINE - 1].strip() == monitor.FORK_CREDIT


def test_monitor_retains_code_across_status_change_and_empty_list_then_updates_next_rollcall():
    first = rollcall()
    next_number = rollcall(43, course_title="Next course", rollcall_time="2026-10-14T08:00:00Z")
    next_radar = rollcall(44, course_title="Radar course", is_number=False, is_radar=True,
                         rollcall_time="2026-10-14T09:00:00Z")
    data = [
        {"rollcalls": [first]},
        {"rollcalls": [dict(first, status="on_call_fine")]},
        {"rollcalls": []},
        {"rollcalls": [next_number]},
        {"rollcalls": []},
        {"rollcalls": [next_radar]},
    ]
    session = Mock(headers={})
    session.get.side_effect = [*(response(item) for item in data), KeyboardInterrupt()]
    snapshots = []
    dashboard = monitor.print_dashboard

    def render(*args, **kwargs):
        output = io.StringIO()
        with redirect_stdout(output):
            dashboard(*args, **kwargs)
        snapshots.append(monitor.strip_ansi(output.getvalue()))

    def answer(session, identifier, course, started, result):
        result['number_code'] = {42: "0031", 43: "0042"}[identifier]
        return True

    account = dict(username="test", password="test", name="Test", id=1)
    with patch.object(monitor.os.path, "exists", return_value=True), \
            patch.object(monitor.requests, "Session", return_value=session), \
            patch.object(monitor, "load_session", return_value=True), \
            patch.object(monitor, "verify_session", return_value={"name": "Test"}), \
            patch.object(monitor, "clear_screen"), \
            patch.object(monitor, "get_terminal_width", return_value=100), \
            patch.object(monitor, "print_dashboard", side_effect=render), \
            patch.object(monitor.time, "sleep"), \
            patch.object(monitor.time, "time", side_effect=itertools.count(100)), \
            patch.object(rollcall_handler, "send_code", side_effect=answer) as send, \
            patch.object(rollcall_handler, "send_radar", return_value=True), \
            pytest.raises(SystemExit) as stopped:
        monitor.start_monitor(account)
    assert stopped.value.code == 0
    assert send.call_count == 2  # Same answered rollcall never fetches or submits again.
    assert len(snapshots) == 5
    assert "Waiting for first rollcall" in snapshots[0]
    assert "Number Code: 0031" in snapshots[1]
    assert "Number Code: 0031" in snapshots[2]
    assert "Already answered" in snapshots[2]
    assert "Next course" in snapshots[3] and "Number Code: 0042" in snapshots[3]
    assert "0031" not in snapshots[3]
    assert "Radar course" in snapshots[4] and "Number Code: -" in snapshots[4]
    assert "0042" not in snapshots[4]
