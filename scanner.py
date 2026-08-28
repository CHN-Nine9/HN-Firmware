import os
import time
import re
import urllib.request
import urllib.error
from urllib.parse import urlparse

BASE_URL = os.environ.get("BASE_URL", "https://iknow.service.hihonor.com/weknow/servlet/download/public")
STATE_DIR = "state"
NEXT_START_FILE = os.path.join(STATE_DIR, "next_start.txt")
CSV_FILE = os.path.join(STATE_DIR, "results.csv")
NEW_CSV = os.path.join(STATE_DIR, "new.csv")

os.makedirs(STATE_DIR, exist_ok=True)

# ---------- 常量 ----------
DEFAULT_START = 0
MAX_CONSECUTIVE = 233
MAX_ENTRIES_PER_RUN = 3250   # 每次运行最多检查 3250 个条目

# ---------- 读取起始编号 ----------
if os.path.exists(NEXT_START_FILE):
    with open(NEXT_START_FILE, 'r') as f:
        content = f.read().strip()
        start_num = int(content) if content.isdigit() else DEFAULT_START
else:
    start_num = DEFAULT_START

# ---------- 初始化 CSV ----------
if not os.path.exists(CSV_FILE):
    with open(CSV_FILE, 'w') as f:
        f.write("WValue,ResourceOrStatus\n")
with open(NEW_CSV, 'w') as f:
    f.write("WValue,ResourceOrStatus\n")

# ---------- 扫描循环 ----------
current_num = start_num
consecutive_invalid = 0
checked = 0

print(f"Starting from W{current_num:08d}")

while consecutive_invalid < MAX_CONSECUTIVE and checked < MAX_ENTRIES_PER_RUN:
    w_value = f"W{current_num:08d}"
    url = f"{BASE_URL}?contextNo={w_value}"
    print(f"[{checked+1}] Checking: {url}")

    status_or_filename = ""
    is_valid = False

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            if resp.status == 200:
                is_valid = True
                content_disp = resp.headers.get('Content-Disposition')
                if content_disp:
                    match = re.search(r'filename="?([^";]+)"?', content_disp)
                    if match:
                        status_or_filename = match.group(1)
                if not status_or_filename:
                    parsed = urlparse(url)
                    status_or_filename = parsed.path.split('/')[-1] or "unknown"
            else:
                status_or_filename = str(resp.status)
    except urllib.error.HTTPError as e:
        status_or_filename = str(e.code)
    except Exception as e:
        status_or_filename = f"Error: {type(e).__name__}"

    # 写入两个 CSV
    line = f"{w_value},{status_or_filename}\n"
    with open(CSV_FILE, 'a') as f_results, open(NEW_CSV, 'a') as f_new:
        f_results.write(line)
        f_new.write(line)

    if is_valid:
        print(f"  -> VALID: {status_or_filename}")
        consecutive_invalid = 0
    else:
        consecutive_invalid += 1
        print(f"  -> INVALID ({status_or_filename}), consecutive: {consecutive_invalid}")

    current_num += 1
    checked += 1
    time.sleep(0.1)   # 礼貌性延迟

# ---------- 确定停止原因并计算下一次起始点 ----------
if consecutive_invalid >= MAX_CONSECUTIVE:
    # 因 233 个连续无效停止 → 下一次从该无效段起点重试
    next_start = current_num - MAX_CONSECUTIVE
    should_continue = False
    reason = "consecutive_invalid"
elif checked >= MAX_ENTRIES_PER_RUN:
    # 因达到条目上限停止 → 下一次从下一个未检查的编号继续
    next_start = current_num
    should_continue = True
    reason = "max_entries"
else:
    # 保险兜底（一般不会发生）
    next_start = current_num
    should_continue = False
    reason = "unknown"

# 保存下一次起始点
with open(NEXT_START_FILE, 'w') as f:
    f.write(str(next_start))

# ---------- 向 GitHub Actions 输出标志 ----------
github_output = os.environ.get('GITHUB_OUTPUT')
if github_output:
    with open(github_output, 'a') as f:
        f.write(f"should_continue={str(should_continue).lower()}\n")

print(f"Stopped. Reason: {reason}, checked {checked} entries.")
print(f"Next start will be: W{next_start:08d}")
print(f"should_continue={should_continue}")
