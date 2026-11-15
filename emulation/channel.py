"""
channel.py — B1 信道模型（链路预算 + 衰落 + BER/PER + ARQ）

公式来源（全部可核验）：
- 自由空间路径损耗：ITU-R P.525（PL = 20log10(4πd/λ)）
- QPSK 瑞利衰落闭式误比特率：Proakis, "Digital Communications" 5th ed.
  Pb = (1/2)(1 - sqrt(gamma_bar/(1+gamma_bar)))，gamma_bar = 平均 SNR
- 误包率：PER = 1 - (1-Pb)^L，L = 包比特数
- 停等 ARQ：P(成功≤M 次重传) = 1 - p^(M+1)
"""
import math
import random
from .config import CH, ARQ

def free_space_path_loss_db(freq_ghz: float, dist_km: float) -> float:
    """ITU-R P.525 自由空间路径损耗（dB）。"""
    d_m = dist_km * 1000.0
    lam = 0.299792458 / freq_ghz  # 波长 m
    return 20.0 * math.log10(4.0 * math.pi * d_m / lam)

def log_distance_path_loss_db(freq_ghz: float, dist_km: float, n: float,
                              ref_dist_km: float = 0.001) -> float:
    """对数距离路径损耗 PL(dB) = PL(d0) + 10 n log10(d/d0)，n=路径损耗指数。"""
    pl0 = free_space_path_loss_db(freq_ghz, ref_dist_km)
    return pl0 + 10.0 * n * math.log10(dist_km / ref_dist_km)

def received_snr_db(dist_km: float = None, n: float = None, freq_ghz: float = None,
                    tx_power_dbm: float = None, tx_gain_dbi: float = None,
                    rx_gain_dbi: float = None, noise_fig_dB: float = None,
                    bandwidth_khz: float = None) -> float:
    """链路预算 → 平均接收 SNR（dB）。参数缺省取 config.CH。"""
    dist_km = dist_km if dist_km is not None else CH.distance_km
    n = n if n is not None else CH.path_loss_exp
    freq_ghz = freq_ghz if freq_ghz is not None else CH.freq_ghz
    tx_power_dbm = tx_power_dbm if tx_power_dbm is not None else CH.tx_power_dbm
    tx_gain_dbi = tx_gain_dbi if tx_gain_dbi is not None else CH.tx_gain_dbi
    rx_gain_dbi = rx_gain_dbi if rx_gain_dbi is not None else CH.rx_gain_dbi
    noise_fig_dB = noise_fig_dB if noise_fig_dB is not None else CH.noise_fig_dB
    bandwidth_khz = bandwidth_khz if bandwidth_khz is not None else CH.bandwidth_khz
    pl = log_distance_path_loss_db(freq_ghz, dist_km, n)
    rx_power_dbm = tx_power_dbm + tx_gain_dbi + rx_gain_dbi - pl
    # 噪声功率 = 热噪声 + 10log10(BW) + NF
    bw_hz = bandwidth_khz * 1000.0
    noise_power_dbm = CH.thermal_noise_dbm + 10.0 * math.log10(bw_hz) + noise_fig_dB
    return rx_power_dbm - noise_power_dbm

def ber_qpsk_rayleigh(snr_db: float) -> float:
    """相干 QPSK 瑞利衰落平均误比特率（Proakis 闭式）。"""
    gamma_bar = 10.0 ** (snr_db / 10.0)
    return 0.5 * (1.0 - math.sqrt(gamma_bar / (1.0 + gamma_bar)))

def per_from_ber(ber: float, packet_bytes: int) -> float:
    """误包率：PER = 1 - (1-BER)^(8*packet_bytes)。"""
    bits = 8 * packet_bytes
    return 1.0 - (1.0 - ber) ** bits

def per_from_snr(snr_db: float, packet_bytes: int) -> float:
    """链路级 PER：由 SNR 与包长直接得出（等价于 QPSK Rayleigh + 包长）。"""
    return per_from_ber(ber_qpsk_rayleigh(snr_db), packet_bytes)

# ------------------------------------------------------------
# 停等 ARQ：给定 PER p，计算成功概率 / 期望传输次数 / 期望时延
# ------------------------------------------------------------
def arq_success_prob(per: float, max_retrans: int = None) -> float:
    """P(在 ≤max_retrans 次重传内成功) = 1 - p^(M+1)。"""
    m = max_retrans if max_retrans is not None else ARQ.max_retrans
    return 1.0 - per ** (m + 1)

def arq_expected_transmissions(per: float, max_retrans: int = None) -> float:
    """期望传输次数（含首传；成功即停，最多 M 次重传）。"""
    m = max_retrans if max_retrans is not None else ARQ.max_retrans
    if per >= 1.0:
        return m + 1.0
    return (1.0 - per ** (m + 1)) / (1.0 - per)

def arq_latency_ms(per: float, frame_ms: float, max_retrans: int = None,
                   rtt_propag_ms: float = None) -> tuple:
    """返回 (期望时延 ms, 标准差 ms, 成功率)。时延 = frame_ms*(期望传输) + RTT*(期望重传)。"""
    m = max_retrans if max_retrans is not None else ARQ.max_retrans
    rtt = rtt_propag_ms if rtt_propag_ms is not None else ARQ.rtt_propag_ms
    success = arq_success_prob(per, m)
    exp_tx = arq_expected_transmissions(per, m)
    exp_lat = frame_ms * exp_tx + rtt * (exp_tx - 1.0)
    # 二项式近似标准差（传输次数近似几何分布）
    if per < 1.0:
        std_tx = math.sqrt(per) / (1.0 - per)
    else:
        std_tx = 0.0
    std_lat = frame_ms * std_tx + rtt * std_tx
    return exp_lat, std_lat, success

def sample_arq_retransmissions(per: float, max_retrans: int = None, rng: random.Random = None) -> int:
    """采样一次 ARQ 实际重传次数（用于蒙特卡洛时延分布）。"""
    m = max_retrans if max_retrans is not None else ARQ.max_retrans
    rng = rng or random
    retx = 0
    while retx <= m:
        if rng.random() > per:  # 成功
            return retx
        retx += 1
    return m + 1  # 用尽重传（失败）
