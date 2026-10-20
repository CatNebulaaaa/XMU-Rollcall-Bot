import uuid
import time
import math
import json
import re
import requests
from datetime import datetime, timezone

base_url = "https://lnt.xmu.edu.cn"
headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9",
    "Referer": "https://ids.xmu.edu.cn/authserver/login",
}

def find_number_code(data, depth=0, max_depth=10):
    """Extract number_code from nested dict/list API responses.

    Args:
        data: Parsed JSON payload from Tronclass APIs.
        depth: Current recursive depth when traversing nested structures.
        max_depth: Maximum depth allowed for traversal to avoid pathological recursion.

    Returns:
        str or None: The first discovered number_code value, or None if not found.
    """
    if depth > max_depth:
        return None
    if isinstance(data, dict):
        number_code = data.get("number_code")
        if number_code is not None:
            return str(number_code)
        for value in data.values():
            nested_code = find_number_code(value, depth + 1, max_depth)
            if nested_code:
                return nested_code
    elif isinstance(data, list):
        for item in data:
            nested_code = find_number_code(item, depth + 1, max_depth)
            if nested_code:
                return nested_code
    return None

def rollcall_date_utc(rollcall_time):
    """Return the UTC date required by the timetable rollcall API."""
    try:
        parsed = datetime.fromisoformat(str(rollcall_time).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError):
        return datetime.now(timezone.utc).date().isoformat()


def find_timetable_number_code(data, rollcall_id):
    """Find a number code for one rollcall in a timetable API response."""
    if isinstance(data, dict):
        items = data.get("rollcalls", data.get("data", []))
        if isinstance(items, dict):
            return find_timetable_number_code(items, rollcall_id)
    elif isinstance(data, list):
        items = data
    else:
        return None

    if not isinstance(items, list):
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = item.get("id", item.get("rollcall_id"))
        if str(item_id) != str(rollcall_id):
            continue
        number_code = item.get("number_code")
        if number_code is not None:
            return str(number_code)
    return None


def get_timetable_number_code(
    in_session, rollcall_id, course_id, rollcall_time, request_headers
):
    """Fetch a number code from the timetable endpoint used by newer servers."""
    if course_id is None:
        print("Timetable lookup needs course_id from the rollcall list.")
        return None

    timetable_url = f"{base_url}/api/timetable_rollcalls"
    params = [
        ("course_ids", str(course_id)),
        ("rollcall_date", rollcall_date_utc(rollcall_time)),
    ]
    try:
        response = in_session.get(
            timetable_url,
            params=params,
            headers=request_headers,
            timeout=10,
        )
        if response.status_code != 200:
            print(
                "Failed to get number code from timetable API. "
                f"Status: {response.status_code}."
            )
            return None
        return find_timetable_number_code(response.json(), rollcall_id)
    except requests.RequestException as e:
        print(f"Failed to request timetable rollcall API: {type(e).__name__}")
    except ValueError:
        print("Failed to parse timetable rollcall API response: invalid JSON")
    return None


def send_code(
    in_session, rollcall_id, course_id=None, rollcall_time=None, result=None
):
    code_url = f"{base_url}/api/rollcall/{rollcall_id}/student_rollcalls"
    answer_url = f"{base_url}/api/rollcall/{rollcall_id}/answer_number_rollcall"
    print("Trying number code from API...")
    t00 = time.time()
    request_headers = in_session.headers
    number_code = None

    try:
        code_response = in_session.get(
            code_url, headers=request_headers, timeout=10
        )
        if code_response.status_code == 200:
            number_code = find_number_code(code_response.json())
        else:
            print(
                "Number code detail API returned status "
                f"{code_response.status_code}; trying timetable API."
            )
    except requests.RequestException as e:
        print(f"Failed to request number code detail API: {type(e).__name__}")
    except ValueError:
        print("Failed to parse number code detail API response: invalid JSON")

    if not number_code:
        print("Number code missing in detail API; trying timetable API...")
        number_code = get_timetable_number_code(
            in_session,
            rollcall_id,
            course_id,
            rollcall_time,
            request_headers,
        )

    if not number_code:
        t01 = time.time()
        print(
            "Failed to get number code from available APIs. "
            f"Time: {t01 - t00:.2f} s."
        )
        return False

    payload = {
        "deviceId": str(uuid.uuid4()),
        "numberCode": number_code
    }
    if result is not None:
        result["number_code"] = number_code
    try:
        response = in_session.put(
            answer_url, json=payload, headers=request_headers, timeout=10
        )
        if response.status_code == 200:
            print(
                "Number code rollcall answered successfully."
            )
            time.sleep(5)
            t01 = time.time()
            print(f"Time: {t01 - t00:.2f} s.")
            return True
        t01 = time.time()
        print(
            "Failed to submit number code. "
            f"Status: {response.status_code}\nTime: {t01 - t00:.2f} s."
        )
        return False
    except requests.RequestException as e:
        t01 = time.time()
        print(
            f"Failed to submit number code: {type(e).__name__}\n"
            f"Time: {t01 - t00:.2f} s."
        )
        return False

