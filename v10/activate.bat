@echo off
REM === 电波对决争锋 - 环境激活 ===
REM 每次使用项目前运行此文件

set PATH=C:\Users\86186\radioconda\Library\bin;C:\Users\86186\radioconda\Scripts;C:\Users\86186\radioconda;%PATH%
set PYTHONPATH=C:\Users\86186\Desktop\hit\src

echo [OK] Radioconda + project environment activated
echo.

REM 验证驱动
python -c "import adi; import iio; from wireless_competition.sdr.pluto import PlutoSDRDevice; d=PlutoSDRDevice(); print('Mode:', 'SIM' if d.is_simulation else 'HARDWARE', '| OK')"

echo.
echo Commands:
echo   仿真: python -m wireless_competition.cli.transmit input.bin --team-id 0 --sim --sim-snr 20 --output recovered.bin
echo   发射: python -m wireless_competition.cli.transmit input.bin --team-id 0 --freq 433e6
echo   接收: python -m wireless_competition.cli.receive --team-id 0 --freq 433e6 --output recovered.bin
echo.
cmd /k
