"""
handshake.py — B1 C2 握手协议与端到端时延模型

拓扑（见 B2 安全架构 §3.1）：
[地面]  GCS ── C2安全引擎(ML-DSA验证+ML-KEM封装+AES-GCM加密) ── 数传modem ══C2链路══ 数传modem ── C2安全引擎(ML-KEM解封装+AES-GCM解密) ── 飞控 [空中]

握手时间线：
  G1 地面计算：verify(253,202) + encaps(84,101) + AES-enc(515~568) + 协议开销
  T1 传输：握手工件(1,568 B) 经 C2 链路（速率 + PER + ARQ）
  A1 空中计算：decap(103,340) + AES-dec(515~568)
  T2 回传确认/遥测：小包

全部时延为"仿真验证"结果（明确标注），非硬件实测 —— 符合项目不伪造板上数据铁律。
"""
import random
from .config import (CryptoTiming, CLOCK, C2, ART, MAVLINK, SCEN, ARQ)
from . import channel as ch

CT = CryptoTiming()

def cycles_to_ms(cycles: float, mhz: float) -> float:
    return cycles / (mhz * 1000.0)

def mavlink_frame_count(payload_bytes: int) -> tuple:
    """返回 (帧数, 每帧总字节)。按 MAVLink v2 拆分：每帧负载上限 255B。"""
    max_payload = 255
    n = max(1, -(-payload_bytes // max_payload))
    return n, MAVLINK.frame_overhead + min(payload_bytes, max_payload)

def frame_airtime_ms(payload_bytes: int, rate_kbps: float) -> float:
    """单帧空口时延（不含重传）：帧总字节 / 数据率。"""
    n, frame_bytes = mavlink_frame_count(payload_bytes)
    total_bytes = n * frame_bytes
    return total_bytes * 8.0 / (rate_kbps * 1000.0) * 1000.0  # ms

def transmit_ms(payload_bytes: int, rate_kbps: float, per: float,
                rng: random.Random = None) -> tuple:
    """传输时延（含 ARQ 重传）。返回 (期望时延 ms, 标准差 ms, 成功率)。"""
    frame_ms = frame_airtime_ms(payload_bytes, rate_kbps)
    # 帧级 PER（若载荷多帧，按帧独立）
    n, _ = mavlink_frame_count(payload_bytes)
    if n == 1:
        return ch.arq_latency_ms(per, frame_ms)
    # 多帧：每帧独立 ARQ，整体成功 = 全部帧成功
    per_frame = 1.0 - (1.0 - per) ** (1.0 / n) if per < 1.0 else per
    exp_lat, std_lat, _ = ch.arq_latency_ms(per_frame, frame_ms)
    success = ch.arq_success_prob(per_frame) ** n
    return exp_lat, std_lat, success

# ------------------------------------------------------------
# 端到端 C2 握手时延（确定性 + 信道随机性）
# ------------------------------------------------------------
def handshake_ms(rate_kbps: float, per: float, mhz: float = None,
                 rng: random.Random = None, include_decap: bool = True) -> dict:
    """单次 C2 握手端到端时延（ms）。

    返回 dict：ground_compute / air_compute / transmit / total / success。
    mhz 缺省取 delivery 24 MHz（保守口径），可选 28.90 MHz。
    """
    mhz = mhz if mhz is not None else CLOCK.delivery_mhz
    rng = rng or random
    # G1 地面计算：verify + encaps + AES-enc + 协议开销
    aes_enc = rng.randint(*CT.aes_gcm_cycles)
    ground_cycles = CT.verify_e2e_cycles + CT.encaps_cycles + aes_enc + CT.protocol_overhead_cycles
    ground_compute = cycles_to_ms(ground_cycles, mhz)
    # A1 空中计算：decap + AES-dec
    aes_dec = rng.randint(*CT.aes_gcm_cycles)
    air_cycles = CT.decaps_cycles + aes_dec
    air_compute = cycles_to_ms(air_cycles, mhz)
    # T1 传输握手工件
    t1, t1_std, succ1 = transmit_ms(ART.handshake_bytes, rate_kbps, per, rng)
    # T2 回传确认（小包）
    t2, _, succ2 = transmit_ms(MAVLINK.msg_telem_payload, rate_kbps, per, rng)
    total = ground_compute + t1 + air_compute + t2
    return {
        "ground_compute": ground_compute,
        "air_compute": air_compute,
        "transmit": t1 + t2,
        "transmit_std": t1_std,
        "total": total,
        "success": succ1 * succ2,
        "rate_kbps": rate_kbps,
        "per": per,
        "mhz": mhz,
    }

def per_command_ms(payload_bytes: int, rate_kbps: float, per: float,
                   mhz: float = None, rng: random.Random = None) -> dict:
    """单条 C2 命令的端到端时延（预算约束指标）：AES-GCM 加/解密 + 命令传输。

    3GPP TR 36.777 的 ≤50ms 单程时延约束的是【逐命令消息】C2 时延，
    而非一次性密钥建立（handshake）。此函数给出预算指标。
    """
    mhz = mhz if mhz is not None else CLOCK.delivery_mhz
    rng = rng or random
    aes = rng.randint(*CT.aes_gcm_cycles)
    # 加/解密各一次（地面加密、空中解密）
    aes_compute = cycles_to_ms(aes * 2, mhz)
    t_tx, _, succ = transmit_ms(payload_bytes, rate_kbps, per, rng)
    return {
        "payload_bytes": payload_bytes,
        "aes_compute_ms": aes_compute,
        "transmit_ms": t_tx,
        "total_ms": aes_compute + t_tx,
        "success": succ,
        "rate_kbps": rate_kbps, "per": per, "mhz": mhz,
    }

def monte_carlo(rate_kbps: float, per: float, mhz: float = None,
                n: int = None, seed: int = 42) -> dict:
    """蒙特卡洛 N 次握手 → 时延分布统计（p50/p95/max/mean/std）与平均成功率。"""
    n = n if n is not None else SCEN.n_samples
    rng = random.Random(seed)
    totals, succ_sum = [], 0.0
    for _ in range(n):
        r = handshake_ms(rate_kbps, per, mhz, rng)
        totals.append(r["total"])
        succ_sum += r["success"]
    totals.sort()
    mean = sum(totals) / n
    def pct(p):
        return totals[min(n - 1, int(p * n))]
    return {
        "rate_kbps": rate_kbps, "per": per, "mhz": mhz, "n": n,
        "mean": mean,
        "p50": pct(0.50), "p95": pct(0.95), "p99": pct(0.99),
        "max": totals[-1], "std": (sum((t - mean) ** 2 for t in totals) / n) ** 0.5,
        "success_rate": succ_sum / n,
    }
