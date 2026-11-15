"""
figures.py — B1 支撑图件生成（读取 output/b1_scenarios.json）

产出（output/figures/）：fig_b1_cmd_latency、fig_b1_handshake_breakdown、
fig_b1_per_sensitivity、fig_b1_rekey。矢量 PDF（稿件）+ PNG（预览）。
"""
import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)  # work/08_refit
OUT = os.path.join(BASE, "output", "figures")
os.makedirs(OUT, exist_ok=True)

C_BLUE = "#1F4E79"; C_RED = "#C00000"; C_GRAY = "#A6A6A6"; C_LBLUE = "#5B9BD5"
plt.rcParams.update({
    "font.size": 9, "axes.grid": False, "figure.dpi": 150,
    "axes.edgecolor": "#444444", "axes.labelcolor": "#222222",
    "text.color": "#222222", "xtick.color": "#444444", "ytick.color": "#444444",
})

def load():
    with open(os.path.join(BASE, "output", "b1_scenarios.json"), encoding="utf-8") as f:
        return json.load(f)

def save(fig, name):
    fig.savefig(os.path.join(OUT, name + ".pdf"), bbox_inches="tight")
    fig.savefig(os.path.join(OUT, name + ".png"), bbox_inches="tight")
    plt.close(fig)

def fig_cmd_latency(rep):
    """每命令 C2 时延 vs 数据率，带 50ms/10ms 预算参考线。"""
    s1 = rep["s1"]
    rates = sorted({r["rate_kbps"] for r in s1})
    cmd = [r["cmd_total_ms"] for r in s1 if r["mhz"] == 24.0]
    cmd = [cmd[rates.index(r)] if False else r for r in [] ]  # placeholder
    # 按 rate 排序取 24MHz
    vals = [next(r["cmd_total_ms"] for r in s1 if r["rate_kbps"] == rt and r["mhz"] == 24.0) for rt in rates]
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    bars = ax.bar([str(int(r)) for r in rates], vals, color=C_BLUE, width=0.5)
    ax.axhline(50, color=C_RED, ls="--", lw=1.2, label="50 ms (3GPP C2 one-way)")
    ax.axhline(10, color=C_GRAY, ls=":", lw=1.2, label="10 ms (autonomous)")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width()/2, v + 0.5, f"{v:.1f}", ha="center", fontsize=8)
    ax.set_ylabel("Per-command C2 latency (ms)")
    ax.set_xlabel("C2 data rate (kbps)")
    ax.set_title("Per-command C2 latency vs data rate (24 MHz)")
    ax.set_ylim(0, 60); ax.legend(fontsize=7, frameon=False)
    save(fig, "fig_b1_cmd_latency")

def fig_handshake_breakdown(rep):
    """一次性握手分解：计算 vs 传输（堆叠柱）。"""
    s1 = [r for r in rep["s1"] if r["mhz"] == 24.0]
    labels = [f'{int(r["rate_kbps"])} kbps' for r in s1]
    compute = [r["hs_compute"] for r in s1]
    transmit = [r["hs_transmit"] for r in s1]
    x = np.arange(len(s1))
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    ax.bar(x, transmit, color=C_BLUE, label="Channel transmit (MAVLink+ARQ)")
    ax.bar(x, compute, bottom=transmit, color=C_RED, label="PQC compute (G1+A1)")
    for i, (c, t) in enumerate(zip(compute, transmit)):
        ax.text(i, t + c + 4, f"{c:.0f}+{t:.0f}", ha="center", fontsize=8)
    ax.set_xticks(x); ax.set_xticklabels(labels)
    ax.set_ylabel("One-time handshake (ms)")
    ax.set_title("PQC key establishment: compute vs transmit (24 MHz)")
    ax.legend(fontsize=7, frameon=False)
    save(fig, "fig_b1_handshake_breakdown")

def fig_per_sensitivity(rep):
    """PER 敏感性：每命令时延 + 一次性握手 vs PER（60 kbps, 24 MHz）。"""
    pts = []
    for per in (1e-3, 1e-2, 1e-1):
        cmd = None; hs = None
        for r in rep["s1"]:
            if r["rate_kbps"] == 60.0 and r["mhz"] == 24.0 and per == 1e-3:
                cmd = r["cmd_total_ms"]; hs = r["hs_p50"]
        for r in rep["s2"]:
            if r["rate_kbps"] == 60.0 and r["per"] == per:
                cmd = r["cmd_total_ms"]; hs = r["hs_p50"]
        pts.append((per, cmd, hs))
    x = [p[0] for p in pts]
    fig, ax = plt.subplots(figsize=(5.0, 3.2))
    ax.plot(x, [p[1] for p in pts], "o-", color=C_BLUE, label="Per-command latency")
    ax.plot(x, [p[2] for p in pts], "s-", color=C_RED, label="One-time handshake")
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlabel("Packet error rate (PER)"); ax.set_ylabel("Latency (ms)")
    ax.set_title("Latency vs PER (60 kbps, 24 MHz)")
    ax.legend(fontsize=7, frameon=False); ax.grid(True, which="both", alpha=0.2)
    save(fig, "fig_b1_per_sensitivity")

def fig_rekey(rep):
    """重密钥中断窗口：每次握手时延。"""
    s3 = [r for r in rep["s3"]]
    labels = [f'{int(r["rate_kbps"])}k/{r["per"]:g}' for r in s3]
    vals = [r["one_handshake_p50"] for r in s3]
    x = np.arange(len(s3))
    fig, ax = plt.subplots(figsize=(5.6, 3.2))
    ax.bar(x, vals, color=[C_RED if r["per"] > 0.01 else C_BLUE for r in s3], width=0.6)
    ax.set_xticks(x); ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=7)
    ax.set_ylabel("Rekey interruption window (ms)")
    ax.set_title("Per-rekey C2 interruption window (one handshake)")
    save(fig, "fig_b1_rekey")

def main():
    rep = load()
    fig_cmd_latency(rep)
    fig_handshake_breakdown(rep)
    fig_per_sensitivity(rep)
    fig_rekey(rep)
    print("图件已生成:", sorted(os.listdir(OUT)))

if __name__ == "__main__":
    main()
