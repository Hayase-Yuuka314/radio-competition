import os
import time
import subprocess

RUN_TIME = 270      # 4分30秒
CHECK_INTERVAL = 0.02

s = ""

start_time = time.time()

while time.time() - start_time < RUN_TIME:

    # 启动 final.py
    proc = subprocess.Popen(["python", "final.py"])

    try:
        while time.time() - start_time < RUN_TIME:

            if os.path.exists("1.txt"):

                # 等待文件写完
                while True:
                    try:
                        with open("1.txt", "r", encoding="utf-8") as f:
                            data = f.read()
                        break
                    except PermissionError:
                        time.sleep(0.01)

                s += data

                os.remove("1.txt")

                print(f"收到一次数据，长度 {len(data)}")

                # 收到一次数据立即结束本次final.py
                if proc.poll() is None:
                    proc.terminate()

                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()

                # 开始下一轮
                break

            time.sleep(CHECK_INTERVAL)

    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                proc.kill()

# 保存最终结果
with open("2.txt", "w", encoding="utf-8") as f:
    f.write(s)

print("完成，共接收 {} 字符".format(len(s)))