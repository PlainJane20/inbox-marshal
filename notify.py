"""Native macOS notification banner via osascript — no new dependency,
no new account, works because this runs on the same Mac you're using."""

import subprocess


def send_macos_notification(title: str, message: str):
    script = f'display notification "{message}" with title "{title}"'
    try:
        subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass  # non-macOS or osascript unavailable — silently skip, don't crash the scan over a notification
