# -*- coding: utf-8 -*-
"""MetalAtom — EIGA 금속분말 아토마이저 시뮬레이터 (오픈소스 간이 모델).

목적: ANSYS를 그대로 재현하는 것이 아니라, 공정 조건을 바꿔가며
입도분포의 RULE(규칙)과 LIMIT(한계)를 찾는 것.
구조: 1 공정 / 2 봉·코일 / 3 노즐 / 4 분말 품질(2단계 예고)

실행: streamlit run app.py
필요 패키지: streamlit, numpy, matplotlib
"""

import math
import os

import numpy as np
import streamlit as st

import physics as ph
import i18n
from materials import ALLOYS, GASES

i18n.install(st)


# ---------------------------------------------------------------- 한글 폰트
def use_korean_font():
    """matplotlib 그래프의 한글이 네모(□)로 깨지지 않도록 한글 폰트를 지정."""
    from matplotlib import font_manager, rcParams

    candidates = ["Malgun Gothic", "맑은 고딕", "Noto Sans KR", "Noto Sans CJK KR",
                  "NanumGothic", "Gulim", "Batang", "Apple SD Gothic Neo"]
    installed = {f.name for f in font_manager.fontManager.ttflist}
    for name in candidates:
        if name in installed:
            rcParams["font.family"] = [name, "DejaVu Sans"]
            rcParams["axes.unicode_minus"] = False
            return name

    # 폰트 캐시에 없을 때: 알려진 경로의 폰트 파일을 직접 등록
    for path in (r"C:\Windows\Fonts\malgun.ttf",
                 "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
                 "/System/Library/Fonts/AppleSDGothicNeo.ttc"):
        if os.path.exists(path):
            font_manager.fontManager.addfont(path)
            name = font_manager.FontProperties(fname=path).get_name()
            rcParams["font.family"] = [name, "DejaVu Sans"]
            rcParams["axes.unicode_minus"] = False
            return name
    return None


st.set_page_config(page_title="MetalAtom — EIGA 아토마이저 시뮬레이터", layout="wide")
st.title("MetalAtom")
st.caption("EIGA 금속분말 아토마이저 시뮬레이터 — 오픈소스 간이 모델. "
           "CFD가 아니라 규칙과 한계를 찾는 도구입니다. "
           "모든 물성은 대표값이며, 본인 장비 데이터로 보정해서 쓰세요.")

# ---------------------------------------------------------------- sidebar
i18n.language_switch(st.sidebar)
st.sidebar.header("공통 설정")
alloy_name = st.sidebar.selectbox("합금", list(ALLOYS.keys()), index=0)
gas_name = st.sidebar.selectbox("분무 가스", list(GASES.keys()), index=0)
alloy = ALLOYS[alloy_name]
gas = GASES[gas_name]
R_gas = 8.314 / gas["M"]

if "melt_rate" not in st.session_state:
    st.session_state["melt_rate"] = 1.4
if "stream_d" not in st.session_state:
    st.session_state["stream_d"] = 3.0
if "D50_um" not in st.session_state:
    st.session_state["D50_um"] = 40.0
if "sig_g" not in st.session_state:
    st.session_state["sig_g"] = 2.0

tab1, tab2, tab3, tab4, tab5, tab_coil, tab_rad, tab6 = st.tabs(
    ["1 공정", "2 봉·코일", "3 노즐", "4 분말 품질", "5 수율 계산",
     "코일 가열 보기", "복사열", "사용법·한계"])


def lubanska_block(P_gas_bar, P_ch_bar, T_gas_K, T_melt_C, D_mm, GMR, K):
    """공통 Lubanska 계산. dict로 반환."""
    T_melt_K = T_melt_C + 273.15
    v_gas, choked = ph.gas_jet_velocity(P_gas_bar * 1e5, P_ch_bar * 1e5,
                                       T_gas_K, gas["gamma"], R_gas)
    rho_g = ph.gas_density(P_ch_bar * 1e5, T_gas_K, gas["M"])
    nu_g = gas["mu"] / rho_g
    nu_m = ph.melt_kinematic_viscosity(alloy, T_melt_K)
    sigma = ph.melt_surface_tension(alloy, T_melt_K)
    D = D_mm / 1000.0
    We = ph.weber_melt(alloy["rho_melt"], v_gas, D, sigma)
    D50 = ph.lubanska_D50(K, D, nu_m, nu_g, We, 1.0, GMR)
    return {"v_gas": v_gas, "choked": choked, "rho_g": rho_g, "nu_g": nu_g,
            "nu_m": nu_m, "sigma": sigma, "We": We, "D50": D50}


def gas_flow_kg_min(P_gas_bar, T_gas_K, gas_area_mm2, Cd=0.9):
    """초크 유량식 기준 가스 질량유량 (kg/min)."""
    return ph.gas_mass_flow_choked(P_gas_bar * 1e5, T_gas_K,
                                   gas_area_mm2 * 1e-6, Cd,
                                   gas["gamma"], R_gas) * 60.0