def radar_error_reason(data):
    """Classify server errors without logging response text or account data."""
    messages = []

    def collect(value, depth=0):
        if depth > 4:
            return
        if isinstance(value, str):
            messages.append(value[:1000].lower())
        elif isinstance(value, dict):
            for key in ("code", "error_code", "errorCode", "error_type", "type", "status", "error", "errors", "message", "msg", "detail", "description", "error_description", "data", "result", "scope", "rollcall"):
                if key in value:
                    collect(value[key], depth + 1)
        elif isinstance(value, list):
            for item in value[:5]:
                collect(item, depth + 1)

    collect(data)
    text = ' '.join(messages)
    reasons = (
        ("login or permission required", ("unauthorized", "forbidden", "login required", "token expired", "登录过期", "未登录", "无权限")),
        ("outside signing range", ("radar_out_of_rollcall_scope", "radar_out_of_scope", "out_of_range", "out of range", "outside", "too_far", "too far", "not_in_range", "not in range", "超出范围", "不在范围", "不在签到范围", "不在点名范围", "超出签到范围", "距离过远", "距离太远")),
        ("rollcall ended or expired", ("rollcall_expired", "rollcall_ended", "rollcall_already_closed", "rollcall_not_in_progress", "has ended", "点名已结束", "签到已结束", "点名过期")),
        ("already answered", ("already_answered", "already_signed", "already answered", "already signed", "已签到", "已完成签到", "重复签到")),
        ("device verification rejected", ("rollcall_device_already_in_use", "radar_device_id_invalid", "device_mismatch", "invalid_device", "device verification", "设备验证", "设备不匹配", "设备异常")),
        ("invalid or missing location", ("rollcall_position_invalid", "invalid_location", "location_required", "invalid latitude", "invalid longitude", "location required", "定位失败", "定位信息", "经纬度无效")),
        ("Bluetooth beacon validation failed", ("rollcall_beacon_nonce_invalid", "radar_signal_invalid")),
        ("missing or invalid request fields", ("invalid_parameter", "missing_parameter", "required field", "missing field", "invalid parameter", "参数错误", "参数缺失", "参数不合法")),
    )
    for reason, patterns in reasons:
        if any(pattern in text for pattern in patterns):
            return reason
    return "unrecognized server rejection"


