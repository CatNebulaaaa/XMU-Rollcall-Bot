import uuid
import time
import math
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
            for key in ("code", "error_code", "errorCode", "error_type", "type", "error", "errors", "message", "msg", "detail"):
                if key in value:
                    collect(value[key], depth + 1)
        elif isinstance(value, list):
            for item in value[:5]:
                collect(item, depth + 1)

    collect(data)
    text = ' '.join(messages)
    reasons = (
        ("login or permission required", ("unauthorized", "forbidden", "login required", "token expired", "登录过期", "未登录", "无权限")),
        ("outside signing range", ("out_of_range", "out of range", "outside", "too_far", "too far", "not_in_range", "not in range", "超出范围", "不在范围", "不在签到范围", "不在点名范围", "超出签到范围", "距离过远", "距离太远")),
        ("rollcall ended or expired", ("rollcall_expired", "rollcall_ended", "rollcall_not_in_progress", "has ended", "点名已结束", "签到已结束", "点名过期")),
        ("already answered", ("already_answered", "already_signed", "already answered", "already signed", "已签到", "已完成签到", "重复签到")),
        ("device verification rejected", ("device_mismatch", "invalid_device", "device verification", "设备验证", "设备不匹配", "设备异常")),
        ("invalid or missing location", ("invalid_location", "location_required", "invalid latitude", "invalid longitude", "location required", "定位失败", "定位信息", "经纬度无效")),
        ("missing or invalid request fields", ("invalid_parameter", "missing_parameter", "required field", "missing field", "invalid parameter", "参数错误", "参数缺失", "参数不合法")),
    )
    for reason, patterns in reasons:
        if any(pattern in text for pattern in patterns):
            return reason
    return "unrecognized server rejection"


def send_radar(in_session, rollcall_id, location=None, radar_points=None, result=None):
    url = f"{base_url}/api/rollcall/{rollcall_id}/answer"

    lat_1, lat_2 = 24.3, 24.6
    lon_1, lon_2 = 118.0, 118.2
    device_id = str(uuid.uuid4())
    last_status = None
    last_reason = None

    def payload(lat, lon):
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

    def answer(lat, lon, require_distance=True):
        nonlocal last_status, last_reason
        last_status = None
        last_reason = None
        try:
            response = in_session.put(
                url, json=payload(lat, lon), headers=in_session.headers, timeout=10
            )
        except requests.RequestException as error:
            print(f"Radar request failed: {type(error).__name__}")
            if result is not None:
                result['detail'] = "network request failed"
            return False, None
        last_status = response.status_code
        # Successful responses need not contain JSON or a distance.
        if response.status_code == 200:
            if result is not None:
                result['detail'] = "Answered successfully"
            return True, None
        if response.status_code in (401, 403):
            print(f"Radar request denied (HTTP {response.status_code}); check login/permissions.")
            if result is not None:
                result['detail'] = f"HTTP {response.status_code}: login or permission required"
            return False, None
        try:
            data = response.json()
        except ValueError:
            print(f"Radar response is not JSON (HTTP {response.status_code}).")
            if result is not None:
                result['detail'] = f"HTTP {response.status_code}: non-JSON response"
            return False, None
        last_reason = radar_error_reason(data)
        detail = f"HTTP {response.status_code}: {last_reason}"
        print(f"Radar point not accepted ({detail}).")
        if result is not None:
            result['detail'] = detail
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
            success, _ = answer(point["latitude"], point["longitude"], require_distance=False)
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