# ---------------------------------------------------------------- tab 1
with tab1:
    st.header("1. 공정부분 — 조건 조절에 따른 입도분포와 외관형상")
    st.write("주의: 가스 압력은 제트 속도가 아니라 가스 유량→GMR을 통해 입도에 작용합니다. "
             "초크(음속) 상태에서는 속도가 포화되므로, 압력을 올려도 속도는 안 올라가고 "
             "유량만 늘어납니다. 그래서 압력 효과가 보이려면 GMR을 입력값이 아니라 "
             "가스 유량/용탕 유량으로 계산해야 합니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        P_gas = st.number_input("가스 공급압력 (bar)", 1.0, 300.0, 20.0, 1.0)
        P_ch = st.number_input("챔버 압력 (bar)", 0.1, 10.0, 1.5, 0.1)
        T_gas = st.number_input("가스 온도 (K)", 200.0, 1000.0, 300.0, 10.0)
    with c2:
        T_melt = st.number_input("금속 온도 (°C)",
                                 float(alloy["T_liquidus"] - 273.15) - 50,
                                 float(alloy["T_liquidus"] - 273.15) + 300,
                                 float(alloy["T_liquidus"] - 273.15) + 50, 10.0)
        D_stream = st.number_input("용탕류 직경 (mm)", 0.5, 10.0, 3.0, 0.1)
        melt_flow = st.number_input("용탕 유량 (kg/min)", 0.1, 100.0,
                                    float(st.session_state["melt_rate"]), 0.1,
                                    key="melt_flow_t1")
        gas_area = st.number_input("가스 출구 면적 (mm²)", 1.0, 200.0, 20.0, 1.0)
    with c3:
        K = st.number_input("Lubanska 상수 K (장비 보정값)", 1.0, 200.0, 40.0, 1.0)
        sig_g = st.number_input("입도분포 폭 σg (로그정규)", 1.2, 4.0, 2.0, 0.1)
        t_min = st.number_input("목표 입도 하한 (µm)", 0.0, 200.0, 5.0, 1.0)
        t_max = st.number_input("목표 입도 상한 (µm)", 1.0, 500.0, 25.0, 1.0)

    m_gas = gas_flow_kg_min(P_gas, T_gas, gas_area)
    GMR_c = m_gas / melt_flow if melt_flow > 0 else 0.0
    r = lubanska_block(P_gas, P_ch, T_gas, T_melt, D_stream, GMR_c, K)
    d10, d50, d90 = ph.D_values(r["D50"], sig_g)
    st.session_state["D50_um"] = d50 * 1e6
    st.session_state["sig_g"] = sig_g
    yld = ph.yield_in_range(r["D50"], sig_g, t_min * 1e-6, t_max * 1e-6)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("D50", f"{d50 * 1e6:.1f} µm")
    m2.metric("D10 / D90", f"{d10 * 1e6:.1f} / {d90 * 1e6:.1f} µm")
    m3.metric(f"목표 범위({t_min:.0f}~{t_max:.0f}µm) 수율", f"{yld * 100:.1f}%")
    m4.metric("계산 GMR", f"{GMR_c:.2f}")
    st.write(f"가스 유량: {m_gas:.2f} kg/min, "
             f"가스 제트 속도: {r['v_gas']:.0f} m/s "
             f"({'초크(음속) 상태' if r['choked'] else '아음속 상태'}), "
             f"표면장력: {r['sigma']:.3f} N/m, "
             f"용탕 동점도: {r['nu_m']:.2e} m²/s, "
             f"Weber 수: {r['We']:.3g}")
    if P_gas > 150:
        st.warning("가스 공급압력이 150 bar를 넘습니다. 실린더 공급 상한(약 150~200 bar)을 "
                   "넘으면 실현이 어려울 수 있습니다 — 장비의 한계로 기록하세요.")

    # PSD 곡선
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    use_korean_font()
    ds = np.logspace(math.log10(1e-6), math.log10(500e-6), 300)
    cdf = [ph.lognormal_cdf(d, r["D50"], sig_g) for d in ds]
    fig, ax = plt.subplots()
    ax.plot(ds * 1e6, cdf)
    ax.set_xscale("log")
    ax.set_xlabel("입자 직경 (µm)")
    ax.set_ylabel("누적 질량분율")
    ax.set_title("입도분포 (로그정규 모델)")
    ax.grid(True, which="both", alpha=0.3)
    st.pyplot(fig)

    # 스윕
    st.subheader("파라미터 스윕 — 규칙 찾기")
    s_var = st.selectbox("스윕 변수", ["가스 공급압력 (bar)", "용탕 유량 (kg/min)",
                                       "금속 온도 (°C)", "용탕류 직경 (mm)"])

    def d50_for(P, mflow, T, D):
        mg = gas_flow_kg_min(P, T_gas, gas_area)
        gmr = mg / mflow if mflow > 0 else 0.0
        return lubanska_block(P, P_ch, T_gas, T, D, gmr, K)["D50"] * 1e6

    sc1, sc2, sc3 = st.columns(3)
    with sc1:
        s_min = st.number_input("스윕 최소값", value=10.0)
    with sc2:
        s_max = st.number_input("스윕 최대값", value=50.0)
    with sc3:
        s_n = st.number_input("스윕 점 개수", 2, 50, 9, 1)
    xs = np.linspace(s_min, s_max, int(s_n))
    d50s = []
    for x in xs:
        if s_var.startswith("가스 공급압력"):
            d50s.append(d50_for(x, melt_flow, T_melt, D_stream))
        elif s_var.startswith("용탕 유량"):
            d50s.append(d50_for(P_gas, x, T_melt, D_stream))
        elif s_var.startswith("금속 온도"):
            d50s.append(d50_for(P_gas, melt_flow, x, D_stream))
        else:
            d50s.append(d50_for(P_gas, melt_flow, T_melt, x))
    st.line_chart({"x": xs, "D50 (µm)": d50s}, x="x")
    st.dataframe({"스윕 변수": xs, "D50 (µm)": np.round(d50s, 1)})

    # 공정 윈도우
    st.subheader("공정 윈도우 — 가스 압력 × 용탕 유량")
    w_p = np.linspace(5, 60, 12)
    w_m = np.linspace(0.5, 5.0, 12)
    grid = np.zeros((len(w_m), len(w_p)))
    for i, mm in enumerate(w_m):
        for j, pp in enumerate(w_p):
            grid[i, j] = d50_for(pp, mm, T_melt, D_stream)
    fig2, ax2 = plt.subplots()
    im = ax2.imshow(grid, aspect="auto", origin="lower",
                    extent=[w_p.min(), w_p.max(), w_m.min(), w_m.max()])
    ax2.set_xlabel("가스 공급압력 (bar)")
    ax2.set_ylabel("용탕 유량 (kg/min)")
    ax2.set_title("D50 (µm) — 색이 진할수록 굵은 분말")
    plt.colorbar(im, ax=ax2)
    st.pyplot(fig2)

# ---------------------------------------------------------------- tab 2
with tab2:
    st.header("2(a). 봉·코일 — 용탕 생성과 팁 이탈 모드")
    c1, c2, c3 = st.columns(3)
    with c1:
        rod_d = st.number_input("봉 지름 (mm)", 10.0, 100.0, 50.0, 1.0)
        feed = st.number_input("봉 공급 속도 (mm/s)", 0.1, 20.0, 5.0, 0.1)
        rpm = st.number_input("봉 회전 속도 (rpm)", 0.0, 500.0, 60.0, 1.0)
    with c2:
        P_coil = st.number_input("코일 출력 (kW)", 1.0, 500.0, 50.0, 1.0)
        eff = st.number_input("코일 효율", 0.1, 1.0, 0.6, 0.05)
        turns = st.number_input("코일 감은 횟수", 1, 50, 10, 1)
        coil_len = st.number_input("코일 길이 (mm)", 10.0, 500.0, 100.0, 1.0)
        coil_top = st.number_input("코일 상부 내경 (mm)", 10.0, 200.0, 80.0, 1.0)
        coil_bot = st.number_input("코일 하부 내경 (mm)", 10.0, 200.0, 80.0, 1.0)
    with c3:
        tip_shape = st.selectbox("팁 형상", ["평탄", "둥근", "샤프"])
        fall_h = st.number_input("팁→노즐 낙하 높이 (m)", 0.05, 1.0, 0.2, 0.05)
        T_melt2 = st.number_input("용탕 온도 (°C) ",
                                  float(alloy["T_liquidus"] - 273.15) - 50,
                                  float(alloy["T_liquidus"] - 273.15) + 300,
                                  float(alloy["T_liquidus"] - 273.15) + 50, 10.0)
        lo_th = st.number_input("이탈모드 하한 We", 0.5, 20.0, 4.0, 0.5)
        hi_th = st.number_input("이탈모드 상한 We", 1.0, 50.0, 12.0, 0.5)
        taper_q = st.number_input("테이퍼 지수 q (집속 강도)", 0.0, 1.0, 0.5, 0.05)

    T_melt2_K = T_melt2 + 273.15
    m_dot = ph.melt_rate_from_power(P_coil, eff, alloy, T_melt2_K)
    v_fall = math.sqrt(2.0 * 9.81 * fall_h)
    d_stream0 = ph.stream_diameter(m_dot, alloy["rho_melt"], v_fall)
    d_stream, v_eff = ph.apply_coil_taper(d_stream0, v_fall,
                                          coil_top / 1000.0, coil_bot / 1000.0,
                                          taper_q)
    v_tip = ph.tip_velocity(v_eff, rpm, rod_d / 2000.0)
    sigma2 = ph.melt_surface_tension(alloy, T_melt2_K)
    We_tip = ph.weber_melt(alloy["rho_melt"], v_tip, d_stream, sigma2)
    mode, mode_txt = ph.detachment_mode(We_tip, lo_th, hi_th)
    # 테이퍼 없는 직선 코일 기준 (비교용)
    v_tip0 = ph.tip_velocity(v_fall, rpm, rod_d / 2000.0)
    We0 = ph.weber_melt(alloy["rho_melt"], v_tip0, d_stream0, sigma2)
    mode0, _ = ph.detachment_mode(We0, lo_th, hi_th)
    st.session_state["melt_rate"] = m_dot * 60.0
    st.session_state["stream_d"] = d_stream * 1000.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("용탕 생성량", f"{m_dot * 60:.2f} kg/min")
    m2.metric("용탕류 직경(추정)", f"{d_stream * 1000:.2f} mm")
    m3.metric("팁 Weber 수", f"{We_tip:.2f}")
    m4.metric("이탈 모드", mode)
    st.info(mode_txt)
    st.write(f"비교 — 직선 코일(테이퍼 없음): 류 직경 {d_stream0 * 1000:.2f} mm, "
             f"팁 Weber 수 {We0:.2f}, 모드 {mode0} / "
             f"테이퍼 적용: 류 직경 {d_stream * 1000:.2f} mm, "
             f"팁 Weber 수 {We_tip:.2f}, 모드 {mode}")
    st.write("스케치 테스트: 상부 내경 = 하부 내경이면 직선 코일(왼쪽 그림), "
             "하부 내경을 줄이면 깔때기 코일(오른쪽 그림)입니다. "
             "테이퍼 지수 q는 집속 강도 보정값입니다 (0 = 집속 없음, 1 = 완전 기하 집속).")
    st.write(f"코일 감은 횟수 {turns}회, 코일 길이 {coil_len:.0f} mm, 팁 형상 {tip_shape} — "
             f"팁 형상보다 코일이 금속을 어떻게 녹이는지가 지배적이라는 점을 기억하세요. "
             f"팁 형상은 현 버전에서는 정성 변수로만 기록됩니다.")
    st.write("참고: 이탈 모드 판정은 경험식 기반 휴리스틱(v1)입니다. "
             "하한/상한 We 임계값은 본인 장비 경험으로 보정하세요.")

# ---------------------------------------------------------------- tab 3
with tab3:
    st.header("3. 노즐 — 상부→하부챔버 통과 중 분쇄")
    st.write("용탕은 노즐 중심 구멍을 타고 상부챔버에서 하부챔버로 이동하며, "
             "그 통과 구간에서 노즐 고압가스에 맞아 분쇄됩니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        bore_d = st.number_input("노즐 보어 지름 (mm)", 0.5, 10.0, 3.0, 0.1)
        bore_len = st.number_input("노즐 보어 길이 (mm)", 1.0, 50.0, 10.0, 1.0)
        nozzle_type = st.selectbox("가스 분사 형태", ["환형 슬릿", "개별 홀"])
        jet_angle = st.number_input("가스 분사각 (° , 축 기준)", 0.0, 90.0, 30.0, 1.0)
        if nozzle_type == "환형 슬릿":
            pitch_d = st.number_input("슬릿 피치 지름 (mm)", 5.0, 100.0, 30.0, 1.0)
            slit_w = st.number_input("슬릿 폭 (mm)", 0.1, 5.0, 0.5, 0.05)
            gas_area3 = ph.annular_slit_area(pitch_d / 1000.0, slit_w / 1000.0) * 1e6
            coverage = 1.0
        else:
            pitch_d = st.number_input("홀 피치 지름 (mm)", 5.0, 100.0, 30.0, 1.0)
            n_holes = st.number_input("홀 개수", 1, 100, 12, 1)
            hole_d = st.number_input("홀 지름 (mm)", 0.2, 5.0, 1.5, 0.1)
            gas_area3 = ph.holes_area(int(n_holes), hole_d / 1000.0) * 1e6
            coverage = ph.jet_coverage(int(n_holes), hole_d / 1000.0, pitch_d / 1000.0)
    with c2:
        P0 = st.number_input("가스 공급압력 (bar) ", 1.0, 300.0, 20.0, 1.0)
        Pc = st.number_input("챔버 압력 (bar) ", 0.1, 10.0, 1.5, 0.1)
        dP = st.number_input("상하부 압력차 (bar)", 0.0, 5.0, 0.5, 0.05)
        bore_profile = st.selectbox("보어 형상", ["직선 (초크, Mach 1)", "디 라발 (초음속)"])
        if bore_profile == "디 라발 (초음속)":
            exit_d = st.number_input("디 라발 출구 지름 (mm)", 1.0, 100.0, 10.0, 0.5)
    with c3:
        m_dot_in = st.number_input("용탕 유량 (kg/min)",
                                   0.1, 100.0,
                                   float(st.session_state["melt_rate"]), 0.1,
                                   key="melt_flow_nozzle")
        v0 = st.number_input("용탕 초기 속도 (m/s)", 0.0, 10.0, 0.5, 0.1)
        Cd = st.number_input("노즐 유량계수 Cd", 0.5, 1.0, 0.9, 0.05)

    v_gas3, choked3 = ph.gas_jet_velocity(P0 * 1e5, Pc * 1e5, 300.0,
                                         gas["gamma"], R_gas)
    rho_g3 = ph.gas_density(Pc * 1e5, 300.0, gas["M"])
    m_gas = ph.gas_mass_flow_choked(P0 * 1e5, 300.0, gas_area3 * 1e-6,
                                    Cd, gas["gamma"], R_gas)
    if bore_profile == "디 라발 (초음속)":
        A_exit = math.pi * (exit_d / 1000.0) ** 2 / 4.0
        A_throat = gas_area3 * 1e-6
        A_ratio = A_exit / A_throat if A_throat > 0 else 1.0
        M_exit = ph.mach_from_area_ratio(A_ratio, gas["gamma"])
        v_jet, T_exit, P_exit = ph.supersonic_exit(P0 * 1e5, 300.0, M_exit,
                                                  gas["gamma"], R_gas)
    else:
        v_jet, M_exit, P_exit, A_ratio = v_gas3, 1.0, None, 1.0
    v_transit = ph.transit_velocity(v0, dP * 1e5, alloy["rho_melt"])
    t_transit = (bore_len / 1000.0) / v_transit if v_transit > 0 else 0.0
    sigma3 = ph.melt_surface_tension(alloy, alloy["T_liquidus"] + 50)
    v_rel = ph.relative_velocity(v_jet, v_transit, jet_angle)
    v_cross = ph.cross_flow_velocity(v_jet, jet_angle)
    We_cross = ph.weber_gas(rho_g3, v_cross, bore_d / 1000.0, sigma3)
    gmr3 = (m_gas * 60) / m_dot_in if m_dot_in > 0 else 0.0

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("가스 제트 속도", f"{v_jet:.0f} m/s")
    m2.metric("가스 유량", f"{m_gas * 60:.2f} kg/min")
    m3.metric("계산 GMR", f"{gmr3:.2f}")
    m4.metric("노즐 통과 시간", f"{t_transit * 1000:.2f} ms")
    if bore_profile == "디 라발 (초음속)":
        st.write(f"디 라발: 목 면적 {gas_area3:.1f} mm², 출구 면적 {A_exit * 1e6:.1f} mm², "
                 f"면적비 {A_ratio:.2f}, 출구 Mach {M_exit:.2f}, "
                 f"출구 압력 {P_exit / 1e5:.2f} bar (챔버 {Pc:.2f} bar)")
        if P_exit < Pc * 1e5 * 0.95:
            st.write("과팽창 상태입니다 (출구 압력 < 챔버 압력). 노즐 출구 부근에 충격파가 생길 수 있습니다.")
        elif P_exit > Pc * 1e5 * 1.05:
            st.write("부족팽창 상태입니다 (출구 압력 > 챔버 압력). 출구 후 제트가 추가로 팽창합니다.")
        else:
            st.write("적정팽창 상태입니다 (출구 압력 ≈ 챔버 압력).")
    st.write(f"가스 출구 면적(형상 계산): {gas_area3:.1f} mm², "
             f"가스 흐름: {'초음속 제트' if bore_profile == '디 라발 (초음속)' else ('초크(음속) 상태' if choked3 else '아음속 상태')}, "
             f"용탕 통과 속도: {v_transit:.2f} m/s, "
             f"상대 속도: {v_rel:.0f} m/s (가스 속도가 지배해서 각도 영향이 작음), "
             f"횡방향 속도(분사각 {jet_angle:.0f}°): {v_cross:.0f} m/s, "
             f"횡방향 상호작용 Weber 수: {We_cross:.3g}")
    if nozzle_type == "개별 홀":
        st.write(f"제트 원주 커버율(출구면 기준): {coverage * 100:.0f}% — "
                 f"제트는 하류에서 확산되므로 실제 커버율은 이보다 높습니다.")
        if coverage < 0.9:
            st.warning("홀 사이 빈틈이 큽니다. 빈틈 부분의 용탕은 분쇄가 약해져 균일성이 떨어질 수 있습니다.")
    if P0 > 150:
        st.warning("가스 공급압력이 150 bar를 넘습니다. 실린더 공급 상한을 확인하세요.")
    st.write("해석: 분사각이 클수록 횡방향 속도 성분이 커져 분쇄 Weber 수가 커집니다 "
             "(30°→60°에서 약 3배). 축방향 성분은 용탕 가속에 쓰입니다. "
             "0°에서는 횡방향 분쇄가 없어 전단 분쇄만 남습니다 (v1에서는 횡방향 성분만 계상). "
             "통과 시간이 짧을수록 분쇄가 노즐 구간에 집중되고, "
             "상하부 압력차가 클수록 용탕 통과 속도가 빨라져 가스와 만나는 시간이 짧아집니다.")

# ---------------------------------------------------------------- tab 4
with tab4:
    st.header("4. 분말 품질 — 상변화·산화·점도·유동성 (2단계)")
    st.subheader("냉각·응고 거리")
    c1, c2 = st.columns(2)
    with c1:
        d_drop = st.number_input("액적 직경 (µm)", 1.0, 500.0, 40.0, 1.0)
        v_drop = st.number_input("액적 비행 속도 (m/s)", 0.1, 50.0, 5.0, 0.1)
        ch_h = st.number_input("챔버 높이 (m)", 0.5, 5.0, 1.5, 0.1)
    with c2:
        T_drop = st.number_input("액적 초기 온도 (°C)", 1000.0, 2500.0, 1500.0, 10.0)
        T_gas4 = st.number_input("챔버 가스 온도 (°C)", 0.0, 500.0, 25.0, 5.0)
    rho_g4 = ph.gas_density(1.5e5, T_gas4 + 273.15, gas["M"])
    t_cool = ph.droplet_cooling_time(d_drop * 1e-6, alloy["rho_melt"], alloy["cp"],
                                     alloy["Lf"], T_drop + 273.15,
                                     T_gas4 + 273.15, alloy["T_liquidus"],
                                     alloy["T_solidus"], rho_g4, v_drop, gas["mu"])
    dist = v_drop * t_cool
    st.metric("응고까지 냉각 시간", f"{t_cool * 1000:.1f} ms")
    st.metric("응고 완료까지 비행 거리", f"{dist:.3f} m")
    if dist > ch_h:
        st.warning("응고 완료 거리가 챔버 높이보다 깁니다. 벽/바닥에 닿기 전에 굳지 못해 "
                   "불규칙 입자·스플랫 위험이 있습니다.")
    else:
        st.success("챔버 높이 안에서 응고가 완료되는 것으로 예측됩니다.")
    st.write("참고: 속도를 초기 속도로 유지한 상한 추정치입니다. 실제 액적은 항력으로 감속하므로 "
             "실제 비행 거리는 이보다 짧습니다.")

    st.subheader("상변화 (응고 구간)")
    interval = alloy["T_liquidus"] - alloy["T_solidus"]
    cool_rate = ((T_drop + 273.15) - (T_gas4 + 273.15)) / t_cool if t_cool > 0 else 0.0
    st.write(f"응고 구간: {interval:.0f} K "
             f"(액상선 {alloy['T_liquidus'] - 273.15:.0f}°C ~ 고상선 {alloy['T_solidus'] - 273.15:.0f}°C), "
             f"평균 냉각 속도: {cool_rate:.2g} K/s")
    if interval > 100:
        st.warning("응고 구간이 넓습니다. 머시(mushy) 상태가 길어져 불규칙 형상 위험이 커집니다.")
    else:
        st.write("응고 구간이 좁아 급속 응고에 유리합니다.")

    st.subheader("산화 (표면 산화층 모델)")
    c3, c4 = st.columns(2)
    with c3:
        D50_in = st.number_input("분말 D50 (µm)", 1.0, 500.0,
                                 float(st.session_state["D50_um"]), 1.0)
    with c4:
        t_ox = st.number_input("산화층 두께 가정 (nm)", 0.0, 100.0, 5.0, 0.5)
    wt_o, ppm_o = ph.oxide_oxygen_content(D50_in * 1e-6, alloy["rho_melt"],
                                          t_ox * 1e-9)
    st.metric("산소 함량 추정", f"{wt_o:.4f} wt% ({ppm_o:.0f} ppm)")
    st.write("오더 추정 모델입니다. 산소량은 1/D에 비례하므로 분말이 가늘수록 산화에 민감합니다. "
             "실제 산화량은 노출 시간, 온도 이력, 챔버 산소 농도에도 좌우됩니다.")

    st.subheader("구형화 (점도 vs 표면장력)")
    mu_drop = ph.melt_viscosity(alloy, T_drop + 273.15)
    sig_drop = ph.melt_surface_tension(alloy, T_drop + 273.15)
    t_sph = ph.spheroidization_time(mu_drop, d_drop * 1e-6, sig_drop)
    st.write(f"구형화 시간 척도: {t_sph * 1e6:.2f} µs (용탕 점도 {mu_drop:.4f} Pa·s, "
             f"표면장력 {sig_drop:.3f} N/m) vs 냉각 시간 {t_cool * 1000:.1f} ms")
    shape_ok = t_sph < t_cool * 0.1
    if shape_ok:
        st.success("구형화가 냉각보다 훨씬 빨라 구형 입자가 예상됩니다.")
    else:
        st.warning("구형화가 냉각보다 느려 불규칙 형상이 남을 수 있습니다. "
                   "산화막이 있으면 구형화가 더 방해받습니다.")

    st.subheader("유동성 (휴리스틱 등급)")
    c5, c6 = st.columns(2)
    with c5:
        sig_g_in = st.number_input("입도분포 폭 σg", 1.2, 4.0,
                                   float(st.session_state["sig_g"]), 0.1)
    with c6:
        fine_th = st.number_input("미분 기준 (µm)", 1.0, 50.0, 10.0, 1.0)
    fines = ph.lognormal_cdf(fine_th * 1e-6, D50_in * 1e-6, sig_g_in)
    st.write(f"미분(<{fine_th:.0f}µm) 분율: {fines * 100:.1f}%")
    good = sum([D50_in >= 20, fines < 0.2, shape_ok])
    rating = "양호" if good == 3 else ("보통" if good == 2 else "불량 가능")
    st.metric("유동성 등급 (휴리스틱)", rating)
    st.write("판정 근거: D50 20µm 이상, 미분 20% 미만, 구형화 완료 — 3개 중 충족 개수. "
             "실측(Hall flow 등)으로 검증이 필요한 추정치입니다.")

# ---------------------------------------------------------------- tab 5 (수율)
with tab5:
    st.header("5. 수율 계산 — 합격 입도 범위로 공정 수율 구하기")
    st.write("분말을 어느 입도 범위로 쓸지 정하면, 그 범위에 들어가는 질량분율이 곧 공정 수율입니다. "
             "예를 들어 10~45 µm만 합격으로 보면, 전체 용탕 중 몇 %가 합격 분말이 되는지 바로 나옵니다. "
             "아래 숫자는 모두 직접 수정할 수 있습니다.")

    yc1, yc2 = st.columns(2)
    with yc1:
        y_dmin = st.number_input("합격 하한 (µm)", 0.0, 500.0, 10.0, 1.0)
        y_dmax = st.number_input("합격 상한 (µm)", 0.0, 500.0, 45.0, 1.0)
        y_melt = st.number_input("용탕 유량 (kg/min, 수율 환산 기준)", 0.1, 100.0,
                                 round(float(st.session_state["melt_rate"]), 2), 0.05)
    with yc2:
        y_d50 = st.number_input("분포 D50 (µm)", 1.0, 500.0,
                                round(float(st.session_state["D50_um"]), 1), 0.1)
        y_sig = st.number_input("분포 폭 σg", 1.2, 4.0,
                                float(st.session_state["sig_g"]), 0.1)
        st.caption("기본값은 `1 공정` 탭의 계산 결과(D50·σg)입니다. "
                   "실측 입도분석 값이 있으면 덮어쓰세요.")

    if y_dmax <= y_dmin:
        st.error("합격 상한이 하한보다 커야 합니다. 숫자를 다시 확인하세요.")
    else:
        d_lo, d_hi, d50y = y_dmin * 1e-6, y_dmax * 1e-6, y_d50 * 1e-6
        frac_lo = ph.lognormal_cdf(d_lo, d50y, y_sig)          # 하한 미달
        frac_hi = 1.0 - ph.lognormal_cdf(d_hi, d50y, y_sig)    # 상한 초과
        yld_in = max(0.0, 1.0 - frac_lo - frac_hi)              # 합격 수율
        y_kg_min = y_melt * yld_in
        d10y, _, d90y = ph.D_values(d50y, y_sig)
        d_mean = ph.mean_diameter_in_range(d50y, y_sig, d_lo, d_hi)

        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric(f"합격 수율 ({y_dmin:.0f}~{y_dmax:.0f} µm)", f"{yld_in * 100:.1f} %")
        m2.metric("합격품 평균 입도", f"{d_mean * 1e6:.1f} µm",
                  help="합격 구간만 남겼을 때의 질량 가중 산술평균 입도입니다. "
                       "범위를 좁히거나 하한을 올리면 이 값도 함께 올라갑니다.")
        m3.metric("미달 (너무 작음)", f"{frac_lo * 100:.1f} %")
        m4.metric("과대 (너무 큼)", f"{frac_hi * 100:.1f} %")
        m5.metric("합격 분말 생산량", f"{y_kg_min:.2f} kg/min")
        st.caption(f"시간당 기준: 용탕 {y_melt * 60:.1f} kg/h 중 합격 분말 {y_kg_min * 60:.1f} kg/h. "
                   f"참고 D10/D50/D90 = {d10y * 1e6:.1f} / {y_d50:.1f} / {d90y * 1e6:.1f} µm")

        # 누적분포 + 합격 구간 표시
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        use_korean_font()
        x_lo = max(0.5, y_dmin * 0.2) if y_dmin > 0 else 0.5
        ds = np.logspace(math.log10(x_lo), math.log10(500.0), 300)
        cdf = np.array([ph.lognormal_cdf(d * 1e-6, d50y, y_sig) for d in ds])
        fig, ax = plt.subplots()
        ax.plot(ds, cdf, color="#1f77b4", lw=1.8, label=i18n.tr("누적 질량분율 (이 크기 이하)"))
        ax.axvspan(max(y_dmin, 0.5), y_dmax, color="#4c9be8", alpha=0.15,
                   label=f"합격 구간 {y_dmin:.0f}~{y_dmax:.0f} µm")
        ax.hlines(frac_lo, max(y_dmin, 0.5), y_dmax, color="#d62728", ls=":", lw=1.2)
        ax.hlines(1.0 - frac_hi, max(y_dmin, 0.5), y_dmax, color="#d62728", ls=":", lw=1.2)
        ax.annotate("", xy=(y_dmax, 1.0 - frac_hi), xytext=(y_dmax, frac_lo),
                    arrowprops=dict(arrowstyle="<->", color="#d62728", lw=1.4))
        ax.text(y_dmax * 1.12, (frac_lo + 1.0 - frac_hi) / 2.0,
                f"수율 {yld_in * 100:.1f}%", color="#d62728", va="center", fontsize=10)
        ax.set_xscale("log")
        ax.set_xlabel("입자 직경 (µm)")
        ax.set_ylabel("누적 질량분율")
        ax.set_title("합격 구간이 전체 수율에서 차지하는 비율")
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(loc="lower right", fontsize=9)
        st.pyplot(fig)

        st.subheader("구간별 분해")
        st.dataframe({
            "구간": [f"미달 (< {y_dmin:.0f} µm)",
                     f"합격 ({y_dmin:.0f}~{y_dmax:.0f} µm)",
                     f"과대 (> {y_dmax:.0f} µm)",
                     "합계"],
            "질량분율 (%)": [round(frac_lo * 100, 2), round(yld_in * 100, 2),
                            round(frac_hi * 100, 2),
                            round((frac_lo + yld_in + frac_hi) * 100, 2)],
            "생산량 (kg/h)": [round(y_melt * 60 * frac_lo, 2),
                             round(y_melt * 60 * yld_in, 2),
                             round(y_melt * 60 * frac_hi, 2),
                             round(y_melt * 60, 2)],
        }, hide_index=True)
        st.write("수율 = Φ[ln(상한/D50)/lnσg] − Φ[ln(하한/D50)/lnσg] (로그정규·질량 기준). "
                 "합격 범위를 좁힐수록 수율은 떨어지고, D50을 합격 구간 가운데로 옮기면 수율이 올라갑니다. "
                 "실제 공정 수율은 분급기 효율, 벽 부착, 산화·오염 손실 때문에 이 값보다 낮습니다.")

# ---------------------------------------------------------------- 코일 가열 보기
with tab_coil:
    st.header("코일 가열 보기 — 봉 팁 콘 + 코일 형상 단면")
    st.write("봉은 위에서 아래로 공급되고, 아래 끝에 콘(테이퍼) 팁이 있습니다. "
             "고주파 전류는 표피 효과로 봉 표면층에만 열을 넣고, 열은 전도로 안쪽으로 퍼집니다. "
             "코일이 봉 단면을 따라 같이 좁아지면 같은 출력이 팁 근처의 작은 단면에 집중되어 "
             "팁이 더 뜨거워집니다. 봉 팁 콘의 크기와 코일의 내경·깊이·간극·축방향 위치를 "
             "아래에서 모두 조절할 수 있습니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        rod_d_h = st.number_input("봉 지름 (mm)", 10.0, 200.0, 60.0, 1.0, key="h_rod_d",
                                  help="봉 지름. 코일–봉 간극과 함께 코일이 봉에서 열마나 떨어지는지를 결정합니다.")
        cone_h = st.number_input("봉 팁 콘 높이 (mm)", 0.0, 300.0, 40.0, 5.0, key="h_cone_h",
                                 help="0이면 콘 없이 직선 팁입니다.")
        tip_d = st.number_input("봉 팁 지름 (mm)", 0.0, 100.0, 1.0, 1.0, key="h_tip_d",
                                help="콘 끝의 지름. 0이면 뾰족한 팁(절단 없음), 0보다 크면 그 지름으로 잘린 절두 원뿔입니다.")
        coil_shape = st.selectbox(
            "코일 형상",
            ["봉 형상 따라가기 (콘 밀착)", "직선", "원뿔 (선형 테이퍼)", "곡선 테이퍼 (지수)"],
            key="h_shape")
        st.caption("‘봉 형상 따라가기’는 코일 내경 = 봉 반경 + 간극으로, 콘 구간에서 코일도 함께 좁아집니다.")
    with c2:
        coil_start = st.number_input("코일 시작 위치 (팁 기준, mm)", -300.0, 300.0, 90.0, 5.0,
                                     key="h_cstart",
                                     help="봉 팁 끝단을 0으로 둔 위치입니다. +는 팁 위, −는 팁 아래"
                                          "(금속보다 더 아래)까지 가능합니다.")
        coil_end = st.number_input("코일 끝 위치 (팁 기준, mm)", -300.0, 300.0, -10.0, 5.0, key="h_cend",
                                   help="코일 마지막 턴의 위치. −로 두면 코일이 금속 팁보다 아래로 내려갑니다 "
                                        "(기본 −10 mm = 팁 아래로 한 턴 더).")
        crop_top = st.number_input("위쪽 잘라내기 (코일 상단에서, mm)", 0.0, 200.0, 20.0, 5.0,
                                   key="h_crop",
                                   help="그림에서 코일 상단부터 이만큼 아래를 위쪽 경계로 씁니다.")
        coil_gap = st.number_input("코일–봉 간극 (mm)", 1.0, 50.0, 20.0, 1.0, key="h_gap",
                                   help="코일 내면과 봉 표면 사이 거리. '봉 형상 따라가기'에서는 코일 내경을 "
                                        "봉 지름 + 간극 2배로 잡고, 다른 형상에서도 최소 간극으로 적용됩니다.")
        turns_h = st.number_input("코일 감은 횟수 (턴)", 1, 50, 10, 1, key="h_turns")
        sect_h = st.selectbox("코일 단면 형상", ["원형", "직사각형"], key="h_sect",
                              help="실제 유도 코일은 보통 원형 단면(동관·동선)입니다. "
                                   "단면 형상과 무관하게 코일 위치·출력 계산은 동일합니다.")
        wire_d = st.number_input("코일선 지름 (mm)", 1.0, 30.0, 6.0, 0.5, key="h_wire",
                                 help="원형 단면의 지름입니다.")
        if sect_h == "직사각형":
            wire_w = st.number_input("코일선 폭 (mm, 반경방향)", 1.0, 30.0, 8.0, 0.5,
                                     key="h_ww")
            wire_h = st.number_input("코일선 두께 (mm, 축방향)", 1.0, 30.0, 6.0, 0.5,
                                     key="h_wh")
        else:
            wire_w = wire_h = wire_d
    with c3:
        if coil_shape == "봉 형상 따라가기 (콘 밀착)":
            coil_top_h = rod_d_h + 2.0 * coil_gap
            coil_bot_h = coil_top_h
            shape_p = 1.0
            st.caption(f"코일 내경은 봉 지름 + 간극 2배 = {coil_top_h:.0f} mm 로 자동 결정됩니다.")
        else:
            coil_top_h = st.number_input("코일 상부 내경 (mm)", 20.0, 200.0, 80.0, 1.0, key="h_top")
            if coil_shape == "원뿔 (선형 테이퍼)":
                coil_bot_h = st.number_input("코일 하부 내경 (mm)", 20.0, 200.0, 60.0, 1.0,
                                             key="h_bot")
                shape_p = 1.0
            elif coil_shape == "곡선 테이퍼 (지수)":
                coil_bot_h = st.number_input("코일 하부 내경 (mm)", 20.0, 200.0, 60.0, 1.0,
                                             key="h_bot")
                shape_p = st.number_input("테이퍼 지수 p", 0.2, 3.0, 2.0, 0.1, key="h_shape_p",
                                          help="p > 1: 아래쪽에서 급격히 좁아짐(팁 집중형), "
                                               "p < 1: 위쪽에서 급격히 좁아짐, p = 1: 원뿔")
            else:
                coil_bot_h = coil_top_h
                shape_p = 1.0
        freq = st.number_input("주파수 (kHz)", 1.0, 500.0, 30.0, 1.0, key="h_freq")
        P_coil_h = st.number_input("코일 출력 (kW)", 1.0, 500.0, 80.0, 1.0, key="h_power",
                                   help="봉 Ø60 mm·코일 간극 20 mm 기본 조건에서 팁이 액상선을 넘으려면 약 80 kW가 필요합니다.")
        eff_h = st.number_input("코일 효율", 0.1, 1.0, 0.6, 0.05, key="h_eff")
        T_feed_h = st.number_input("봉 공급 온도 (°C)", 0.0, 500.0, 25.0, 5.0, key="h_tfeed")
        feed_h = st.number_input("봉 공급 속도 (mm/s)", 0.1, 20.0, 2.0, 0.1, key="h_feed")
        shank = st.number_input("코일 위 봉 길이 (mm)", 10.0, 200.0, 30.0, 5.0, key="h_shank")

    R = rod_d_h / 2000.0
    r_tip = min(max(tip_d, 0.0) / 2000.0, R)
    shank_m = shank / 1000.0
    gap_r = coil_gap / 1000.0
    # 코일 위치 기준은 봉 팁(아래): +는 팁 위, −는 팁 아래
    c_start_m = coil_start / 1000.0
    c_end_m = coil_end / 1000.0
    H = max(abs(coil_start - coil_end), 1.0) / 1000.0     # 코일 축방향 길이
    L = shank_m + max(c_start_m, c_end_m, 0.0)            # 봉 길이 = 팁 깊이
    z_start = L - c_start_m
    z_end = L - c_end_m
    z1, z2 = min(z_start, z_end), max(z_start, z_end)     # 코일 상단/하단 깊이
    cone_m = min(cone_h / 1000.0, L * 0.9)
    z_cone0 = L - cone_m         # 콘 시작 깊이
    Nz = 260
    z = np.linspace(0.0, L, Nz)
    dz = z[1] - z[0]

    def rod_radius(zz):
        """봉 반경 (m) at depth zz: 원통 → 콘 → 팁."""
        if cone_m <= 0.0 or zz <= z_cone0:
            return R
        f = min(max((zz - z_cone0) / cone_m, 0.0), 1.0)
        return R + (r_tip - R) * f

    Rz = np.array([rod_radius(zz) for zz in z])

    def coil_radius(zz):
        """코일 내면 반경 (m) at depth zz."""
        if coil_shape == "봉 형상 따라가기 (콘 밀착)":
            return rod_radius(zz) + gap_r
        return ph.coil_radius_at(zz, z1, z2, coil_top_h / 2000.0,
                                 coil_bot_h / 2000.0, shape_p)

    def clear_radius(zz):
        """그림·계산용 실제 코일 반경 (봉과 겹치면 간극만큼 밀어냄)."""
        return max(coil_radius(zz), rod_radius(zz) + max(0.02 * rod_radius(zz), gap_r * 0.5))

    _zc = np.linspace(z1, z2, 40)
    _over = [(zz, coil_radius(zz), rod_radius(zz)) for zz in _zc
             if coil_radius(zz) <= rod_radius(zz)]
    if _over:
        _z0, _rc, _rr = min(_over, key=lambda t: t[1] - t[2])
        st.warning(f"코일이 봉을 파고듭니다 (깊이 {_z0 * 1000:.0f} mm에서 코일 반경 "
                   f"{_rc * 1000:.1f} mm ≤ 봉 반경 {_rr * 1000:.1f} mm). "
                   "그림은 겹치지 않게 보정해 그립니다. 코일 내경을 키우거나 간극을 조정하세요.")

    spacing = H / turns_h if turns_h > 0 else H
    ripple = 1.0 + 0.3 * np.cos(2 * np.pi * (z - z1) / spacing)
    ripple = np.where((z >= z1) & (z <= z2), ripple, 1.0)
    P_rod = eff_h * P_coil_h * 1000.0
    k_th = alloy["k_thermal"]
    delta = ph.skin_depth(alloy["rho_e"], freq * 1000.0)

    def solve_heat(rc_func):
        """코일 반경 함수 → 봉 단면 온도장 (Nz x Nr)."""
        w2 = np.zeros(Nz)
        for i, zz in enumerate(z):
            if z1 <= zz <= z2:
                rc = max(rc_func(zz), Rz[i] * 1.02)
                w2[i] = (Rz[i] / rc) ** 2     # 가까운 코일일수록 결합이 세짐
        w2 = w2 * ripple
        s = w2.sum()
        qp = P_rod * w2 / (s * dz) if s > 0 else np.zeros(Nz)
        Tax = ph.rod_descent_temperature_var(z, qp, feed_h / 1000.0,
                                             alloy["rho_melt"], alloy["cp"],
                                             T_feed_h + 273.15, alloy["T_liquidus"],
                                             alloy["Lf"], Rz)
        Tg, _ = ph.radial_temperature_field_var(Tax, qp, Rz, delta, k_th, Nr=33)
        return Tg

    Tg = solve_heat(coil_radius)
    r_sc = coil_radius(z1)           # 같은 상부 내경의 직선 코일 기준값
    Tg_s = solve_heat(lambda zz: r_sc)
    T_surf = Tg[:, -1] - 273.15
    T_cent = Tg[:, 0] - 273.15
    T_liq_C = alloy["T_liquidus"] - 273.15

    def melt_len_from_tip(Tsurf_C):
        ml = 0.0
        for i in range(Nz - 1, -1, -1):
            if Tsurf_C[i] >= T_liq_C:
                ml = (L - z[i]) * 1000.0
            else:
                break
        return ml

    melt_len = melt_len_from_tip(T_surf)
    tip_C = T_surf[-1]
    tip_molten = tip_C >= T_liq_C
    if tip_C > T_feed_h:
        P_min = P_coil_h * (T_liq_C - T_feed_h) / (tip_C - T_feed_h)
    else:
        P_min = float("inf")
    melt_len_s = melt_len_from_tip(Tg_s[:, -1] - 273.15)
    tip_s_C = Tg_s[-1, -1] - 273.15
    alpha = k_th / (alloy["rho_melt"] * alloy["cp"])
    t_res = H / (feed_h / 1000.0)
    t_diff = R ** 2 / alpha

    # ---- 팁 이탈 모드 (물방울 vs 실) — tab2와 같은 Weber 수 휴리스틱
    T_melt_K = max(tip_C, T_liq_C) + 273.15
    m_pow = ph.melt_rate_from_power(P_coil_h, eff_h, alloy, T_melt_K)      # kg/s
    m_feed = alloy["rho_melt"] * math.pi * R ** 2 * (feed_h / 1000.0)       # kg/s
    m_dot_melt = min(m_pow, m_feed) if m_feed > 0 else m_pow
    d_exit_m = max(2.0 * r_tip, 1e-3)                                      # 팁 구멍 지름
    v_exit = (m_dot_melt / (alloy["rho_melt"] * math.pi * (d_exit_m / 2.0) ** 2)
              if m_dot_melt > 0 else 0.0)
    sigma_melt = ph.melt_surface_tension(alloy, T_melt_K)
    We_tip_m = ph.weber_melt(alloy["rho_melt"], v_exit, d_exit_m, sigma_melt)
    mode_m, mode_txt_m = ph.detachment_mode(We_tip_m)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("표피 깊이", f"{delta * 1000:.2f} mm")
    m2.metric("팁 표면 온도", f"{tip_C:.0f} °C")
    m3.metric("용융 캡 길이", f"{melt_len:.0f} mm")
    m4.metric("용탕 생성 임계 출력 (근사)", f"{P_min:.1f} kW" if P_min != float("inf") else "—")
    tip_label = "뾰족(Ø0)" if r_tip <= 1e-9 else f"Ø{r_tip * 2000:.1f} mm"
    st.caption(f"형상: 봉 Ø{rod_d_h:.0f} mm → 콘 {cone_h:.0f} mm 구간에서 팁 {tip_label}, "
               f"코일 {coil_shape}·{sect_h} 단면 {wire_w:.1f}×{wire_h:.1f} mm·"
               f"길이 {H * 1000:.0f} mm·{turns_h}턴, "
               f"코일은 팁 기준 {coil_start:+.0f} mm ~ {coil_end:+.0f} mm (+위/−아래). "
               f"봉 길이 {L * 1000:.0f} mm, 코일 상단은 봉 위에서 {shank:.0f} mm 내려온 지점입니다.")
    if tip_molten:
        st.success(f"팁 표면이 액상선 이상입니다. 용탕 생성 가능 — 이탈 모드: {mode_m} "
                   f"(팁 Weber 수 {We_tip_m:.1f}, 류 직경 {d_exit_m * 1000:.2f} mm, "
                   f"속도 {v_exit:.2f} m/s, 용탕량 {m_dot_melt * 60:.2f} kg/min)")
        st.info(mode_txt_m)
        with st.expander("왜 물방울 모드 / 실 모드로 갈리나? (점도·표면장력 이야기)"):
            st.markdown(i18n.doc("droplet",
                "판정은 팁 **Weber 수** `We = ρ·v²·d/σ` 하나로 합니다 "
                "(ρ 용탕 밀도, v 팁 출구 속도, d 팁 구멍 지름, σ 표면장력).\n\n"
                "- **녹았는지와는 별개입니다.** 팁이 액상선을 넘어 완전히 녹아도, 출구 속도가 느리고 "
                "구멍이 크면 관성이 표면장력을 이기지 못해 액적이 매달렸다가 끊어지며 물방울로 떨어집니다 "
                "(We < 4).\n"
                "- 구멍이 작거나 유량(속도)이 크면 가는 **실**이 됩니다 (We > 12). 4~12는 전이 영역.\n"
                "- 그래서 ‘녹은 덩이가 통째로 떨어진다’의 주원인은 고주파 조건이 아니라 "
                "출구 유속과 구멍 지름입니다. 출력이 낮아 국부만 녹는 경우에도 덩어리가 떨어지지만, "
                "이 모델은 팁이 균일하게 용융됐다고 가정하므로 그 현상은 다루지 않습니다.\n"
                "- 실 모드로 가려면: 팁 지름↓, 출력/공급속도↑(유량↑), 간극↓, 과열↑(σ↓).\n"
                "- 점도는 `Oh = μ/√(ρ·σ·d)` 로 영향을 줍니다. 점성이 크면 경계 We가 올라가 "
                "물방울 쪽이 넓어집니다. 다만 팁 구멍이 mm급이면 Oh ≈ 0.002로 영향이 1 % 미만이고, "
                "마이크로 오리피스·고점도 용탕에서 중요해집니다 (현재 판정식은 We만 사용 — 한계)."))

    else:
        st.warning("팁 표면이 액상선에 못 미칩니다. 출력을 올리거나 코일을 팁에 가깝게 해야 용탕이 생깁니다.")
    st.write(f"직선 코일(상=하 내경) 비교: 팁 표면 온도 {tip_s_C:.0f} °C, 용융 캡 {melt_len_s:.0f} mm — "
             f"원뿔 코일은 열을 팁 쪽에 집중시켜 같은 출력에서 팁이 더 뜨겁습니다.")
    st.write(f"체류 시간 {t_res:.1f} s vs 열확산 시간 {t_diff:.1f} s — "
             f"체류 시간이 확산 시간보다 짧으면 중심까지 열이 다 퍼지기 전에 팁이 나가므로 "
             f"표면 위주 가열이 됩니다 (정상상태 근사라 실제보다 균일하게 보일 수 있음).")
    st.write("턴별 리플(0.3)은 예시 크기입니다. 턴 간격이 좁을수록 리플이 촘촘해져 가열이 균일해집니다.")

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    use_korean_font()
    # ---- 단면 온도장: 가열되지 않는 코일 위 구간은 빼고, 마우스 오버로 온도 확인
    import plotly.graph_objects as go
    Nr = Tg.shape[1]
    xi = np.linspace(0.0, 1.0, Nr)
    Rp = np.maximum(Rz, 1e-4) * 1000.0            # 반경 (mm)
    crop_m = crop_top / 1000.0
    zcrop = z1 + crop_m                          # 위쪽 비가열부는 잘라내고 코일 구간부터
    keep = z >= zcrop - 1e-9
    if keep.sum() < 2:
        keep = z >= 0.0
    zk = z[keep] * 1000.0
    Rk = Rp[keep]
    Tk = Tg[keep] - 273.15
    r_common = np.linspace(0.0, float(Rp.max()), Nr)
    Zc = np.full((len(zk), Nr), np.nan)
    for i in range(len(zk)):
        prof = np.interp(r_common, xi * Rk[i], Tk[i], left=Tk[i][0])
        prof[r_common > Rk[i] + 1e-9] = np.nan    # 봉 밖은 투명하게
        Zc[i] = prof
    x_mm = np.concatenate([-r_common[::-1], r_common[1:]])
    Zplot = np.concatenate([Zc[:, ::-1], Zc[:, 1:]], axis=1)

    bottom_mm = max(L, z2) * 1000.0 + 8.0
    top_mm = min(zcrop * 1000.0, bottom_mm - 25.0)
    pitch_mm = (H / turns_h) * 1000.0 if turns_h > 0 else H * 1000.0
    if wire_h > pitch_mm + 1e-9:
        st.warning(f"코일선 두께({wire_h:.1f} mm)가 턴 간격({pitch_mm:.1f} mm)보다 커서 "
                   "그림에서 턴이 겹칩니다. 선재 치수를 줄이거나 턴 수를 늘리세요.")
    shapes = []
    for i in range(int(turns_h)):
        zi = z1 + (i + 0.5) * (H / turns_h)
        rc = clear_radius(zi) * 1000.0
        yc = zi * 1000.0
        for sgn in (-1, 1):
            if sect_h == "원형":
                shapes.append(dict(type="circle", layer="above",
                                   x0=sgn * rc - wire_w / 2.0, x1=sgn * rc + wire_w / 2.0,
                                   y0=yc - wire_w / 2.0, y1=yc + wire_w / 2.0,
                                   line=dict(color="black", width=0.6), fillcolor="#ffd54a"))
            else:
                shapes.append(dict(type="rect", layer="above",
                                   x0=sgn * rc - wire_w / 2.0, x1=sgn * rc + wire_w / 2.0,
                                   y0=yc - wire_h / 2.0, y1=yc + wire_h / 2.0,
                                   line=dict(color="black", width=0.6), fillcolor="#ffd54a"))

    # 팁에서 떨어지는 용탕 — 실(연속류) 또는 물방울
    y_tip_mm = L * 1000.0
    if tip_molten:
        d_met_mm = max(d_exit_m * 1000.0, 1.2)
        y_low = max(bottom_mm - 3.0, y_tip_mm + 6.0)
        if mode_m.startswith("droplet"):
            for k in range(3):
                yc = y_tip_mm + 3.5 + k * 6.5
                if yc > y_low:
                    break
                rd = max(d_met_mm * 0.9, 1.7)
                shapes.append(dict(type="circle", layer="above",
                                   x0=-rd, x1=rd, y0=yc - rd, y1=yc + rd,
                                   line=dict(color="#6d0b0b", width=0.5),
                                   fillcolor="#cf1d1d"))
        else:
            hw = max(d_met_mm / 2.0, 0.7)
            shapes.append(dict(type="rect", layer="above", x0=-hw, x1=hw,
                               y0=y_tip_mm, y1=y_low,
                               line=dict(color="#6d0b0b", width=0.5),
                               fillcolor="#cf1d1d"))
            if mode_m.startswith("transition"):
                rd = max(d_met_mm * 0.9, 1.7)
                shapes.append(dict(type="circle", layer="above",
                                   x0=-rd, x1=rd,
                                   y0=y_low + 1.5 - rd, y1=y_low + 1.5 + rd,
                                   line=dict(color="#6d0b0b", width=0.5),
                                   fillcolor="#cf1d1d"))
        anno_metal = ("물방울 모드" if mode_m.startswith("droplet")
                      else ("전이 영역" if mode_m.startswith("transition") else "실(연속류) 모드"))
        shapes.append(dict(type="line", layer="above", xref="paper", yref="y",
                           x0=0.0, x1=1.0, y0=y_tip_mm, y1=y_tip_mm,
                           line=dict(color="#cf1d1d", width=0.8, dash="dot")))
    zc = np.linspace(z1, z2, 60)
    rc_curve = np.array([clear_radius(zz) for zz in zc]) * 1000.0
    xmax = max(float(rc_curve.max()), float(Rk.max())) * 1.35
    for _zz in (z_start, z_end):
        shapes.append(dict(type="line", layer="above", xref="paper", yref="y",
                           x0=0.0, x1=1.0, y0=_zz * 1000.0, y1=_zz * 1000.0,
                           line=dict(color="#8a6d00", width=1, dash="dash")))

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=x_mm, y=zk, z=Zplot, colorscale="Inferno", connectgaps=False,
        colorbar=dict(title="°C", len=0.7, thickness=14, x=1.01),
        hovertemplate=i18n.tr("반경 %{x:.1f} mm<br>깊이 %{y:.1f} mm<br>온도 %{z:.0f} °C<extra></extra>"),
        name="온도"))
    for sgn in (-1, 1):
        fig.add_trace(go.Scatter(x=sgn * Rk, y=zk, mode="lines",
                                 line=dict(color="white", width=1.2),
                                 hoverinfo="skip", showlegend=False))
        fig.add_trace(go.Scatter(x=sgn * rc_curve, y=zc * 1000.0, mode="lines",
                                 line=dict(color="#e8c400", width=1, dash="dot"),
                                 hoverinfo="skip", showlegend=False))
    molten = Tk[:, -1] >= T_liq_C
    if molten.any():
        for sgn in (-1, 1):
            fig.add_trace(go.Scatter(
                x=sgn * Rk[molten], y=zk[molten], mode="markers",
                marker=dict(color="cyan", size=3),
                hovertemplate=i18n.tr("액상선 이상<br>깊이 %{y:.1f} mm<extra></extra>"),
                showlegend=False))
    anno = []
    if cone_m > 0:
        anno.append(dict(x=-xmax * 0.95, y=z_cone0 * 1000.0, xref="x", yref="y", text=i18n.tr("콘 시작"),
                         showarrow=False, xanchor="left", font=dict(color="white", size=10),
                         bgcolor="rgba(20,20,20,0.75)", yshift=9))
    for _zz, _lbl, _val in ((z_start, "코일 시작", coil_start), (z_end, "코일 끝", coil_end)):
        _y = max(_zz * 1000.0, top_mm + 2.0)          # 크롭 위로 나가면 상단에 붙임
        _cut = _y > _zz * 1000.0 + 0.5
        anno.append(dict(x=1.0, y=_y, xref="paper", yref="y",
                         text=i18n.tr(f"{_lbl} {_val:+.0f} mm" + ("  ↑ 위로 계속" if _cut else "")),
                         showarrow=False, xanchor="right", yanchor="bottom",
                         font=dict(color="#6b5500", size=9),
                         bgcolor="rgba(255,255,255,0.85)"))
    if tip_molten:
        anno.append(dict(x=0.015, y=y_tip_mm + 5.0, xref="paper", yref="y",
                         text=i18n.tr(f"{anno_metal} (We {We_tip_m:.1f})"),
                         showarrow=False, xanchor="left", yanchor="top",
                         font=dict(color="#cf1d1d", size=10),
                         bgcolor="rgba(255,255,255,0.85)"))
    fig.update_layout(
        height=560, margin=dict(l=70, r=95, t=46, b=44),
        title=dict(text=i18n.tr(f"가열 단면 — {coil_shape} · 위쪽 비가열부 생략 "
                                f"(색 = 온도, 마우스를 올리면 값)"), font=dict(size=13)),
        xaxis=dict(title=i18n.tr("반경 (mm)"), range=[-xmax, xmax], zeroline=False, showgrid=False),
        yaxis=dict(title=i18n.tr("깊이 (mm, 아래로 갈수록 팁)"), range=[bottom_mm, top_mm],
                   showgrid=False, scaleanchor="x", scaleratio=1, constrain="domain"),
        shapes=shapes, annotations=anno, plot_bgcolor="white")
    st.plotly_chart(fig, width="stretch")

    fig2, ax2 = plt.subplots()
    ax2.plot(T_surf, z * 1000, label=i18n.tr("표면 온도"))
    ax2.plot(T_cent, z * 1000, label=i18n.tr("중심 온도"))
    ax2.axvline(T_liq_C, color="c", ls="--", label=i18n.tr("액상선"))
    ax2.invert_yaxis()
    ax2.set_xlabel("°C")
    ax2.set_ylabel(i18n.tr("깊이 (mm)"))
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    st.pyplot(fig2)

    expl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "cone-vs-straight-explainer.png")
    if os.path.exists(expl_path):
        st.image(expl_path,
                 caption="원뿔 vs 직선 코일 — 왜 원뿔이 팁을 더 뜨겁게 만드는가 "
                         "(실제 계산 결과, 316L·50kW·효율 0.6·공급 2.0mm/s)")