def radar_diagnostic(data, status, reason=None):
    """Explain a rejection using only bounded, safe machine codes."""
    codes = []
    numeric_codes = []

    def shape(value, key='', depth=0):
        if depth > 5:
            return '<nested>'
        if re.search(r'token|cookie|password|secret|authorization|nonce|session|student|username|email', key, re.I):
            return '<redacted>'
        if isinstance(value, dict):
            return {name if re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,48}', str(name)) else '<field>':
                    shape(item, str(name), depth + 1) for name, item in list(value.items())[:30]}
        if isinstance(value, list):
            return [shape(item, key, depth + 1) for item in value[:3]]
        if isinstance(value, str) and key in ('', 'error', 'error_code', 'errorCode', 'code', 'message', 'msg', 'detail', 'description', 'error_description', 'status', 'type'):
            codes.extend(re.findall(r'\b(?:radar|rollcall)_[a-z0-9_]{1,64}\b', value[:1000]))
            if value in ('out_of_range', 'invalid_parameter', 'missing_parameter', 'device_mismatch', 'invalid_location', 'unauthorized', 'forbidden'):
                codes.append(value)
        if key in ('error_code', 'errorCode', 'code') and type(value) is int and -999999 <= value <= 999999:
            numeric_codes.append(str(value))
            return value
        if key in ('error_code', 'errorCode', 'code') and isinstance(value, str) and re.fullmatch(r'-?[0-9]{1,6}', value):
            numeric_codes.append(value)
            return value
        return '<' + type(value).__name__ + '>'

    report = {'http_status': status, 'captured_at': datetime.now(timezone.utc).isoformat(),
              'method': 'PUT', 'endpoint': '/api/rollcall/<id>/answer?api_version=1.76',
              'error_structure': shape(data), 'error_codes': sorted(set(codes))}
    if status in (401, 403):
        reason = 'login or permission required'
    elif status == 429:
        reason = 'too many requests'
    elif status is not None and status >= 500:
        reason = 'server error'
    elif status == 404:
        reason = 'endpoint or rollcall not found'
    reason = reason or radar_error_reason(data)
    descriptions = {
        'outside signing range': ('当前位置不在签到范围内', '确认实际教室位置；楼宇中心可能不在签到半径内。'),
        'rollcall ended or expired': ('点名已结束或已过期', '本次点名已不能提交，请核对点名状态。'),
        'already answered': ('服务端表示已经签到', '请在官方 App 核对记录；此响应不能证明是脚本完成的。'),
        'device verification rejected': ('设备校验未通过', '请用官方 App 完成签到；保留错误码以核查设备标识兼容性。'),
        'invalid or missing location': ('定位信息缺失或无效', '检查点位文件是否使用 WGS84、经纬度是否填反；也可能是定位字段不兼容。'),
        'Bluetooth beacon validation failed': ('蓝牙信标校验未通过', '需要现场蓝牙验证，请用官方 App 开启蓝牙后签到。'),
        'missing or invalid request fields': ('请求参数缺失或无效', '这是接口参数问题，换点位通常无效；请保留错误码和诊断文件。'),
        'login or permission required': ('登录失效或没有操作权限', '重新登录后再试；若仍为 HTTP 403，请核对课程权限。'),
        'too many requests': ('请求过于频繁，服务端已限流', '请暂停重试，稍后再试；换点位不能解除限流。'),
        'server error': ('畅课服务端或网关出错', '请稍后再试；这类状态不能用于判断点位是否正确。'),
        'endpoint or rollcall not found': ('接口或本次点名不存在', '点名可能已失效，也可能是接口路径变化；请保留诊断文件。'),
        'non-JSON response': ('接口返回了无法解析的内容', '可能是登录页、网关页面或接口格式变化；不能据此判断距离。'),
        'network timeout': ('请求超时，未收到签到结果', '请先在官方 App 核对是否已签到，再检查网络。'),
        'network request failed': ('网络请求失败，未取得服务端结果', '检查网络后重试；当前无法判断是否在签到范围。'),
        'unrecognized server rejection': ('服务器拒绝请求，原因尚未识别', '不能判定为距离问题；请查看下方错误码和脱敏诊断文件。'),
    }
    summary, advice = descriptions[reason]
    if 'rollcall_device_already_in_use' in codes:
        summary = '设备标识已被占用'
    report.update(reason=reason, summary=summary, advice=advice,
                  numeric_error_codes=sorted(set(numeric_codes)))
    return report


def save_radar_rejection(report):
    """Save a sanitized diagnostic and return its actual path, or None."""
    from .config import CONFIG_DIR
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        path = CONFIG_DIR / 'radar_last_rejection.json'
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        return str(path.absolute())
    except OSError:
        return None


