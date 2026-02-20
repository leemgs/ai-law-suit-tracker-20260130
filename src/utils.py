import os

def debug_log(msg: str):
    """
    DEBUG 환경 변수가 '1'일 때만 메세지를 출력합니다.
    """
    if os.environ.get("DEBUG") == "1":
        print(f"[DEBUG] {msg}")
