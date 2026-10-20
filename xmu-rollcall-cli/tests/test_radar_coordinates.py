import json
import os
from unittest.mock import Mock, patch

os.environ['XMU_ROLLCALL_CONFIG_DIR'] = os.path.join(os.path.dirname(__file__), '.test-config')

import pytest
from xmu_rollcall import verify


# Captured by isolated replay of module 72238 in official Android 2.16.1,
# APK SHA256 13d5fdd6a432127744653390938f705451ec2161d5bf689e4d1bb72247a83974.
@pytest.mark.parametrize('wgs84, expected', [
    ((24.6083073, 118.3090821), (24.605525235609267, 118.3138389036347)),
    ((24.6084008, 118.3080402), (24.605616895389733, 118.31279538658299)),
    ((24.6080642, 118.3053024), (24.60527556196021, 118.31005338857678)),
    ((24.6070605, 118.295194), (24.604255592864124, 118.29993088622076)),
    ((24.6081345, 118.2954988), (24.605330012214903, 118.30023614887435)),
])
def test_conversion_matches_official_mobile_module_replay(wgs84, expected):
    assert verify.wgs84_to_gcj02(*wgs84) == pytest.approx(expected, abs=1e-11, rel=0)


@pytest.mark.parametrize('coordinates', [(0, 0), (40.7, -74), (60, 120)])
def test_coordinates_outside_official_conversion_region_are_unchanged(coordinates):
    assert verify.wgs84_to_gcj02(*coordinates) == coordinates


def test_point_retry_converts_once_without_mutating_input_and_uses_official_api_version():
    points = [dict(name='Test', latitude=24.6083073, longitude=118.3090821)]
    original = json.dumps(points)
    session = Mock(headers={})
    session.put.return_value = Mock(status_code=400)
    session.put.return_value.json.return_value = {'error_code': 'radar_out_of_rollcall_scope'}
    with patch.object(verify.time, 'sleep'):
        assert not verify.send_radar(session, 42, radar_points=points)
        assert not verify.send_radar(session, 42, radar_points=points)
    assert json.dumps(points) == original
    for call in session.put.call_args_list:
        assert call.args[0].endswith('/api/rollcall/42/answer?api_version=1.76')
        body = call.kwargs['json']
        assert (body['latitude'], body['longitude']) == pytest.approx(
            (24.605525235609267, 118.3138389036347), abs=1e-11, rel=0)
