import time
from datetime import datetime, timezone
from .verify import send_code, send_radar

def process_rollcalls(data, session, location=None, radar_points=None, last_rollcall=None):
    """处理签到数据"""
    data_empty = {'rollcalls': []}
    result = handle_rollcalls(data, session, location, radar_points, last_rollcall)
    if False in result:
        return data_empty
    else:
        return data

def extract_rollcalls(data):
    """提取签到信息"""
    rollcalls = data['rollcalls']
    result = []
    if rollcalls:
        rollcall_count = len(rollcalls)
        for rollcall in rollcalls:
            result.append({
                'course_id': rollcall.get('course_id'),
                'course_title': rollcall['course_title'],
                'created_by_name': rollcall['created_by_name'],
                'department_name': rollcall['department_name'],
                'is_expired': rollcall['is_expired'],
                'is_number': rollcall['is_number'],
                'is_radar': rollcall['is_radar'],
                'rollcall_id': rollcall['rollcall_id'],
                'rollcall_status': rollcall['rollcall_status'],
                'rollcall_time': rollcall.get('rollcall_time'),
                'scored': rollcall['scored'],
                'status': rollcall['status']
            })
    else:
        rollcall_count = 0
    return rollcall_count, result

def remember_rollcall(last_rollcall, rollcall, rollcall_type, result, number_code=None):
    """Keep the newest non-expired rollcall for dashboard redraws."""
    if last_rollcall is None:
        return
    try:
        def parsed_time(value):
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        if last_rollcall and parsed_time(rollcall['rollcall_time']) < parsed_time(last_rollcall['rollcall_time']):
            return
    except (TypeError, ValueError):
        pass
    if last_rollcall.get('rollcall_id') != rollcall['rollcall_id']:
        last_rollcall.clear()
    last_rollcall.update(
        rollcall_id=rollcall['rollcall_id'], course_title=rollcall['course_title'],
        rollcall_time=rollcall['rollcall_time'], rollcall_type=rollcall_type, result=result,
    )
    if number_code is not None:
        last_rollcall['number_code'] = number_code


def handle_rollcalls(data, session, location=None, radar_points=None, last_rollcall=None):
    """处理签到流程"""
    count, rollcalls = extract_rollcalls(data)
    answer_status = [False for _ in range(count)]

    if count:
        print(time.strftime("%H:%M:%S", time.localtime()), f"New rollcall(s) found!\n")
        for i in range(count):
            number_result = {}
            radar_result = {}
            print(f"{i+1} of {count}:")
            print(f"Course name: {rollcalls[i]['course_title']}, rollcall created by {rollcalls[i]['department_name']} {rollcalls[i]['created_by_name']}.")

            if rollcalls[i]['is_radar']:
                temp_str = "Radar rollcall"
            elif rollcalls[i]['is_number']:
                temp_str = "Number rollcall"
            else:
                temp_str = "QRcode rollcall"
            print(f"Rollcall type: {temp_str}\n")

            if rollcalls[i]['is_expired']:
                print("Rollcall expired; skipping.")
                answer_status[i] = True
                continue
            elif (rollcalls[i]['status'] == 'absent') & (rollcalls[i]['is_number']) & (not rollcalls[i]['is_radar']):
                if send_code(
                    session,
                    rollcalls[i]['rollcall_id'],
                    rollcalls[i]['course_id'],
                    rollcalls[i]['rollcall_time'],
                    result=number_result,
                ):
                    answer_status[i] = True
                else:
                    print("Answering failed.")
            elif rollcalls[i]['status'] == 'on_call_fine':
                print("Already answered.")
                answer_status[i] = True
            elif rollcalls[i]['is_radar']:
                if send_radar(session, rollcalls[i]['rollcall_id'], location, radar_points, result=radar_result):
                    answer_status[i] = True
                else:
                    print("Answering failed.")
            else:
                # TODO: qrcode rollcall
                print("Answering failed. QRcode rollcall not supported yet.")

            result = "Answered successfully" if answer_status[i] else "Answering failed"
            if rollcalls[i]['status'] == 'on_call_fine':
                result = "Already answered"
            elif radar_result.get('detail'):
                result = radar_result['detail']
            remember_rollcall(last_rollcall, rollcalls[i], temp_str, result, number_result.get('number_code'))
            if last_rollcall is not None and last_rollcall.get('rollcall_id') == rollcalls[i]['rollcall_id'] and radar_result:
                last_rollcall['radar_diagnostic'] = radar_result.get('diagnostic')
                last_rollcall['radar_attempts'] = radar_result.get('attempts', [])

    return answer_status