# ---------------------------------------------------------------- 복사열
with tab_rad:
    st.header("복사열 — 주변(챔버 벽) 온도 변화")
    st.write("봉과 코일이 뜨거워지면 표면에서 복사로 주변 벽에 열을 보냅니다. 벽은 열용량 때문에 "
             "서서히 데워지고, 가스 대류와 외부 냉각·재복사로 열을 잃습니다. 고온부 온도·면적·복사율, "
             "벽 재질·두께·면적, 시간을 바꿔가며 **주변 온도가 시간에 따라** 어떻게 오르는지 봅니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        T_hot_C = st.number_input("고온부(봉·코일) 표면 온도 (°C)", 100.0, 2500.0, 1500.0, 10.0,
                                  key="r_thot")
        area_hot = st.number_input("고온부 표면적 (m²)", 0.001, 2.0, 0.030, 0.001, format="%.3f",
                                   key="r_ahot",
                                   help="예: 봉 Ø60 mm × 120 mm ≈ 0.023 m², 코일 턴까지 더하면 약 0.03 m².")
        eps_rad = st.number_input("복사율 ε", 0.05, 1.0, 0.8, 0.05, key="r_eps",
                                  help="산화된 금속 0.7~0.9, 광택 금속 0.1~0.3.")
        F_view = st.number_input("형상 계수 F (고온부→벽)", 0.01, 1.0, 0.30, 0.01, key="r_f",
                                 help="고온부가 벽을 보는 비율(기하). 챔버가 클수록 작습니다.")
    with c2:
        area_wall = st.number_input("주변 벽 면적 (m²)", 0.01, 10.0, 0.30, 0.01, key="r_awall")
        wall_t = st.number_input("벽 두께 (mm)", 0.5, 50.0, 5.0, 0.5, key="r_twall")
        wall_mat = st.selectbox("벽 재질",
                                ["스테인리스 (ρ 7900, cp 500)", "탄소강 (ρ 7850, cp 470)",
                                 "알루미늄 (ρ 2700, cp 900)", "구리 (ρ 8960, cp 385)"],
                                key="r_mat")
        h_conv = st.number_input("가스 대류 계수 h (W/m²·K)", 0.0, 500.0, 10.0, 1.0, key="r_h",
                                 help="정지 가스 5~20, 순환 가스 50~200.")
        h_out = st.number_input("벽 외부 냉각 계수 (W/m²·K)", 0.0, 5000.0, 50.0, 10.0, key="r_hout",
                                help="물 재킷이면 500~3000, 진공·단열이면 작게(0~20).")
    with c3:
        T_wall0 = st.number_input("벽 초기 온도 (°C)", 0.0, 1500.0, 25.0, 5.0, key="r_tw0")
        T_gas = st.number_input("가스(챔버) 온도 (°C)", 0.0, 1500.0, 25.0, 5.0, key="r_tgas")
        t_end = st.number_input("관찰 시간 (s)", 10.0, 7200.0, 600.0, 10.0, key="r_tend")
        st.caption("벽은 두께 방향으로 온도가 균일(집중 열용량)하다고 가정합니다.")

    wall_mats = {"스테인리스 (ρ 7900, cp 500)": (7900.0, 500.0),
                 "탄소강 (ρ 7850, cp 470)": (7850.0, 470.0),
                 "알루미늄 (ρ 2700, cp 900)": (2700.0, 900.0),
                 "구리 (ρ 8960, cp 385)": (8960.0, 385.0)}
    rho_w, cp_w = wall_mats[wall_mat]
    t_r, Tw_r, Q_r, T_eq_r, t90_r = ph.wall_temperature_transient(
        T_hot_C + 273.15, T_wall0 + 273.15, T_gas + 273.15,
        area_hot, area_wall, view_factor=F_view, eps=eps_rad,
        thick_m=wall_t / 1000.0, rho_w=rho_w, cp_w=cp_w,
        h_conv=h_conv, h_out=h_out, t_end=t_end, n_out=300)
    q_flux0 = ph.radiation_heat_flux(T_hot_C + 273.15, T_wall0 + 273.15, eps_rad) / 1000.0
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("초기 복사 열유속", f"{q_flux0:.1f} kW/m²")
    m2.metric("평형(정상상태) 벽 온도", f"{T_eq_r:.0f} °C")
    m3.metric("90 % 도달 시간", f"{t90_r:.0f} s")
    m4.metric(f"{t_end:.0f} s 뒤 벽 온도", f"{Tw_r[-1]:.0f} °C")

    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    fig_r = make_subplots(specs=[[{"secondary_y": True}]])
    fig_r.add_trace(go.Scatter(x=t_r, y=Tw_r, name=i18n.tr("벽 온도"),
                               line=dict(color="#d9480f", width=2),
                               hovertemplate="t = %{x:.0f} s<br>벽 %{y:.0f} °C<extra></extra>"),
                    secondary_y=False)
    fig_r.add_trace(go.Scatter(x=t_r, y=Q_r / 1000.0, name=i18n.tr("복사 열유량"),
                               line=dict(color="#1c7ed6", width=1.5, dash="dot"),
                               hovertemplate="t = %{x:.0f} s<br>%{y:.2f} kW<extra></extra>"),
                    secondary_y=True)
    fig_r.add_hline(y=T_eq_r, line=dict(color="#d9480f", width=1, dash="dash"),
                    annotation_text=i18n.tr(f"평형 {T_eq_r:.0f} °C"), annotation_position="top left")
    fig_r.update_layout(height=430, margin=dict(l=64, r=64, t=44, b=40),
                        title=dict(text=i18n.tr("주변 벽 온도와 복사 열유량 (시간에 따라)"),
                                   font=dict(size=13)),
                        legend=dict(orientation="h", y=1.02, x=0))
    fig_r.update_xaxes(title=i18n.tr("시간 (s)"))
    fig_r.update_yaxes(title=i18n.tr("벽 온도 (°C)"), secondary_y=False)
    fig_r.update_yaxes(title=i18n.tr("복사 열유량 (kW)"), secondary_y=True, showgrid=False)
    st.plotly_chart(fig_r, width="stretch")
    st.write(f"벽 열용량 m·cp = {rho_w * wall_t / 1000.0 * area_wall * cp_w / 1000:.1f} kJ/K — "
             "무거운 벽일수록 천천히 데워집니다. 초기 복사 열유속은 벽이 차가울 때 가장 크고, "
             "벽이 데워지면 T⁴ 차이가 줄어 급격히 떨어집니다(파란 점선).")

