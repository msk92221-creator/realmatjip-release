"""에뮬레이터 UI 자동화 헬퍼 — 텍스트로 노드 찾아 탭/덤프.

사용법:
    python ui_tap.py dump              # 화면 텍스트 목록
    python ui_tap.py tap "설정"         # 텍스트 노드 중앙 탭
    python ui_tap.py type "검색어"      # 포커스된 필드에 입력 (ASCII)
"""
import re
import subprocess
import sys

ADB = r"C:\Users\msk92\AppData\Local\Android\Sdk\platform-tools\adb.exe"
DEV = "-s"
DEV_ID = "emulator-5554"


def dump_xml() -> str:
    out = subprocess.run([ADB, DEV, DEV_ID, "exec-out", "uiautomator", "dump", "/dev/tty"],
                         capture_output=True, timeout=30)
    return out.stdout.decode("utf-8", "ignore")


def find_bounds(xml: str, text: str):
    m = re.search(
        r'text="' + re.escape(text) + r'"[^>]*bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', xml)
    if not m:
        return None
    x = (int(m.group(1)) + int(m.group(3))) // 2
    y = (int(m.group(2)) + int(m.group(4))) // 2
    return x, y


def tap(x: int, y: int):
    subprocess.run([ADB, DEV, DEV_ID, "shell", "input", "tap", str(x), str(y)], timeout=15)


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dump"
    if cmd == "dump":
        xml = dump_xml()
        texts = [t for t in re.findall(r'text="([^"]{1,70})"', xml) if t.strip()]
        print(" | ".join(texts))
    elif cmd == "tap":
        text = sys.argv[2]
        pos = find_bounds(dump_xml(), text)
        if not pos:
            print(f"NOT_FOUND: {text}")
            return 1
        tap(*pos)
        print(f"TAPPED {text} at {pos}")
    elif cmd == "type":
        subprocess.run([ADB, DEV, DEV_ID, "shell", "input", "text", sys.argv[2]], timeout=15)
        print("TYPED", sys.argv[2])
    elif cmd == "key":
        subprocess.run([ADB, DEV, DEV_ID, "shell", "input", "keyevent", sys.argv[2]], timeout=15)
        print("KEY", sys.argv[2])
    return 0


if __name__ == "__main__":
    sys.exit(main())
