# -*- coding: utf-8 -*-
"""Explainer figure: why does a conical coil make the tip hotter?

Uses the real physics from physics.py (same defaults as the app's
heating tab) so the curves are computed, not drawn by hand.
Output: cone-vs-straight-explainer.png (Korean labels, Noto CJK font).
"""
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import physics as ph
from materials import ALLOYS

plt.rcParams["font.family"] = ["Noto Sans CJK JP", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

alloy = ALLOYS["316L 스테인리스"]
R = 0.025            # rod radius (50 mm rod)
H = 0.100            # coil depth 100 mm
L = 0.130            # shank 30 mm + coil 100 mm
z1 = 0.030
Nz = 120
z = np.linspace(0, L, Nz)
dz = z[1] - z[0]
turns = 10
spacing = H / turns
ripple = np.where((z >= z1) & (z <= L),
                  1.0 + 0.3 * np.cos(2 * np.pi * (z - z1) / spacing), 1.0)
P_rod = 0.6 * 50 * 1000.0
k_th = alloy["k_thermal"]
A_rod = math.pi * R ** 2
delta = ph.skin_depth(alloy["rho_e"], 30000.0)
feed = 0.002  # 2.0 mm/s (app default)


def solve(rt, rb):
    w = np.zeros(Nz)
    for i, zz in enumerate(z):
        if z1 <= zz <= L:
            rc = max(ph.coil_radius_at(zz, z1, L, rt, rb), R * 1.05)
            w[i] = (R / rc) ** 2
    w = w * ripple
    s = w.sum()
    qp = P_rod * w / (s * dz) if s > 0 else np.zeros(Nz)
    Tax = ph.rod_descent_temperature(z, qp, feed, alloy["rho_melt"], A_rod,
                                     alloy["cp"], 298.15, alloy["T_liquidus"],
                                     alloy["Lf"], R)
    Tg, _ = ph.radial_temperature_field(Tax, qp, R, delta, k_th)
    return qp, Tg[:, -1] - 273.15


qp_s, Ts_s = solve(0.040, 0.040)   # straight 80/80 mm
qp_c, Ts_c = solve(0.040, 0.030)   # cone 80/60 mm
T_melt_C = alloy["T_liquidus"] - 273.15
print("straight tip %.0f C, cone tip %.0f C, melt %.0f C"
      % (Ts_s[-1], Ts_c[-1], T_melt_C))

fig = plt.figure(figsize=(14, 8))
gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.1], wspace=0.25)

# ---------------- left: schematic sections ----------------
ax = fig.add_subplot(gs[0, 0])
ax.set_aspect("equal")
ax.axis("off")
ax.set_title("단면 모식도 (색 = 단위 길이당 가열량)", fontsize=13)
qmax = max(qp_s.max(), qp_c.max())
cmap = plt.get_cmap("inferno")
rod_w = 50.0  # mm


def draw_case(xc, qp, coil_top_r, coil_bot_r, label):
    # rod coloured by local power density
    nblocks = 60
    idx = np.linspace(0, Nz - 1, nblocks).astype(int)
    for k in range(nblocks - 1):
        i0, i1 = idx[k], idx[k + 1]
        z0, z1b = z[i0] * 1000, z[i1] * 1000
        col = cmap(qp[i0] / qmax)
        ax.add_patch(plt.Rectangle((xc - rod_w / 2, z0), rod_w, z1b - z0,
                                   facecolor=col, edgecolor="none"))
    ax.plot([xc - rod_w / 2, xc - rod_w / 2], [0, L * 1000], "k-", lw=1)
    ax.plot([xc + rod_w / 2, xc + rod_w / 2], [0, L * 1000], "k-", lw=1)
    # coil turns + cone outline
    for i in range(turns):
        zi = z1 + (i + 0.5) * (H / turns)
        rc = ph.coil_radius_at(zi, z1, L, coil_top_r, coil_bot_r) * 1000
        for sgn in (-1, 1):
            ax.add_patch(plt.Rectangle((xc + sgn * rc - 3, zi * 1000 - 3),
                                       6, 6, facecolor="#ffd54a",
                                       edgecolor="k", lw=0.5))
    ax.plot([xc - coil_top_r * 1000, xc - coil_bot_r * 1000],
            [z1 * 1000, L * 1000], "y--", lw=1)
    ax.plot([xc + coil_top_r * 1000, xc + coil_bot_r * 1000],
            [z1 * 1000, L * 1000], "y--", lw=1)
    ax.text(xc, L * 1000 + 12, label, ha="center", fontsize=12,
            fontweight="bold")
    # tip marker
    ax.annotate("팁", xy=(xc, L * 1000), xytext=(xc + 42, L * 1000 - 8),
                fontsize=11, arrowprops=dict(arrowstyle="->"))


draw_case(-70, qp_s, 0.040, 0.040, "직선 코일 (80/80 mm)")
draw_case(70, qp_c, 0.040, 0.030, "원뿔 코일 (80/60 mm)")
ax.set_xlim(-140, 145)
ax.set_ylim(L * 1000 + 25, -15)
ax.text(-70, -10, "결합 일정 → 균등 가열", ha="center", fontsize=11)
ax.text(70, -10, "아래로 갈수록 결합↑ → 팁 집중",
        ha="center", fontsize=11)

# ---------------- right: computed temperature profiles ----------------
ax2 = fig.add_subplot(gs[0, 1])
ax2.plot(Ts_s, z * 1000, label="직선 코일", lw=2)
ax2.plot(Ts_c, z * 1000, label="원뿔 코일", lw=2)
ax2.axvline(T_melt_C, color="c", ls="--", label="액상선")
ax2.invert_yaxis()
ax2.set_xlabel("표면 온도 (°C)")
ax2.set_ylabel("깊이 (mm, 위=공급, 아래=팁)")
ax2.set_title("계산된 표면 온도 프로파일", fontsize=13)
ax2.legend()
ax2.grid(True, alpha=0.3)
ax2.annotate("직선 팁 %.0f°C" % Ts_s[-1],
             xy=(Ts_s[-1], L * 1000), xytext=(650, 100),
             fontsize=11, arrowprops=dict(arrowstyle="->"))
ax2.annotate("원뿔 팁 %.0f°C (더 뜨거움)" % Ts_c[-1],
             xy=(Ts_c[-1], L * 1000), xytext=(1250, 117),
             fontsize=11, arrowprops=dict(arrowstyle="->"))

fig.suptitle("왜 원뿔 코일이 팁을 더 뜨겁게 만들까?",
             fontsize=16, fontweight="bold")
fig.text(0.5, 0.02,
         "결합 세기 ∝ (봉 반경 / 코일 반경)² — 코일이 좁아질수록 같은 출력이 팁 근처에 집중됩니다.",
         ha="center", fontsize=11)
fig.savefig("cone-vs-straight-explainer.png", dpi=150, bbox_inches="tight")
print("saved cone-vs-straight-explainer.png")
