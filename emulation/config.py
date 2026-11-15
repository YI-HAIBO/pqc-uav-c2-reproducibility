"""
config.py — B1 全系统仿真验证：参数配置（全部锚定可核验来源）

数据铁律：所有外部参数均来自权威一手来源（标准号/官方链接），
本设计自身数据取自 tab:cycles / tab:rt（template_taes.tex，已实测/已证）。
任何数字不编造、不推测；无法核验的参数在注释中标注为"假设"并给出理由。
"""
from dataclasses import dataclass, field

# ============================================================
# 1) 密码引擎时序 —— 来源：已投稿 TAES 稿件 tab:cycles（template_taes.tex L405-421）
#    全部为确定性测量（D=1，CoV=0.000%）
# ============================================================
@dataclass(frozen=True)
class CryptoTiming:
    keygen_cycles: int = 57128          # ML-KEM-512 keygen, N=2000
    encaps_cycles: int = 84101          # ML-KEM-512 encapsulation, N=200
    decaps_cycles: int = 103340         # ML-KEM-512 decapsulation, N=200
    decaps_implicit_cycles: int = 105405  # 隐式拒绝路径 (+2.0%)
    verify_core_cycles: int = 249577    # ML-DSA-44 verify core
    verify_e2e_cycles: int = 253202     # ML-DSA-44 verify 端到端(含4576B预像重载, E11)
    sign_cycles: int = 203548           # ML-DSA-44 sign (kappa=0 nominal)
    aes_gcm_cycles: tuple = (515, 568)  # AES-256-GCM 加/解密 (数据相关, 16B/块)
    protocol_overhead_cycles: int = 1653  # E11 观测: 339471 - (253202+84101+515) ≈ 1653 (mailbox/命令往返)

# ============================================================
# 2) 时钟口径 —— 来源：template_taes.tex（tab:rt 双口径）
# ============================================================
@dataclass(frozen=True)
class Clock:
    fmax_mhz: float = 28.90   # 综合 Fmax
    delivery_mhz: float = 24.0  # 保守交付口径
    def period_ns(self, mhz: float) -> float:
        return 1000.0 / mhz

CLOCK = Clock()

# ============================================================
# 3) 3GPP TR 36.777 C2 链路 KPI —— 来源：3GPP TR 36.777 (2017)
# ============================================================
@dataclass(frozen=True)
class C2KPI:
    rate_kbps: tuple = (60.0, 100.0)  # C2 数据率 60-100 kbps
    per_target: float = 1e-3          # 目标误包率 ≤1e-3
    latency_oneway_ms: float = 50.0   # 单程时延 ≤50 ms
    latency_autonomous_ms: float = 10.0  # 自主飞行每消息预算 10 ms (DTU 综述)

C2 = C2KPI()

# ============================================================
# 4) 密码工件尺寸 —— 来源：template_taes.tex（表 tab:params / 正文）
# ============================================================
@dataclass(frozen=True)
class Artifact:
    mlkem_pk_bytes: int = 800       # ML-KEM-512 公钥
    mlkem_ct_bytes: int = 768       # ML-KEM-512 密文
    handshake_bytes: int = 1568     # pk+ct（握手工件）
    mldsa_pk_bytes: int = 1312      # ML-DSA-44 公钥
    mldsa_sig_bytes: int = 2420     # ML-DSA-44 签名

ART = Artifact()

# ============================================================
# 5) MAVLink v2 帧封装 —— 来源：MAVLink v2 规范（mavlink.io）
#    v2 帧 = 10B 头(0xFD,len,incompat,compat,seq,sysid,compid,msgid[3]) + payload + 2B CRC
#    → 每帧固定开销 12B（不含 payload）；payload 由消息负载决定
# ============================================================
@dataclass(frozen=True)
class Mavlink:
    header_bytes: int = 10
    crc_bytes: int = 2
    frame_overhead: int = 12          # header+crc
    # 常见 C2 消息负载（近似，来源 mavlink.io 消息定义）
    msg_cmd_payload: int = 32         # SET_ATTITUDE_TARGET 类
    msg_telem_payload: int = 48       # 遥测类

MAVLINK = Mavlink()

# ============================================================
# 6) 信道模型参数（物理链路预算）—— 来源：Proakis 标准闭式 + ITU-R P.525 自由空间
#    全部为可核验的教科书/建议书常数；频率/功率/增益为典型 UAV C2 假设值
#    （标注"假设"：因无真实射频设备实测，取 2.4 GHz ISM 常用值，与 Viulinx/SiK 类数据链一致）
# ============================================================
@dataclass(frozen=True)
class Channel:
    freq_ghz: float = 2.4                 # 2.4 GHz ISM（UAV C2 主流频段）
    tx_power_dbm: float = 20.0            # +20 dBm (100 mW) —— 典型 UAV 数传
    tx_gain_dbi: float = 0.0              # 全向
    rx_gain_dbi: float = 0.0
    noise_fig_dB: float = 5.0             # 接收机噪声系数
    bandwidth_khz: float = 1000.0         # 1 MHz 信道（支撑 ~60-100 kbps 有效负载）
    path_loss_exp: float = 2.0            # 自由空间 n=2；城市 NLOS 用 3.0-3.5（敏感性分析）
    thermal_noise_dbm = -173.9            # 290K 热噪声谱密度 dBm/Hz
    # 距离（假设场景：视距地空，0.5-5 km 典型）
    distance_km: float = 1.0

CH = Channel()

# ============================================================
# 7) ARQ 参数（链路层可靠传输）
# ============================================================
@dataclass(frozen=True)
class Arq:
    max_retrans: int = 4                  # 最大重传次数（停等 ARQ）
    rtt_propag_ms: float = 0.1            # 传播/处理往返（地空 1km 级）
ARQ = Arq()

# ============================================================
# 8) 场景参数
# ============================================================
@dataclass(frozen=True)
class Scenarios:
    # S1 标称：PER 取 3GPP 目标 1e-3；速率 60/100 kbps
    # S2 劣化：PER 1e-2 / 1e-1
    # S3 切换/重密钥：模拟 N 次重密钥
    # S4 故障注入：隐式拒绝率（设计实测 240/240）
    # S5 等级扩展：k=l=8（Level-3/5）→ 周期近似 2×（来源：论文"架构以约 2× 成本扩展到更高级"）
    per_nominal: float = 1e-3
    per_degraded: tuple = (1e-2, 1e-1)
    rates_kbps: tuple = (60.0, 100.0)
    n_samples: int = 10000
    rekey_count: int = 10
    level3_5_scale: float = 2.0

SCEN = Scenarios()