def wgs84_to_gcj02(latitude, longitude):
    """Match the official mobile client's mainland-China coordinate conversion."""
    if longitude < 72.004 or longitude > 137.8347 or latitude < 0.8293 or latitude > 55.8271:
        return latitude, longitude
    x, y = longitude - 105, latitude - 35
    common = 20 * math.sin(6 * x * math.pi) + 20 * math.sin(2 * x * math.pi)
    dlat = common + 20 * math.sin(y * math.pi) + 40 * math.sin(y * math.pi / 3)
    dlat += 160 * math.sin(y * math.pi / 12) + 320 * math.sin(y * math.pi / 30)
    dlon = common + 20 * math.sin(x * math.pi) + 40 * math.sin(x * math.pi / 3)
    dlon += 150 * math.sin(x * math.pi / 12) + 300 * math.sin(x * math.pi / 30)
    dlat *= 2 / 3
    dlon *= 2 / 3
    dlat += 2 * x - 100 + 3 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    dlon += 300 + x + 2 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    radians = math.radians(latitude)
    eccentricity = 0.006693421622965943
    magic = 1 - eccentricity * math.sin(radians) ** 2
    root = math.sqrt(magic)
    dlat = 180 * dlat / (6378137 * (1 - eccentricity) / (magic * root) * math.pi)
    dlon = 180 * dlon / (6378137 / root * math.cos(radians) * math.pi)
    return latitude + dlat, longitude + dlon


