"""OFDM 调制解调器。

完整的 OFDM 物理层：IFFT/FFT + 循环前缀 + 导频 + 信道估计。
参数：子载波数、CP长度、导频间隔、调制阶数。
"""

from __future__ import annotations

import numpy as np


class OFDMModem:
    """OFDM 调制解调器。

    每个 OFDM 符号 = IFFT(数据子载波 + 导频子载波) + CP。
    接收端：去CP → FFT → 导频信道估计 → 均衡 → 解调。
    """

    def __init__(
        self,
        n_subcarriers: int = 64,
        cp_length: int = 16,
        pilot_spacing: int = 8,
        modulation: str = "bpsk",
    ):
        """
        Args:
            n_subcarriers: 子载波总数（含导频和直流）。
            cp_length: 循环前缀长度。
            pilot_spacing: 导频子载波间距（每隔 N 个数据子载波插一个导频）。
            modulation: 子载波调制方式 ("bpsk" | "qpsk")。
        """
        self.n_subcarriers = n_subcarriers
        self.cp_length = cp_length
        self.pilot_spacing = pilot_spacing
        self.modulation = modulation

        # 子载波分配
        self._dc_idx = n_subcarriers // 2       # 直流子载波（置零）
        self._pilot_indices = self._build_pilot_indices()
        self._data_indices = self._build_data_indices()

        # 导频值（固定 BPSK ±1 序列）
        self._pilot_values = np.array(
            [1, -1, 1, 1, -1, -1, 1, -1] * 20, dtype=np.complex128
        )[:len(self._pilot_indices)]

        self._n_data = len(self._data_indices)
        self._n_pilots = len(self._pilot_indices)

    def _build_pilot_indices(self) -> np.ndarray:
        """构建导频子载波索引（均匀分布，避开 DC）。"""
        pilots = []
        for i in range(self.n_subcarriers):
            if i == self._dc_idx:
                continue
            # 每 pilot_spacing 个子载波放一个导频
            # 用距 DC 的位置计算
            dist_from_dc = abs(i - self._dc_idx)
            if dist_from_dc % self.pilot_spacing == 0:
                pilots.append(i)
        return np.array(pilots, dtype=int)

    def _build_data_indices(self) -> np.ndarray:
        """构建数据子载波索引（非导频、非 DC）。"""
        all_indices = set(range(self.n_subcarriers))
        used = {self._dc_idx} | set(self._pilot_indices)
        return np.array(sorted(all_indices - used), dtype=int)

    # ── 发射端 ──────────────────────────────────────────

    def modulate(self, bits: np.ndarray) -> np.ndarray:
        """比特 → OFDM 时域波形。

        Args:
            bits: 输入比特 (0/1)，长度应为 n_data * bits_per_symbol * N_OFDM_symbols。

        Returns:
            复数 OFDM 时域信号。
        """
        bits = np.asarray(bits, dtype=np.uint8).flatten()
        bits_per_sym = 2 if self.modulation == "qpsk" else 1
        syms_per_ofdm = self._n_data

        # 计算 OFDM 符号数
        n_ofdm_symbols = max(1, len(bits) // (syms_per_ofdm * bits_per_sym))
        bits = bits[:n_ofdm_symbols * syms_per_ofdm * bits_per_sym]

        # 比特→符号
        data_symbols = self._bits_to_symbols(bits)
        data_symbols = data_symbols.reshape(n_ofdm_symbols, syms_per_ofdm)

        # 逐个 OFDM 符号生成
        time_signal = []
        for sym_idx in range(n_ofdm_symbols):
            # 构建频域帧
            freq_frame = np.zeros(self.n_subcarriers, dtype=np.complex128)
            freq_frame[self._dc_idx] = 0.0  # DC 置零
            freq_frame[self._data_indices] = data_symbols[sym_idx]
            freq_frame[self._pilot_indices] = self._pilot_values

            # IFFT
            time_sym = np.fft.ifft(np.fft.ifftshift(freq_frame)) * np.sqrt(self.n_subcarriers)

            # 加 CP
            ofdm_sym = np.concatenate([time_sym[-self.cp_length:], time_sym])
            time_signal.append(ofdm_sym)

        return np.concatenate(time_signal).astype(np.complex128)

    def _bits_to_symbols(self, bits: np.ndarray) -> np.ndarray:
        """比特→复数符号。"""
        if self.modulation == "bpsk":
            return (1.0 - 2.0 * bits.astype(np.float64)).astype(np.complex128)
        else:  # qpsk
            bits = bits.reshape(-1, 2)
            real = 1.0 - 2.0 * bits[:, 0].astype(np.float64)
            imag = 1.0 - 2.0 * bits[:, 1].astype(np.float64)
            return ((real + 1j * imag) / np.sqrt(2)).astype(np.complex128)

    # ── 接收端 ──────────────────────────────────────────

    def demodulate(self, signal: np.ndarray) -> np.ndarray:
        """OFDM 时域波形 → 比特。

        Args:
            signal: 复数 OFDM 时域信号。

        Returns:
            恢复的比特 (0/1)。
        """
        sym_len = self.n_subcarriers + self.cp_length
        n_ofdm = len(signal) // sym_len
        if n_ofdm == 0:
            return np.array([], dtype=np.uint8)

        signal = signal[:n_ofdm * sym_len]

        all_bits = []
        for sym_idx in range(n_ofdm):
            start = sym_idx * sym_len
            ofdm_sym = signal[start:start + sym_len]

            # 去 CP
            time_sym = ofdm_sym[self.cp_length:]

            # FFT
            freq_sym = np.fft.fftshift(np.fft.fft(time_sym)) / np.sqrt(self.n_subcarriers)

            # 导频信道估计（线性插值）
            channel_est = self._channel_estimate(freq_sym)

            # 均衡 + 解调
            data_freq = freq_sym[self._data_indices]
            data_est = channel_est[self._data_indices]
            equalized = data_freq / (data_est + 1e-12)

            bits = self._symbols_to_bits(equalized)
            all_bits.append(bits)

        return np.concatenate(all_bits) if all_bits else np.array([], dtype=np.uint8)

    def _channel_estimate(self, freq_sym: np.ndarray) -> np.ndarray:
        """导频线性插值信道估计。"""
        rx_pilots = freq_sym[self._pilot_indices]
        h_at_pilots = rx_pilots / (self._pilot_values + 1e-12)

        # 线性插值到所有子载波
        h_all = np.zeros(self.n_subcarriers, dtype=np.complex128)
        for i in range(len(self._pilot_indices) - 1):
            p1 = self._pilot_indices[i]
            p2 = self._pilot_indices[i + 1]
            h1 = h_at_pilots[i]
            h2 = h_at_pilots[i + 1]
            for k in range(p1, p2 + 1):
                alpha = (k - p1) / max(1, p2 - p1)
                h_all[k] = h1 + alpha * (h2 - h1)

        # 边缘外推
        if self._pilot_indices[0] > 0:
            h_all[:self._pilot_indices[0]] = h_at_pilots[0]
        if self._pilot_indices[-1] < self.n_subcarriers - 1:
            h_all[self._pilot_indices[-1] + 1:] = h_at_pilots[-1]

        return h_all

    def _symbols_to_bits(self, symbols: np.ndarray) -> np.ndarray:
        """复数符号→比特。"""
        if self.modulation == "bpsk":
            return (np.real(symbols) <= 0).astype(np.uint8)
        else:
            real_bits = (np.real(symbols) <= 0).astype(np.uint8)
            imag_bits = (np.imag(symbols) <= 0).astype(np.uint8)
            bits = np.empty(len(symbols) * 2, dtype=np.uint8)
            bits[0::2] = real_bits
            bits[1::2] = imag_bits
            return bits

    # ── 属性 ──────────────────────────────────────────

    @property
    def bits_per_ofdm_symbol(self) -> int:
        bps = 2 if self.modulation == "qpsk" else 1
        return self._n_data * bps

    @property
    def symbol_length(self) -> int:
        return self.n_subcarriers + self.cp_length

    @property
    def efficiency(self) -> float:
        """频谱效率 = 数据子载波 / (总子载波 + CP)。"""
        return self._n_data / (self.n_subcarriers + self.cp_length)

    def summary(self) -> dict:
        return {
            "n_subcarriers": self.n_subcarriers,
            "cp_length": self.cp_length,
            "pilot_spacing": self.pilot_spacing,
            "modulation": self.modulation,
            "n_data_carriers": self._n_data,
            "n_pilot_carriers": self._n_pilots,
            "bits_per_ofdm_symbol": self.bits_per_ofdm_symbol,
            "symbol_length": self.symbol_length,
            "efficiency": f"{self.efficiency:.2%}",
        }
