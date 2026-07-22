# tests/operation/test_operation.py
"""operation 脚本自动测试。确保关键脚本在已知输入下产生预期行为。"""
import subprocess, sys, os, glob, tempfile, json

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
OP = os.path.join(ROOT, "operation")


def _run(op_script, *args, timeout=60):
    """运行 operation 脚本并返回 (exit_code, stdout, stderr)。"""
    result = subprocess.run(
        [sys.executable, os.path.join(OP, op_script)] + list(args),
        cwd=ROOT, capture_output=True, timeout=timeout,
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        encoding="utf-8", errors="replace",
    )
    return result.returncode, result.stdout or "", result.stderr or ""


def test_11_e2e_pass():
    """正常通信应 PASS。"""
    ret, out, err = _run("11_contest_e2e.py", "--size", "500", "--mode", "dsss", "--snr", "20")
    assert ret == 0, f"exit={ret}, stderr={err[:200]}"
    assert "[PASS]" in out, f"Expected PASS, got: {out[-200:]}"


def test_11_e2e_fail():
    """极低 SNR 应 FAIL。"""
    ret, out, err = _run("11_contest_e2e.py", "--size", "500", "--mode", "dsss", "--snr", "-50")
    assert ret != 0, f"Expected non-zero exit for failure, got {ret}"
    assert "[FAIL]" in out, f"Expected FAIL, got: {out[-200:]}"


def test_11_e2e_robust():
    """传统稳健模式应 PASS。"""
    ret, out, err = _run("11_contest_e2e.py", "--size", "500", "--mode", "robust", "--snr", "30")
    assert ret == 0, f"exit={ret}"
    assert "[PASS]" in out


def test_00_check():
    """环境检查应 PASS。"""
    ret, out, err = _run("00_check.py", timeout=30)
    assert ret == 0, f"exit={ret}"
    assert "就绪" in out or "OK" in out


def test_04_dsss():
    """DSSS 演示应正常运行。"""
    ret, out, err = _run("04_dsss_demo.py", timeout=30)
    assert ret == 0, f"exit={ret}, stderr={err[:200]}"
    assert "SNR= -10dB" in out


def test_06_contest():
    """多队模拟应正常运行。"""
    ret, out, err = _run("06_contest.py", timeout=30)
    assert ret == 0, f"exit={ret}"


def test_03_simulate():
    """传统仿真应正常运行。"""
    ret, out, err = _run("03_simulate.py", "30", "256", timeout=30)
    assert ret == 0, f"exit={ret}"
    assert "恢复" in out


def test_08_prepare():
    """赛前检查应正常运行。"""
    ret, out, err = _run("08_prepare.py", timeout=30)
    assert ret == 0, f"exit={ret}"


def test_09_tx_sim():
    """09 TX --sim 应生成输出文件。"""
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        test_file = os.path.join(tmp, "test.bin")
        with open(test_file, "wb") as f:
            f.write(b"x" * 256)
        ret, out, err = _run("09_contest_tx.py", "--file", test_file, "--sim",
                             "--mode", "dsss", "--output-dir", tmp, timeout=30)
        assert ret == 0, f"exit={ret}, err={err[:200]}"
        # 应生成 frame_*.npy 文件
        frames = glob.glob(os.path.join(tmp, "**", "frame_*.npy"), recursive=True)
        assert len(frames) > 0, "No frame files generated"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_10_rx_crash_fix():
    """10 RX 传统模式不应崩溃（验证 P1-01 修复）。"""
    import tempfile, shutil
    tmp = tempfile.mkdtemp()
    try:
        test_file = os.path.join(tmp, "test.bin")
        with open(test_file, "wb") as f:
            f.write(b"x" * 256)
        # TX
        ret_tx, out_tx, _ = _run("09_contest_tx.py", "--file", test_file, "--sim",
                                 "--mode", "robust", "--output-dir", tmp, timeout=30)
        assert ret_tx == 0, f"TX failed: exit={ret_tx}, out={out_tx[-300:]}"
        # 找 TX 输出目录
        tx_dirs = []
        for root, dirs, files in os.walk(tmp):
            if any(f.startswith("frame_") and f.endswith(".npy") for f in files):
                tx_dirs.append(root)
        assert len(tx_dirs) > 0, f"TX did not produce frame files in {tmp}"
        # RX
        ret_rx, out_rx, _ = _run("10_contest_rx.py", "--sim", "--tx-dir", tx_dirs[0],
                                 "--mode", "robust", timeout=30)
        assert ret_rx == 0, f"RX failed: exit={ret_rx}, out={out_rx[-300:]}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