def send_radar(in_session, rollcall_id, location=None, radar_points=None, result=None):
    url = f"{base_url}/api/rollcall/{rollcall_id}/answer?api_version=1.76"

    lat_1, lat_2 = 24.3, 24.6
    lon_1, lon_2 = 118.0, 118.2
    device_id = str(uuid.uuid4())
    last_status = None
    last_reason = None

    def reject(data, reason=None, point_name='指定位置'):
        diagnostic = radar_diagnostic(data, last_status, reason)
        diagnostic['path'] = save_radar_rejection(diagnostic)
        diagnostic['point'] = point_name
        status_text = f'HTTP {last_status}' if last_status is not None else '无 HTTP 响应'
        detail = f"{status_text}: {diagnostic['reason']}"
        code_text = ', '.join(diagnostic['error_codes'] + diagnostic['numeric_error_codes']) or '服务端未提供可安全展示的错误码'
        print(f"雷达签到失败：{diagnostic['summary']}（{detail}）。")
        print(f"错误码：{code_text}")
        print(f"建议：{diagnostic['advice']}")
        print(f"脱敏诊断：{diagnostic['path'] or '保存失败；当前界面仍保留原因和错误码'}")
        if result is not None:
            result['detail'] = detail
            result['diagnostic'] = diagnostic
            result.setdefault('attempts', []).append({
                'point': point_name, 'summary': diagnostic['summary'],
                'http_status': last_status, 'error_codes': diagnostic['error_codes'] + diagnostic['numeric_error_codes'],
            })
        return diagnostic['reason']

    def payload(lat, lon):
        # CLI arguments and point files stay WGS84; convert once at the API boundary.
        lat, lon = wgs84_to_gcj02(lat, lon)
        return {
            "accuracy": 35,
            "altitude": 0,
            "altitudeAccuracy": None,
            "deviceId": device_id,
            "heading": None,
            "latitude": lat,
            "longitude": lon,
            "speed": None
        }

    def answer(lat, lon, require_distance=True, point_name='指定位置'):
        nonlocal last_status, last_reason
        last_status = None
        last_reason = None
        try:
            response = in_session.put(
                url, json=payload(lat, lon), headers=in_session.headers, timeout=10
            )
        except requests.RequestException as error:
            reject(None, 'network timeout' if isinstance(error, requests.Timeout) else 'network request failed', point_name)
            if result is not None:
                result['detail'] = "network request failed"
            return False, None
        last_status = response.status_code
        # Successful responses need not contain JSON or a distance.
        if response.status_code == 200:
            if result is not None:
                result['detail'] = "Answered successfully"
                result.pop('diagnostic', None)
                result.setdefault('attempts', []).append({
                    'point': point_name, 'summary': '签到成功', 'http_status': 200, 'error_codes': [],
                })
            return True, None
        try:
            data = response.json()
        except ValueError:
            last_reason = reject(None, 'non-JSON response', point_name)
            return False, None
        last_reason = reject(data, point_name=point_name)
        if not require_distance:
            return False, None
        if response.status_code not in (400, 422) or last_reason not in ("outside signing range", "unrecognized server rejection"):
            return False, None
        distance = data.get("distance") if isinstance(data, dict) else None
        try:
            if isinstance(distance, bool):
                raise ValueError
            distance = float(distance)
            if not math.isfinite(distance) or distance < 0:
                raise ValueError
        except (TypeError, ValueError):
            keys = ", ".join(sorted(data)) if isinstance(data, dict) else type(data).__name__
            print(
                f"Radar response has no usable distance (HTTP {response.status_code}; "
                f"fields: {keys}). The old location solver cannot continue; "
                "provide your actual --latitude/--longitude, or use the official client."
            )
            return False, None
        return False, distance

    if radar_points:
        for index, point in enumerate(radar_points):
            if index:
                time.sleep(5)
            print(f"Radar point {index + 1}/{len(radar_points)}: {point['name']}")
            success, _ = answer(point["latitude"], point["longitude"], require_distance=False, point_name=point['name'])
            if success:
                print("Radar rollcall answered successfully.")
                return True
            if last_status not in (400, 422):
                print("Stopping this point round after a network, authentication, or server error.")
                return False
            if last_reason not in (None, "outside signing range", "unrecognized server rejection"):
                print("Stopping this point round: changing location cannot resolve this rejection.")
                return False
        # Keep at least five seconds between the last point and the next round.
        time.sleep(5)
        print("None of the configured radar points was accepted; monitoring will retry later.")
        return False

    if location is not None:
        success, _ = answer(*location, require_distance=False)
        return success

    success, distance_1 = answer(lat_1, lon_1)
    if success:
        return True
    if distance_1 is None:
        return False
    success, distance_2 = answer(lat_2, lon_2)
    if success:
        return True
    if distance_2 is None:
        return False

    def latlon_to_xy(lat, lon, lat0, lon0):
        R = 6371000
        x = math.radians(lon - lon0) * R * math.cos(math.radians(lat0))
        y = math.radians(lat - lat0) * R
        return x, y

    def xy_to_latlon(x, y, lat0, lon0):
        R = 6371000
        lat = lat0 + math.degrees(y / R)
        lon = lon0 + math.degrees(x / (R * math.cos(math.radians(lat0))))
        return lat, lon

    def circle_intersections(x1, y1, d1, x2, y2, d2):
        D = math.hypot(x2 - x1, y2 - y1)

        if D > d1 + d2 or D < abs(d1 - d2):
            return None

        a = (d1**2 - d2**2 + D**2) / (2 * D)
        h = math.sqrt(max(0, d1**2 - a**2))

        xm = x1 + a * (x2 - x1) / D
        ym = y1 + a * (y2 - y1) / D

        rx = -(y2 - y1) * (h / D)
        ry = (x2 - x1) * (h / D)

        p1 = (xm + rx, ym + ry)
        p2 = (xm - rx, ym - ry)
        return p1, p2

    def solve_two_points(lat1, lon1, lat2, lon2, d1, d2):
        lat0 = (lat1 + lat2) / 2
        lon0 = (lon1 + lon2) / 2
        x1, y1 = latlon_to_xy(lat1, lon1, lat0, lon0)
        x2, y2 = latlon_to_xy(lat2, lon2, lat0, lon0)

        sols = circle_intersections(x1, y1, d1, x2, y2, d2)
        if sols is None:
            return None

        p1 = xy_to_latlon(sols[0][0], sols[0][1], lat0, lon0)
        p2 = xy_to_latlon(sols[1][0], sols[1][1], lat0, lon0)
        return p1, p2

    resolutions = solve_two_points(lat_1, lon_1, lat_2, lon_2, distance_1, distance_2)
    if resolutions:
        ((sol_x_1, sol_y_1), (sol_x_2, sol_y_2)) = resolutions
    else:
        return False

    success, distance = answer(sol_x_1, sol_y_1)
    if success:
        return True
    if distance is None:
        return False
    success, _ = answer(sol_x_2, sol_y_2)
    if success:
        return True

    return False