with tab6:
    st.header("사용법·한계")
    st.markdown(i18n.doc("usage", """
**쓰는 순서**
1. 사이드바에서 합금과 가스를 고릅니다.
2. `1 공정`에서 조건을 바꾸며 D50·입도분포·수율을 보고, 스윕과 공정 윈도우로 규칙을 찾습니다.
3. `2 봉·코일`에서 용탕 생성량과 팁 이탈 모드(물방울/실)를 확인합니다.
4. `3 노즐`에서 가스 유량·GMR·통과 시간을 보고 노즐 형상의 영향을 봅니다.
5. `4 분말 품질`에서 응고 거리가 챔버 안에 들어가는지 확인합니다.
6. `5 수율 계산`에서 합격 입도 범위(예: 10~45 µm)를 지정하면 그 범위가 전체 수율의 몇 %인지 나옵니다.
7. `복사열`에서 고온부가 주변 벽을 시간에 따라 얼마나 데우는지 확인합니다.

**팁 이탈 모드(물방울 vs 실) — 왜 갈리나**
- 판정은 **팁 Weber 수** `We = ρ·v²·d/σ` 하나로 합니다 (ρ 용탕 밀도, v 팁 출구 속도, d 팁 구멍 지름, σ 표면장력).
- **녹았는지 여부와는 별개**입니다. 팁이 액상선을 넘어 완전히 녹아도, 출구 속도가 느리고 구멍이 크면
  관성이 표면장력을 이기지 못해 액적이 매달렸다 끊어지며 **물방울**로 떨어집니다 (`We < 4`).
- 구멍이 작거나 유량(속도)이 크면 가는 **실**이 됩니다 (`We > 12`). `4~12`는 전이 영역.
- 따라서 “녹은 덩어리가 통째로 떨어진다”의 주원인은 **고주파 조건이 아니라 출구 유속·구멍 지름**입니다.
  출력이 낮아 국부만 녹는 경우에도 덩어리가 떨어지지만, 이 모델은 팁이 균일하게 용융됐다고 가정하므로
  그 현상은 다루지 않습니다.
- 실 모드로 가려면: 팁 지름↓, 코일 출력·공급속도↑(유량↑), 간극↓(결합↑), 과열↑(σ↓).
- **점도**는 `Oh = μ/√(ρ·σ·d)` 로 들어갑니다. 점성이 크면 경계 We가 올라가 물방울 쪽이 넓어집니다.
  다만 팁 구멍이 mm급이면 `Oh ≈ 0.002` 로 영향이 1 % 미만이고, 마이크로 오리피스나 고점도 용탕
  (슬래그·글라스)에서 중요해집니다. **현재 판정식은 We만 사용합니다(한계).**
- σ는 온도가 오르면 줄어 We가 커집니다 → 같은 유속이라도 과열이 크면 실 쪽으로 갑니다.

**복사열 탭**
- 고온부는 `q = ε·σ·A_hot·F·(T_hot⁴ − T_wall⁴)` 로 벽에 복사 열을 보냅니다.
- 벽은 열용량 `m·cp` 만큼 서서히 데워지고, 가스 대류(`h·A·(T−T_gas)`)와 외부 냉각·재복사로 열을 잃습니다.
- 시간 상수는 대략 `τ = m·cp/(4εσA·T³ + h·A)` 이고, ‘90 % 도달 시간’으로 확인합니다.
- 물 냉각 벽(h_out ↑)은 온도가 낮게 유지되고, 진공·단열이면 수백 도까지 오릅니다.

**핵심 식**
- Lubanska 상관식: D50/D = K·√[(νm/νg)·(1/We)·(1+M/A)], We는 용탕 밀도 기준
- 입도분포: 로그정규 분포 (σg 기본값 2.0)
- 가스: 초크(음속) 조건에서 음속 제트, 질량유량은 초크 유량식
- 팁 이탈 모드: 휴리스틱(v1) — 임계값은 경험으로 보정 필요

**한계 (솔직하게)**
- CFD가 아닙니다. 난류, 노즐 내부 유동, 실제 3차원 형상은 풀지 않습니다.
- 물성은 대표값입니다. 본인 합금 실측값으로 교체하세요.
- K 상수, 코일 효율, 이탈 모드 임계값은 장비 의존 보정 파라미터입니다.
- 상변화·산화·유동성은 2단계에서 추가됩니다.

**다음 단계**
- 과거 ALD 운전 기록이 있으면 K와 이탈 모드 임계값, 테이퍼 지수 q를 보정합니다.
- 목표 노즐 형태를 첫 테스트 케이스로 넣어봅니다.
- 노즐 형상(보어, 분사각, 슬릿 형태)과 코일 테이퍼를 조합한 최적 조건 탐색을
  스윕/윈도우로 확장합니다.
"""))
