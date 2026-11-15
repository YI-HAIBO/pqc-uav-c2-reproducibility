"""
__main__.py — B1 场景矩阵执行入口

用法（在 work/08_refit 下）：
  python -m b1_emulation            # 运行 S1–S5 + 瓶颈分析，打印报告并保存 JSON
  python -m b1_emulation --json      # 仅保存 JSON 数据文件
"""
import json
import os
import sys
from .scenarios import run_all
from . import handshake as hs
from . import channel as ch
from .config import C2, SCEN

def fmt_row(d, keys):
    return "  ".join(f"{k}={d[k]:.4g}" if isinstance(d[k], float) else f"{k}={d[k]}" for k in keys)

def print_report(rep):
    print("=" * 78)
    print("B1 全系统仿真验证 —— 场景矩阵 S1–S5（仿真验证结果，非硬件实测）")
    print("=" * 78)
    print(f"[来源] 密码时序: {rep['sources']['crypto_cycles']}")
    print(f"[来源] C2 KPI : {rep['sources']['c2_kpi']}")
    print(f"[来源] 信道    : {rep['sources']['channel']}")
    print(f"[来源] 协议    : {rep['sources']['mavlink']}")
    print()

    print("--- S1 标称 C2（PER=1e-3）：一次性握手 + 每命令预算指标 ---")
    k = ["rate_kbps", "clock", "hs_p50", "hs_transmit", "hs_compute", "hs_success",
         "cmd_total_ms", "cmd_transmit_ms", "cmd_aes_ms", "cmd_budget50_pct", "cmd_budget10_pct"]
    for r in rep["s1"]:
        print(fmt_row(r, k))
    print()

    print("--- S2 劣化信道（PER=1e-2/1e-1，24 MHz）：每命令预算 + 一次性握手 ---")
    k = ["per", "rate_kbps", "cmd_total_ms", "cmd_budget50_pct", "cmd_budget10_pct",
         "hs_p50", "hs_max", "hs_success"]
    for r in rep["s2"]:
        print(fmt_row(r, k))
    print()

    print("--- S3 切换/重密钥（10 次）---")
    k = ["per", "rate_kbps", "one_handshake_p50", "total_rekey_mean_ms", "interruption_window_p95", "success_rate"]
    for r in rep["s3"]:
        print(fmt_row(r, k))
    print()

    print("--- S4 故障注入 → 隐式拒绝 ---")
    s4 = rep["s4"]
    print(f"  注入 {s4['injected']} 例 → 隐式拒绝 {s4['implicit_reject']} / 接受 {s4['accept']}（拒绝率 {s4['reject_rate']*100:.1f}%）")
    print(f"  语义: {s4['semantics']}")
    print()

    print("--- S5 安全等级扩展（Level-3/5, ~2× 周期）---")
    k = ["level", "scale", "rate_kbps", "total_p50_scaled"]
    for r in rep["s5"]:
        print(fmt_row(r, k))
    print()

    print("--- 瓶颈分析：密码计算 vs 信道传输 ---")
    k = ["rate_kbps", "clock", "compute_ms", "transmit_ms", "compute_to_transmit_ratio", "total_ms"]
    for r in rep["bottleneck"]:
        print(fmt_row(r, k))
    print()

def save_json(rep, outdir):
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, "b1_scenarios.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rep, f, indent=2, ensure_ascii=False)
    print(f"[JSON] 已保存: {path}")
    return path

def main():
    rep = run_all()
    # 修复 S5 的 total_p50_scaled 占位值
    for r in rep["s5"]:
        # 用 S1 名义拆解计算/传输
        g = hs.handshake_ms(r["rate_kbps"], SCEN.per_nominal, 24.0)
        compute = g["ground_compute"] + g["air_compute"]
        transmit = g["transmit"]
        r["compute_ms"] = compute
        r["transmit_ms"] = transmit
        r["total_p50_scaled"] = transmit + compute * r["scale"]
    outdir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "output")
    save_json(rep, outdir)
    print_report(rep)

if __name__ == "__main__":
    main()
