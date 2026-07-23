import time
import subprocess
import sys

RUN_TIME = 270      # 4分30秒
BLOCK_SIZE = 10
SEND_TIME = 2       # 每次运行 sta.py 的时间

# 读取 pas.txt
with open("pas.txt", "r", encoding="utf-8") as f:
    data = f.read().strip()

if len(data) < BLOCK_SIZE:
    raise ValueError("pas.txt 长度不足 10 个字符！")

index = 0          # 当前读取位置
group = 1          # 当前组号

start_time = time.time()

while time.time() - start_time < RUN_TIME:

    # 取10个字符
    block = data[index:index + BLOCK_SIZE]

    # 组成写入内容：001ABCDEFGHIJ
    output = f"{group:03d}{block}"

    # 写入3.txt
    with open("3.txt", "w", encoding="utf-8") as f:
        f.write(output)

    print("发送：", output)

    # 启动 sta.py
    proc = subprocess.Popen([
    r"E:\rdcd\envs\gnuradio\python.exe",
    "sta.py"
])

    try:
        remaining = RUN_TIME - (time.time() - start_time)
        time.sleep(min(SEND_TIME, remaining))
    finally:
        # 结束 sta.py
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()
                # time.sleep(1000)

    # 更新位置和组号
    index += BLOCK_SIZE
    group += 1

print("发送完成。")