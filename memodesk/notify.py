"""바탕화면 알림(Windows 토스트). 실패해도 작업을 멈추지 않는다.

PowerShell 로 띄운다 — 추가 설치가 필요 없다. 제목 · 본문은 환경 변수로 넘긴다(명령줄 따옴표에 한글 · 특수문자가 섞이면 깨진다).
"""

from __future__ import annotations

import os
import subprocess

POWERSHELL_APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"

SCRIPT = r"""
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$template = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02)
$texts = $template.GetElementsByTagName('text')
$texts.Item(0).AppendChild($template.CreateTextNode($env:NOTIFY_TITLE)) > $null
$texts.Item(1).AppendChild($template.CreateTextNode($env:NOTIFY_BODY)) > $null
$toast = [Windows.UI.Notifications.ToastNotification]::new($template)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier($env:NOTIFY_APP).Show($toast)
"""


def toast(title: str, body: str) -> bool:
    """알림을 띄웠으면 True. Windows 가 아니거나 실패하면 False."""
    if os.name != "nt":
        return False
    env = {**os.environ, "NOTIFY_TITLE": title[:120], "NOTIFY_BODY": body[:240], "NOTIFY_APP": POWERSHELL_APP_ID}
    try:
        result = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", SCRIPT],
                                env=env, capture_output=True, timeout=30)
        return result.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
