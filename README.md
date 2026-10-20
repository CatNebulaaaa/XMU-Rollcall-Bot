# XMU Rollcall Bot · CatNebulaaaa Fork

这是 [CatNebulaaaa](https://github.com/CatNebulaaaa) 维护的改造版本，基于 [KrsMt-0113/XMU-Rollcall-Bot](https://github.com/KrsMt-0113/XMU-Rollcall-Bot)，保留原作者署名和 MIT 许可证。

## 本 fork 的修改

- 数字签到：旧 `student_rollcalls` 接口缺码时，查询 `timetable_rollcalls`，传入课程 ID 和签到的 UTC 日期，并按签到 ID 精确匹配。
- 雷达签到：普通 `xmu start` 默认启用五个翔安校区点位轮询，不依赖接口返回距离；点位间隔 5 秒，成功立即停止。
- 启动标题为 `XMU Rollcall Bot CLI`，底部显示 `Fork by CatNebulaaaa` 并保留 `KrsMt` 原作者署名。
- 数字签到后，TUI 的 `LAST ROLLCALL` 区域持续显示课程、签到时间、结果和签到码；下一次签到出现时更新，列表清空或同一次签到状态变化不会清除签到码。重新启动程序后从空白状态开始。
- 雷达失败时，TUI 持续显示中文原因、HTTP 状态、可安全展示的机器错误码、处理建议、各点位结果和脱敏诊断文件的实际路径。长错误码和路径自动换行。遇到已结束、设备验证或参数错误等非位置问题时停止本轮点位轮询；未知错误明确提示不能判定为距离问题。
- 修正雷达请求的坐标系和 API 版本：输入继续使用 WGS84，在提交时按官方移动 App 的算法转换为 GCJ-02，并使用 `api_version=1.76`。补全 `radar_out_of_rollcall_scope` 等官方错误码及嵌套响应识别。核查依据见 [RADAR_COMPATIBILITY.md](RADAR_COMPATIBILITY.md)。
- 处理缺距离、非法 JSON、超时、登录拒绝和点位文件错误，避免原来的 `NoneType` 计算崩溃。

## 安装与启动

安装这个 fork，而不是上游 PyPI 版本：

```bash
python -m pip install --upgrade "git+https://github.com/CatNebulaaaa/XMU-Rollcall-Bot.git#subdirectory=xmu-rollcall-cli"
xmu config
xmu start
```

已有账号配置可以继续使用。更新后退出旧进程，再启动 `xmu start`，无需额外点位参数，也无需进入特定目录。

默认点位为学武楼、坤銮楼、文宣楼、西部片区2号楼（学信楼）、西部片区4号楼（启信楼）。坐标位于包内的 `radar_points.json`，取自具名楼宇轮廓的中心，采用 WGS84。

楼宇中心不等于教室或教师的实际位置，因此预设点位不能保证处于签到半径内。HTTP 400 也不一定表示距离过远；应先查看拒绝类别，确认需要调整位置还是处理其他请求问题。目前没有真实雷达提交成功的验证记录。

请继续在点位文件及 `--latitude/--longitude` 中填写 WGS84；程序会在发送请求时转换一次，不要提前把点位转换为 GCJ-02。失败时会自动在 XMU 配置目录保存 `radar_last_rejection.json`，包含中文解释、建议、响应结构、HTTP 状态和受限的机器错误码，不保存原始响应、个人字段值、Cookie 或 Token。写入失败会在界面上明确说明。

例如，服务器返回 `radar_out_of_rollcall_scope` 时，界面显示“当前位置不在签到范围内”，并建议确认实际教室位置；返回 `rollcall_device_already_in_use` 时，显示“设备标识已被占用”，并提示使用官方 App、保留错误码以核查兼容性。HTTP 401/403、429、5xx、非 JSON 和网络超时分别给出对应建议。已在手机完成签到时仍会保留“上次脚本请求”的失败信息，避免把手机签到误认为脚本成功。下一次点名出现时更新该区域。

自定义点位或单个实际位置：

```bash
xmu start --radar-points points.json
xmu start --latitude YOUR_LATITUDE --longitude YOUR_LONGITUDE
```

自定义 JSON 使用以下格式；将占位符替换为实际数字：

```json
{
  "coordinate_system": "WGS84",
  "points": [
    {"name": "YOUR_LOCATION", "latitude": null, "longitude": null}
  ]
}
```

两个坐标都留空的点会跳过，至少需要一个有效点。国内地图上的 GCJ-02 或 BD-09 坐标不能直接填成 WGS84。

## 验证与数据来源

已通过 48 项模拟接口回归测试，并检查安装后的默认启动和界面署名。验证没有提交真实签到；楼宇中心不代表具体教室位置，真实课堂效果仍需验证。

点位来源见 [RADAR_POINTS_SOURCES.json](RADAR_POINTS_SOURCES.json)。地图数据为 © OpenStreetMap contributors，遵循 [ODbL 1.0](https://www.openstreetmap.org/copyright)。楼名与[厦大教学楼资料](https://metc.xmu.edu.cn/fwzn/ggjxfw.htm)及[信息学院楼宇名称公示](https://informatics.xmu.edu.cn/info/1103/12447.htm)核对。

运行测试：

```bash
cd xmu-rollcall-cli
python -m pip install pytest
python -m pytest tests -q
```

## 上游历史文档

以下保留上游原文档，相关版本和更新说明属于上游项目。

<div align="center">

  <img src="https://socialify.git.ci/KrsMt-0113/XMU-Rollcall-Bot/image?font=JetBrains+Mono&forks=1&language=1&name=1&owner=1&pattern=Plus&stargazers=1&theme=Light" />

</div>

<div align="center">

  <img src="https://img.shields.io/github/directory-file-count/KrsMt-0113/XMU-Rollcall-Bot" />
  <img src="https://img.shields.io/github/languages/code-size/KrsMt-0113/XMU-Rollcall-Bot" />

</div>

---

> 由于事务繁忙，近期无计划更新本项目，用不了的话，那你就 **好好上课** 。
> 
> *but:*
> ```javascript
> 对于 iOS 用户，以下提供一种替代方案: Shortcut(快捷指令).
> 
> Shortcut 提供了在 Safari 浏览器中执行 JavaScript 脚本的能力, 可以在 Safari 中登录平台后执行脚本达到目的.
> 登录后需'请求桌面网站', 因为以下语句都在 base_url='https://lnt[.]xmu[.]edu[.]cn' 的前提下正常执行.
> 以下是示例脚本:
> 
> fetch('/api/radar/rollcalls')
>   .then(r=>r.text())
>   .then(completion)
>   .catch(e=>completion(String(e))); //获得签到列表
> 
> 获得到签到列表后, 提取出 rollcall_id, 此处可插入一段通知展示待签到课程.
> 
> fetch('/api/rollcall/__rollcall_id__/student_rollcalls') // __rollcall_id__ 处插入魔法变量, 下同
>   .then(r=>r.text())
>   .then(completion)
>   .catch(e=>completion(String(e))) //获得神秘数字
> 
> 以防最终签到失败, 可在此处插入通知展示神秘数字.
> 
> const deviceId=crypto.randomUUID(); //生成设备标识符
> fetch('/api/rollcall/__rollcall_id__/answer_number_rollcall',{
>   method:'PUT',
>   headers:{'Content-Type':'application/json'},
>   body:JSON.stringify({
>     'deviceId':String(deviceId),
>     'numberCode':String(__numbercode__) //此处插入魔法变量
>   })
> })
>   .then(r=>r.text())
>   .then(completion)
>   .catch(e=>completion(String(e)));
> 
> 完成仪式之后, 插入一条通知表明进度. 当然, 以上三段程式码可以合并, 省去利用快捷方式笨拙的方法提取变量的过程.
> 
> 对于 Android 用户, 据说也存在类似 Shortcut 的能力, 如有实现方法同上.
> 
> Windows / MacOS / Linux 等桌面操作系统, 在浏览器的开发者工具控制台执行以上语句即可.
> ```

---

以下是原文档.

---

[使用手册](https://krsmt.notion.site/cli-doc)

> [!WARNING]
> 2026-05-12 之前的登录方式已被弃用。使用 `pip install -U xmulogin` 更新相关组件到最新版本。
>
> 2026-05-15 ~登录组件出现新的问题，等待进一步排查修复。~
>
> 2026-05-15 降级`xmulogin`组件以恢复正常: `pip install xmulogin==1.0.0`

## 快速开始

```bash
pip install xmu-rollcall-cli
```

## 使用方法

```bash
xmu config  # 配置账号。使用统一身份认证账号密码。
xmu switch  # 切换账号。
xmu start   # 启动监控。
```

## 其他

[数字化教学平台附件下载器](https://chromewebstore.google.com/detail/imannochailfofibofphcpmlddlbbhao?utm_source=item-share-cb)
