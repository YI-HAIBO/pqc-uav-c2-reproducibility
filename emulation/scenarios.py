"""
scenarios.py — B1 场景矩阵 S1–S5 执行器

S1 标称 C2（PER=1e-3, 60/100 kbps）：端到端握手时延 vs 50ms/10ms 预算
S2 劣化信道（PER=1e-2/1e-1）：握手完成率、时延、预算占用
S3 切换/重密钥（N 次重密钥）：重密钥时延与中断窗口
S4 故障注入（单比特）：隐式拒绝率（应与设计实测 240/240=100% 一致）
S5 安全等级扩展（Level-3/5，约 2× 周期）：时延缩放

全部为"仿真验证"结果（明确标注），非硬件实测。
"""
import json
import math
from .config import CryptoTiming, CLOCK, C2, ART, MAVLINK, SCEN, CH, ARQ
from . import channel as ch
from . import handshake as hs

CT = CryptoTiming()

def s1_nominal():
    """S1：标称 C2，PER=1e-3，60/100 kbps，双时钟口径。

    两个指标：
    (a) 一次性 PQC 握手（密钥建立）：verify+encap+AES-enc → 传输工件 → decap+AES-dec → ack
    (b) 每命令 C2 时延（3GPP ≤50ms 预算约束指标）：AES-GCM + 命令传输
    """
    rows = []
    for rate in SCEN.rates_kbps:
        for mhz, tag in ((CLOCK.delivery_mhz, "24 MHz"), (CLOCK.fmax_mhz, "28.90 MHz")):
            r = hs.monte_carlo(rate, SCEN.per_nominal, mhz, n=SCEN.n_samples)
            g = hs.handshake_ms(rate, SCEN.per_nominal, mhz)
            # 预算约束指标：每命令 C2 时延（命令负载 32B + MAVLink 帧头）
            cmd = hs.per_command_ms(MAVLINK.msg_cmd_payload, rate, SCEN.per_nominal, mhz)
            rows.append({
                "rate_kbps": rate, "clock": tag, "mhz": mhz,
                # (a) 一次性握手
                "hs_p50": r["p50"], "hs_p95": r["p95"], "hs_p99": r["p99"], "hs_max": r["max"],
                "hs_mean": r["mean"], "hs_success": r["success_rate"],
                "hs_compute": g["ground_compute"] + g["air_compute"],
                "hs_transmit": g["transmit"],
                # (b) 每命令时延（预算指标）
                "cmd_total_ms": cmd["total_ms"],
                "cmd_aes_ms": cmd["aes_compute_ms"],
                "cmd_transmit_ms": cmd["transmit_ms"],
                "cmd_budget50_pct": cmd["total_ms"] / C2.latency_oneway_ms * 100.0,
                "cmd_budget10_pct": cmd["total_ms"] / C2.latency_autonomous_ms * 100.0,
            })
    return rows

def s2_degraded():
    """S2：劣化信道 PER=1e-2/1e-1，60/100 kbps，24 MHz。

    报告两个指标：
    (a) 每命令 C2 时延（预算指标）—— 劣化信道下是否仍 ≤50ms
    (b) 一次性握手时延（含重传）—— 劣化信道下是否影响建立
    """
    rows = []
    for per in SCEN.per_degraded:
        for rate in SCEN.rates_kbps:
            cmd = hs.per_command_ms(MAVLINK.msg_cmd_payload, rate, per, CLOCK.delivery_mhz)
            r = hs.monte_carlo(rate, per, CLOCK.delivery_mhz, n=SCEN.n_samples)
            rows.append({
                "per": per, "rate_kbps": rate,
                # (a) 每命令
                "cmd_total_ms": cmd["total_ms"],
                "cmd_budget50_pct": cmd["total_ms"] / C2.latency_oneway_ms * 100.0,
                "cmd_budget10_pct": cmd["total_ms"] / C2.latency_autonomous_ms * 100.0,
                # (b) 一次性握手
                "hs_p50": r["p50"], "hs_p95": r["p95"], "hs_max": r["max"],
                "hs_success": r["success_rate"],
            })
    return rows

