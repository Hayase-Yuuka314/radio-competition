#!/usr/bin/env python
# scripts/probe_sdr_stack.py
# SDR 软件栈探测 — 只读，不发射。
"""用法:
  python scripts/probe_sdr_stack.py --versions
  python scripts/probe_sdr_stack.py --versions --json -
  python scripts/probe_sdr_stack.py --hardware        # 需连接 SDR
"""
import sys, os, json, argparse

VERSION_REPORT = {
    "python": sys.version.split()[0],
    "radioconda": None,
    "gnuradio": None,
    "gr_iio": None,
    "pyadi_iio": None,
    "libiio": None,
    "soapysdr": None,
    "numpy": None,
    "scipy": None,
    "grc": None,
}

# 探测各组件
try:
    import numpy; VERSION_REPORT["numpy"] = numpy.__version__
except: pass

try:
    import scipy; VERSION_REPORT["scipy"] = scipy.__version__
except: pass

try:
    import gnuradio; VERSION_REPORT["gnuradio"] = gnuradio.version()
except: pass

try:
    import adi; VERSION_REPORT["pyadi_iio"] = adi.__version__
except: pass

try:
    import iio; VERSION_REPORT["libiio"] = f"{iio.version[0]}.{iio.version[1]}.{iio.version[2]}"
except: pass

try:
    from gnuradio import iio as gr_iio_mod; VERSION_REPORT["gr_iio"] = "available"
except: pass

try:
    import SoapySDR; VERSION_REPORT["soapysdr"] = SoapySDR.SoapySDR_getAPIVersion()
except: pass

# 检查 conda 环境
VERSION_REPORT["radioconda"] = "detected" if "CONDA_PREFIX" in os.environ else "not in conda"

# 检查 grcc
import shutil
VERSION_REPORT["grc"] = "available" if shutil.which("gnuradio-companion") or shutil.which("grcc") else "not found"


def probe_hardware():
    """只读硬件探测 — 列出 Pluto 设备属性和 URI。不发射。"""
    hw = {"pluto_devices": [], "errors": []}
    try:
        # 方法1: pyadi-iio
        import adi
        ctx = adi.ad9361.ContextManager()
        for uri in ctx.uri_list:
            try:
                sdr = adi.Pluto(uri)
                hw["pluto_devices"].append({
                    "uri": uri,
                    "tx_lo": int(sdr.tx_lo),
                    "rx_lo": int(sdr.rx_lo),
                    "sample_rate": int(sdr.sample_rate),
                    "rf_bandwidth": int(sdr.rf_bandwidth),
                    "gain_control_mode": sdr.gain_control_mode,
                    "tx_hardwaregain": float(sdr.tx_hardwaregain_chan0),
                    "rx_hardwaregain": float(sdr.rx_hardwaregain_chan0),
                })
            except Exception as e:
                hw["errors"].append(f"pyadi-iio {uri}: {e}")
    except Exception as e:
        hw["errors"].append(f"pyadi-iio discovery: {e}")

    # 方法2: libiio context scan
    try:
        import iio
        ctx = iio.scan_context()
        if ctx:
            dev_list = ctx.get_description().split("\n")
            for d in dev_list:
                if d.strip():
                    hw["pluto_devices"].append({"libiio_desc": d.strip()})
    except Exception as e:
        hw["errors"].append(f"libiio scan: {e}")

    return hw


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--versions", action="store_true")
    ap.add_argument("--hardware", action="store_true")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    output = {}
    if args.versions:
        output["versions"] = VERSION_REPORT
    if args.hardware:
        output["hardware"] = probe_hardware()

    if not output:
        ap.print_help()
        return 0

    if args.json == "-":
        json.dump(output, sys.stdout, indent=2, default=str)
    else:
        for section, data in output.items():
            print(f"\n[{section}]")
            if isinstance(data, dict):
                for k, v in data.items():
                    print(f"  {k}: {v}")
            elif isinstance(data, list):
                for item in data:
                    print(f"  {item}")

if __name__ == "__main__":
    sys.exit(main())