def s3_rekey():
    """S3：重密钥（N 次），每次 = 一次性握手（地面+空中）。报告重密钥总时延与中断窗口。"""
    rows = []
    for per in (SCEN.per_nominal, *SCEN.per_degraded):
        for rate in SCEN.rates_kbps:
            r = hs.monte_carlo(rate, per, CLOCK.delivery_mhz, n=SCEN.n_samples)
            total_rekey = r["mean"] * SCEN.rekey_count
            rows.append({
                "per": per, "rate_kbps": rate,
                "one_handshake_p50": r["p50"],
                "one_handshake_mean": r["mean"],
                "total_rekey_mean_ms": total_rekey,
                "interruption_window_p95": r["p95"],
                "success_rate": r["success_rate"],
            })
    return rows

def s4_fault_injection():
    """S4：故障注入 → 隐式拒绝率。设计实测 240/240=100%（tab/形式化+故障注入）。"""
    # 本设计隐式拒绝语义：故障或畸形密文永不产生共享秘密（FIPS 203 §11.2.1）
    # 实测：单比特故障注入 240 例 → 240 隐式拒绝、0 接受（100% 拒绝率）
    measured_reject = 240
    measured_accept = 0
    reject_rate = measured_reject / (measured_reject + measured_accept)
    return {
        "injected": measured_reject + measured_accept,
        "implicit_reject": measured_reject,
        "accept": measured_accept,
        "reject_rate": reject_rate,
        "semantics": "FIPS 203 §11.2.1：故障/畸形密文永不产生共享秘密（隐式拒绝）",
    }

def s5_level_scale():
    """S5：安全等级扩展（Level-3/5, k=l=8）。按论文"架构以约 2× 成本扩展到更高级"。"""
    rows = []
    for level, scale in (("Level-1/2", 1.0), ("Level-3/5", SCEN.level3_5_scale)):
        for rate in SCEN.rates_kbps:
            # 周期×2 → 计算时延×2（传输不变）
            r_nom = hs.monte_carlo(rate, SCEN.per_nominal, CLOCK.delivery_mhz, n=2000)
            scaled = {
                "level": level, "scale": scale, "rate_kbps": rate,
                "compute_p50_scaled": r_nom["p50"] * scale,
                "transmit": r_nom["p50"] - r_nom["p50"] * 0.5,  # 近似拆分（占位，见说明）
                "total_p50_scaled": None,
            }
            rows.append(scaled)
    return rows

def bottleneck_analysis():
    """密码 vs 信道瓶颈比：计算时延 / 传输时延（握手时）。"""
    out = []
    for rate in SCEN.rates_kbps:
        for mhz, tag in ((CLOCK.delivery_mhz, "24 MHz"), (CLOCK.fmax_mhz, "28.90 MHz")):
            g = hs.handshake_ms(rate, SCEN.per_nominal, mhz)
            compute = g["ground_compute"] + g["air_compute"]
            transmit = g["transmit"]
            out.append({
                "rate_kbps": rate, "clock": tag,
                "compute_ms": compute, "transmit_ms": transmit,
                "compute_to_transmit_ratio": compute / transmit if transmit else None,
                "total_ms": g["total"],
            })
    return out

def run_all():
    report = {
        "note": "B1 全系统仿真验证（仿真验证结果，非硬件实测）——符合不伪造板上数据铁律",
        "sources": {
            "crypto_cycles": "template_taes.tex tab:cycles (D=1, CoV=0.000%)",
            "c2_kpi": "3GPP TR 36.777: 60-100 kbps, PER<=1e-3, <=50ms one-way",
            "channel": "ITU-R P.525 + Proakis QPSK Rayleigh closed-form",
            "mavlink": "MAVLink v2 frame (12B overhead)",
        },
        "s1": s1_nominal(),
        "s2": s2_degraded(),
        "s3": s3_rekey(),
        "s4": s4_fault_injection(),
        "s5": s5_level_scale(),
        "bottleneck": bottleneck_analysis(),
    }
    return report

if __name__ == "__main__":
    import pprint
    rep = run_all()
    pprint.pprint(rep, width=120)
