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
# 조건 불러오기로 합금/가스를 바꿀 수 있게 선택박스에 키를 둔다.
# 키를 새로 단 첫 실행에는 이전에 본 합금(_alloy_seen)을 이어받아 선택이 초기화되지 않게 한다.
if "sel_alloy" not in st.session_state and st.session_state.get("_alloy_seen") in ALLOYS:
    st.session_state["sel_alloy"] = st.session_state["_alloy_seen"]
if "sel_gas" not in st.session_state:
    st.session_state["sel_gas"] = list(GASES.keys())[0]
alloy_name = st.sidebar.selectbox("합금", list(ALLOYS.keys()), index=0, key="sel_alloy")
gas_name = st.sidebar.selectbox("분무 가스", list(GASES.keys()), index=0, key="sel_gas")
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

# ---------------------------------------------------------------- 연동(linking) 계층
# 값마다 '주인' 탭을 하나만 둡니다.
#   1 공정       : 가스 압력·챔버 압력·금속 온도·용탕류 직경·입도 목표 (공정 조건의 기준)
#   2 봉·코일     : 봉 지름·공급 속도·회전·코일 출력·효율 (용탕 생성량의 계산 기준)
#   코일 가열 보기 : 코일 형상(위치·간극·턴수·주파수·선재)
# 나머지 탭은 이 값을 받아 쓰고, 직접 고치려 하면 연동 해제를 안내합니다.
# Streamlit은 위젯이 만들어진 뒤에는 그 값을 바꿀 수 없으므로, 연동은 탭을 만들기 전에
# session_state로 밀어 넣습니다. 사용자가 직접 고친 값은 덮지 않습니다.

_DEFAULTS = {
    # 1 공정
    "t1_pgas": 35.0, "t1_pch": 1.5, "t1_tgas": 300.0,
    "t1_tmelt": float(alloy["T_liquidus"] - 273.15) + 50.0,
    "t1_dstream": 3.0, "t1_gasarea": 20.0, "t1_k": 40.0, "t1_sig": 2.0,
    "t1_dmin": 15.0, "t1_dmax": 40.0,
    # 2 봉·코일
    "t2_rod_d": 60.0, "t2_feed": 2.0, "t2_rpm": 60.0,
    "t2_pcoil": 80.0, "t2_eff": 0.6, "t2_fall_mm": 200.0,
    "t2_tmelt": float(alloy["T_liquidus"] - 273.15) + 50.0,
    "t2_lo": 4.0, "t2_hi": 12.0, "t2_q": 0.5,
    # 3 노즐
    "t3_bore": 18.0, "t3_blen": 20.0, "t3_angle": 30.0,
    "t3_pitch": 30.0, "t3_slit": 0.5, "t3_holes": 12.0, "t3_hole": 1.5,
    "t3_dp": 0.5, "t3_v0": 0.5, "t3_cd": 0.9, "t3_exit": 10.0,
    # 4 분말 품질
    "t4_drop": 40.0, "t4_vdrop": 5.0, "t4_chh": 1.5, "t4_tgas": 25.0,
    "t4_ox": 5.0, "t4_fines": 10.0,
    # 코일 가열 보기 (코일 형상의 기준)
    "g_cone": 40.0, "g_tip": 1.0, "g_cstart": 90.0, "g_cend": -10.0,
    "g_crop": 0.0, "g_gap": 20.0, "g_turns": 5, "g_wire": 6.0,
    "g_ww": 8.0, "g_wh": 6.0, "g_freq": 30.0, "g_tfeed": 25.0, "g_shank": 30.0,
    "g_shape_p": 2.0,
    "g_rodlen": 100.0,
    "g_len": 100.0, "g_top": 100.0, "g_bot": 100.0,
    # 복사열
    "rad_ahot": 0.030, "rad_eps": 0.8, "rad_f": 0.30, "rad_awall": 0.30,
    "rad_twall": 5.0, "rad_h": 10.0, "rad_hout": 50.0,
    "rad_tw0": 25.0, "rad_tgas": 25.0, "rad_tend": 1800.0,
    # 선택 항목
    "t2_tip": "평탄", "t3_type": "환형 슬릿", "t3_profile": "직선 (초크, Mach 1)",
    "g_shape": "봉 형상 따라가기 (콘 밀착)", "g_sect": "원형",
    "rad_mat": "스테인리스 (ρ 7900, cp 500)",
    # 연동 스위치 (기본 켜짐)
    "h_sync": True,
}
for _k, _v in _DEFAULTS.items():
    if _k not in st.session_state:
        st.session_state[_k] = _v

# 낙하 거리 단일화: 예전 두 입력(2(a) t2_fall_mm, 코일뷰 g_fall)은 같은 물리량
# (팁→노즐 = 팁→가스 영역, 가스 제트가 노즐 보어 자리)이므로 fall_mm 하나를 공유한다.
# 두 탭 위젯은 각각 fall_mm_2a / fall_mm_coil 키를 쓰고 on_change로 fall_mm에 연동한다
# (Streamlit은 같은 키의 위젯을 두 번 만들 수 없어서 키를 나눈 것).
# 기존 세션 값은 2(a) 값(사용자가 직접 바꾼 값) 우선으로 이어받는다.
if "fall_mm" not in st.session_state:
    if "t2_fall_mm" in st.session_state:
        st.session_state["fall_mm"] = st.session_state["t2_fall_mm"]
    elif "g_fall" in st.session_state:
        st.session_state["fall_mm"] = st.session_state["g_fall"]
    else:
        st.session_state["fall_mm"] = 200.0


# ---------------------------------------------------------------- 조건 저장/불러오기
# 공정 조건(합금·가스·1공정·2봉코일·코일형상·3노즐·4분말·복사열)을 이름+메모와 함께
# presets.json 파일에 저장하고, 목록에서 골라 불러온다. 파일이 있으면 매 실행마다
# 읽어오므로 새로 받은 파일이 바로 목록에 보인다. 저장할 때마다 .bak 백업을 남긴다.
import json as _json
import os as _os

_PRESET_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "presets.json")
_PRESET_KEYS = ([k for k in _DEFAULTS
                 if k not in ("t1_tmelt", "t2_tmelt", "t2_fall_mm", "h_sync")]
                + ["fall_mm", "sel_alloy", "sel_gas"])


def _load_presets_from_disk():
    try:
        with open(_PRESET_FILE, "r", encoding="utf-8") as _f:
            _data = _json.load(_f)
    except (OSError, ValueError):
        return None
    if not isinstance(_data, list):
        return None
    _out = []
    for _p in _data:
        if isinstance(_p, dict) and isinstance(_p.get("values"), dict) and _p.get("title"):
            _out.append({"title": str(_p["title"]),
                         "memo": str(_p.get("memo", "")),
                         "values": dict(_p["values"])})
    return _out


def _save_presets_to_disk(presets):
    try:
        if _os.path.exists(_PRESET_FILE):
            _os.replace(_PRESET_FILE, _PRESET_FILE + ".bak")
        with open(_PRESET_FILE, "w", encoding="utf-8") as _f:
            _json.dump(presets, _f, ensure_ascii=False, indent=2)
        return True
    except OSError:
        return False


def _preset_clean_value(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)):
        return v
    try:
        return float(v)
    except (TypeError, ValueError):
        return str(v)


def _preset_summary(values):
    _alloy = values.get("sel_alloy", "?")
    _p = values.get("t2_pcoil", "?")
    _f = values.get("t2_feed", "?")
    _tip = values.get("g_tip", "?")
    _fall = values.get("fall_mm", "?")
    _bore = values.get("t3_bore", "?")
    return f"{_alloy} · {_p}kW · 공급 {_f}mm/s · 팁 Ø{_tip} · 낙하 {_fall}mm · 보어 Ø{_bore}"


_disk_presets = _load_presets_from_disk()
if _disk_presets is not None:
    st.session_state["presets"] = _disk_presets
if "presets" not in st.session_state:
    st.session_state["presets"] = []


def _preset_save_current():
    _ss = st.session_state
    _title = str(_ss.get("preset_new_title", "")).strip()
    _presets = list(_ss.get("presets", []))
    if not _title:
        _title = f"조건 {len(_presets) + 1}"
    _values = {k: _preset_clean_value(_ss[k]) for k in _PRESET_KEYS if k in _ss}
    _presets.append({"title": _title, "memo": str(_ss.get("preset_new_memo", "")),
                     "values": _values})
    if _save_presets_to_disk(_presets):
        _ss["presets"] = _presets
        _ss["preset_msg"] = f"저장했습니다: {_title}"
    else:
        _ss["preset_msg"] = "저장에 실패했습니다 (presets.json 쓰기 오류)."
    _ss["preset_new_title"] = ""
    _ss["preset_new_memo"] = ""


def _preset_load_selected():
    _ss = st.session_state
    _presets = list(_ss.get("presets", []))
    _idx = _ss.get("preset_select", 0)
    if not _presets or _idx is None or int(_idx) >= len(_presets):
        return
    _p = _presets[int(_idx)]
    for _k, _v in _p["values"].items():
        _ss[_k] = _v
    _ss["preset_edit_title"] = _p["title"]
    _ss["preset_edit_memo"] = _p.get("memo", "")
    _ss["preset_msg"] = f"불러왔습니다: {_p['title']}"


def _preset_select_changed():
    _ss = st.session_state
    _presets = list(_ss.get("presets", []))
    _idx = _ss.get("preset_select", 0)
    if _presets and _idx is not None and int(_idx) < len(_presets):
        _p = _presets[int(_idx)]
        _ss["preset_edit_title"] = _p["title"]
        _ss["preset_edit_memo"] = _p.get("memo", "")


def _preset_update_meta():
    _ss = st.session_state
    _presets = list(_ss.get("presets", []))
    _idx = _ss.get("preset_select", 0)
    if not _presets or _idx is None or int(_idx) >= len(_presets):
        return
    _presets[int(_idx)]["title"] = str(_ss.get("preset_edit_title", "")).strip() or _presets[int(_idx)]["title"]
    _presets[int(_idx)]["memo"] = str(_ss.get("preset_edit_memo", ""))
    if _save_presets_to_disk(_presets):
        _ss["presets"] = _presets
        _ss["preset_msg"] = "제목/메모를 저장했습니다."
    else:
        _ss["preset_msg"] = "저장에 실패했습니다 (presets.json 쓰기 오류)."


def _preset_delete_selected():
    _ss = st.session_state
    _presets = list(_ss.get("presets", []))
    _idx = _ss.get("preset_select", 0)
    if not _presets or _idx is None or int(_idx) >= len(_presets):
        return
    _title = _presets[int(_idx)]["title"]
    del _presets[int(_idx)]
    if _save_presets_to_disk(_presets):
        _ss["presets"] = _presets
        _ss["preset_msg"] = f"삭제했습니다: {_title}"
    else:
        _ss["preset_msg"] = "삭제 저장에 실패했습니다 (presets.json 쓰기 오류)."
    _ss["preset_delete_armed"] = False
    _ss["preset_select"] = 0
    if _presets:
        _ss["preset_edit_title"] = _presets[0]["title"]
        _ss["preset_edit_memo"] = _presets[0].get("memo", "")
    else:
        _ss["preset_edit_title"] = ""
        _ss["preset_edit_memo"] = ""


st.sidebar.header("조건 저장 / 불러오기")
if st.session_state.get("preset_msg"):
    st.sidebar.success(st.session_state["preset_msg"])
    st.session_state["preset_msg"] = ""
_presets_now = list(st.session_state.get("presets", []))
st.sidebar.text_input("새 조건 제목", key="preset_new_title")
st.sidebar.text_area("새 조건 메모", key="preset_new_memo")
st.sidebar.button("현재 조건 저장", on_click=_preset_save_current)
if _presets_now:
    st.sidebar.selectbox("불러올 조건", options=list(range(len(_presets_now))),
                         format_func=lambda i: _presets_now[i]["title"],
                         key="preset_select", on_change=_preset_select_changed)
    _sel_idx = st.session_state.get("preset_select", 0)
    if _sel_idx is None or int(_sel_idx) >= len(_presets_now):
        _sel_idx = 0
    _sel = _presets_now[int(_sel_idx)]
    if "preset_edit_title" not in st.session_state:
        st.session_state["preset_edit_title"] = _sel["title"]
    if "preset_edit_memo" not in st.session_state:
        st.session_state["preset_edit_memo"] = _sel.get("memo", "")
    st.sidebar.caption(_preset_summary(_sel["values"]))
    if _sel.get("memo"):
        st.sidebar.caption(_sel["memo"])
    st.sidebar.button("불러오기", on_click=_preset_load_selected)
    st.sidebar.text_input("제목 수정", key="preset_edit_title")
    st.sidebar.text_area("메모 수정", key="preset_edit_memo")
    st.sidebar.button("제목/메모 저장", on_click=_preset_update_meta)
    if st.session_state.get("preset_delete_armed"):
        st.sidebar.warning("정말 삭제할까요?")
        st.sidebar.button("삭제 확인", on_click=_preset_delete_selected)
        if st.sidebar.button("삭제 취소"):
            st.session_state["preset_delete_armed"] = False
    else:
        if st.sidebar.button("선택한 조건 삭제"):
            st.session_state["preset_delete_armed"] = True
else:
    st.sidebar.caption("저장된 조건이 없습니다. 위에서 현재 조건을 저장하세요.")


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


def _num(label, lo, hi, default, key, step=None, fmt=None, help=None, disabled=False, link=None):
    """키가 고정된 숫자 입력. session_state 값을 먼저 채워 연동값이 들어가게 합니다.

    Streamlit은 number_input의 value/min_value/max_value/step가 모두 같은
    타입(전부 int 또는 전부 float)이어야 합니다. 호출부가 int 범위 + float 스텝처럼
    섞어서 넘겨도(예: 홀 개수 1, 100, 12, step 1.0) 여기서 하나로 통일합니다.
    세션에 이미 들어 있는 값(이전 버전에서 남은 문자열 포함)도 같은 타입으로 강제
    변환하고, 숫자로 바꿀 수 없으면 기본값으로 되돌립니다.
    """
    ss = st.session_state
    use_float = (isinstance(step, float)
                 or any(isinstance(v, float) for v in (lo, hi, default)))

    def _coerce(v, fallback):
        try:
            f = float(v)
        except (TypeError, ValueError):
            return fallback
        return f if use_float else int(f)

    lo_c = _coerce(lo, 0)
    hi_c = _coerce(hi, lo_c)
    def_c = _clamp(_coerce(default, lo_c), lo_c, hi_c)
    if link is not None and link in ss:
        # 연동 입력: 위젯 생성 전에 공유값으로 맞춘다 (생성 뒤에는 바꿀 수 없음).
        ss[key] = _clamp(_coerce(ss[link], def_c), lo_c, hi_c)
    elif key not in ss:
        ss[key] = def_c
    else:
        ss[key] = _clamp(_coerce(ss[key], def_c), lo_c, hi_c)
    kw = dict(min_value=lo_c, max_value=hi_c, key=key, help=help, disabled=disabled)
    if link is not None:
        def _sync_to_link():
            ss[link] = ss[key]
        kw["on_change"] = _sync_to_link
    if step is not None:
        kw["step"] = float(step) if use_float else int(step)
    if fmt:
        kw["format"] = fmt
    return st.number_input(label, **kw)


def _opt_back(cur, options):
    """화면에 보이는(번역된) 선택값을 한국어 원문 옵션으로 되돌립니다."""
    if cur is None:
        return None
    for o in options:
        shown = i18n.tr(o)
        if o == cur or shown == cur or str(shown).lower() == str(cur).lower():
            return o
    return None


def _sel(label, options, key, index=0, help=None):
    ss = st.session_state
    if ss.get(key) not in options:
        # 저장값이 번역된 표시값이면 원문으로 되돌린 뒤, 위젯이 실제로 보여주는 값으로 넣습니다.
        back = _opt_back(ss.get(key), options) or options[index]
        ss[key] = i18n.tr(back)
    kw = dict(options=options, key=key)
    if help:
        kw["help"] = help
    return st.selectbox(label, **kw)


# 합금을 바꾸면 녹는점(액상선)이 달라지므로, 온도 관련 값을 새 합금 기준으로 다시 잡습니다.
# (위젯 키가 세션에 남아 있으면 예전 온도가 그대로 유지되기 때문입니다.)
if st.session_state.get("_alloy_seen") != alloy_name:
    st.session_state["_alloy_seen"] = alloy_name
    _tm_new = float(alloy["T_liquidus"] - 273.15) + 50.0
    st.session_state["t1_tmelt"] = _tm_new
    st.session_state["t2_tmelt"] = _tm_new
    st.session_state["t4_tdrop"] = float(_clamp(_tm_new, 1000.0, 2500.0))
    for _k in ("t1_tmelt", "t2_tmelt", "t4_tdrop"):
        st.session_state["_p_" + _k] = None
        st.session_state["_e_" + _k] = False


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


def _push(dst, value, lo, hi, tol=1e-6):
    """연동값을 dst 위젯의 session_state에 넣습니다(사용자가 고친 값은 덮지 않음)."""
    ss = st.session_state
    if not ss.get("h_sync", True) or ss.get("unl_" + dst):
        return
    v = float(_clamp(float(value), lo, hi))
    last = ss.get("_p_" + dst)
    cur = ss.get(dst)
    if last is not None and cur is not None and abs(float(cur) - float(last)) > tol:
        ss["_e_" + dst] = True          # 직접 고친 값 → 덮지 않고 연동 해제를 안내
        return
    ss[dst] = v
    ss["_p_" + dst] = v


def _unlink_ui(key):
    """연동된 값을 고치려 했을 때 안내하고, 연동 해제/복구 버튼을 보여줍니다."""
    ss = st.session_state
    if not ss.get("h_sync", True):
        return
    if ss.get("unl_" + key):
        c1, c2 = st.columns([3, 1])
        c1.caption("연동 해제됨 — 이 탭에서 직접 입력하는 값입니다.")
        if c2.button("연동 다시 사용", key="rl_" + key, width="stretch"):
            ss["unl_" + key] = False
            ss["_p_" + key] = None
            st.rerun()
        return
    if not ss.get("_e_" + key):
        return
    st.warning("이 값은 앞 탭에서 연동된 값입니다. 직접 입력하려면 연동을 해제해야 합니다.")
    c1, c2 = st.columns(2)
    if c1.button("연동 해제하고 이 값 사용", key="ul_" + key, width="stretch"):
        ss["unl_" + key] = True
        ss["_e_" + key] = False
        ss["_p_" + key] = None
        st.rerun()
    if c2.button("연동값으로 되돌리기", key="rb_" + key, width="stretch"):
        ss["_e_" + key] = False
        ss["_p_" + key] = None
        st.rerun()


_TM_LO = float(alloy["T_liquidus"] - 273.15) - 50.0
_TM_HI = float(alloy["T_liquidus"] - 273.15) + 300.0

# 양방향으로 공유하는 설정값 그룹. 첫 번째 항목이 1 공정(기준)입니다.
_GROUPS = (
    ("gas", (("t1_pgas", 1.0, 300.0), ("t3_p0", 1.0, 300.0))),
    ("chamber", (("t1_pch", 0.1, 10.0), ("t3_pc", 0.1, 10.0))),
    ("tmelt", (("t1_tmelt", _TM_LO, _TM_HI), ("t2_tmelt", _TM_LO, _TM_HI),
               ("t4_tdrop", 1000.0, 2500.0))),
    ("sig", (("t1_sig", 1.2, 4.0), ("t4_sig", 1.2, 4.0), ("t5_sig", 1.2, 4.0))),
    ("dmin", (("t1_dmin", 0.0, 200.0), ("t5_dmin", 0.0, 500.0))),
    ("dmax", (("t1_dmax", 1.0, 500.0), ("t5_dmax", 0.0, 500.0))),
)


def _sync_groups():
    """설정값을 모든 탭에서 같은 값으로 맞춥니다(어느 탭에서 고치든 양방향)."""
    ss = st.session_state
    if not ss.get("h_sync", True):
        return
    for _name, members in _GROUPS:
        canon = None
        for key, lo, hi in members:              # 이번 실행에서 고친 탭을 먼저 찾음
            if ss.get("unl_" + key):
                continue
            cur = ss.get(key)
            last = ss.get("_p_" + key)
            if cur is not None and last is not None and abs(float(cur) - float(last)) > 1e-6:
                canon = float(cur)
                break
        if canon is None:
            for key, lo, hi in members:
                if ss.get(key) is not None:
                    canon = float(ss[key])
                    break
        if canon is None:
            continue
        canon = float(_clamp(canon, members[0][1], members[0][2]))
        for key, lo, hi in members:
            if ss.get("unl_" + key):
                continue
            v = float(_clamp(canon, lo, hi))
            ss[key] = v
            ss["_p_" + key] = v


def _process_chain():
    """입력만으로 용탕 생성량·입도를 미리 계산합니다.

    탭을 만들기 전에 계산해 두면, 연동값이 같은 실행에서 앞 탭에 들어가므로
    화면이 한 번 깜빡이며 다시 그려지는 일(추가 재실행)이 없습니다.
    """
    ss = st.session_state
    T_C = float(ss["t1_tmelt"])
    T_K = T_C + 273.15
    P = float(ss["t2_pcoil"])
    eff = float(ss["t2_eff"])
    m_pow = ph.melt_rate_from_power(P, eff, alloy, T_K)                 # kg/s
    rod = float(ss["t2_rod_d"])
    feed = float(ss["t2_feed"])
    m_feed = alloy["rho_melt"] * math.pi * (rod / 2000.0) ** 2 * (feed / 1000.0)
    m_dot = min(m_pow, m_feed) if m_feed > 0 else m_pow
    melt = m_dot * 60.0
    m_gas = gas_flow_kg_min(float(ss["t1_pgas"]), float(ss["t1_tgas"]),
                            float(ss["t1_gasarea"]))
    gmr = m_gas / melt if melt > 0 else 0.0
    r = lubanska_block(float(ss["t1_pgas"]), float(ss["t1_pch"]),
                       float(ss["t1_tgas"]), T_C, float(ss["t1_dstream"]),
                       gmr, float(ss["t1_k"]))
    sig = float(ss["t1_sig"])
    d10, d50, d90 = ph.D_values(r["D50"], sig)
    v_fall = math.sqrt(2.0 * 9.81 * float(ss.get("fall_mm", 200.0)) / 1000.0)
    ss["melt_rate"] = melt
    ss["D50_um"] = d50 * 1e6
    ss["sig_g"] = sig
    ss["stream_d"] = ph.stream_diameter(m_dot, alloy["rho_melt"], v_fall) * 1000.0
    return {"m_dot": m_dot, "melt": melt, "m_gas": m_gas, "gmr": gmr, "r": r,
            "sig": sig, "d10": d10, "d50": d50, "d90": d90}


# 연동 스위치를 껐다 켜면 이전 편집 표시를 지워, 다시 연동값이 우선하도록 합니다.
_sync_now = bool(st.session_state.get("h_sync", True))
if st.session_state.get("_sync_prev") != _sync_now:
    for _k in [k for k in list(st.session_state.keys())
               if k.startswith("_p_") or k.startswith("_e_")]:
        try:
            del st.session_state[_k]
        except KeyError:
            pass
st.session_state["_sync_prev"] = _sync_now

_sync_groups()
_CHAIN = _process_chain()

# 설정값은 _sync_groups()가 모든 탭에 같은 값으로 맞추고,
# 계산으로 나오는 값(용탕 유량·D50)만 한 방향으로 밀어 넣습니다.
_push("t4_d50", _CHAIN["d50"] * 1e6, 1.0, 500.0)
_push("t5_d50", _CHAIN["d50"] * 1e6, 1.0, 500.0)
# 2 봉·코일 → 1·3 탭 용탕 유량, 5 수율
_push("t1_meltflow", _CHAIN["melt"], 0.1, 100.0)
_push("t3_meltflow", _CHAIN["melt"], 0.1, 100.0)
_push("t5_melt", _CHAIN["melt"], 0.1, 100.0)


tab1, tab2, tab3, tab4, tab5, tab_rad, tab6 = st.tabs(
    ["1 공정", "2 봉·코일", "3 노즐", "4 분말 품질", "5 수율 계산",
     "복사열", "사용법·한계"])


# ---------------------------------------------------------------- tab 1
with tab1:
    st.header("1. 공정부분 — 조건 조절에 따른 입도분포와 외관형상")
    st.write("주의: 가스 압력은 제트 속도가 아니라 가스 유량→GMR을 통해 입도에 작용합니다. "
             "초크(음속) 상태에서는 속도가 포화되므로, 압력을 올려도 속도는 안 올라가고 "
             "유량만 늘어납니다. 그래서 압력 효과가 보이려면 GMR을 입력값이 아니라 "
             "가스 유량/용탕 유량으로 계산해야 합니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        P_gas = _num("가스 공급압력 (bar)", 1.0, 300.0, 35.0, "t1_pgas", 1.0)
        P_ch = _num("챔버 압력 (bar)", 0.1, 10.0, 1.5, "t1_pch", 0.1)
        T_gas = _num("가스 온도 (K)", 200.0, 1000.0, 300.0, "t1_tgas", 10.0)
    with c2:
        T_melt = _num("금속 온도 (°C)",
                      float(alloy["T_liquidus"] - 273.15) - 50,
                      float(alloy["T_liquidus"] - 273.15) + 300,
                      float(alloy["T_liquidus"] - 273.15) + 50, "t1_tmelt", 10.0,
                      help="코일이 녹여 낸 용탕의 온도입니다. 2 봉·코일과 4 분말 품질 탭이 "
                           "이 값을 그대로 받아 씁니다.")
        D_stream = _num("용탕류 직경 (mm)", 0.5, 10.0, 3.0, "t1_dstream", 0.1)
        melt_flow = _num("용탕 유량 (kg/min)", 0.1, 100.0, 2.0, "t1_meltflow", 0.1,
                         help="2 봉·코일의 봉 지름·공급 속도·코일 출력에서 계산된 값이 "
                              "자동으로 들어옵니다. 직접 입력하려면 연동을 해제하세요.")
        _unlink_ui("t1_meltflow")
        gas_area = _num("가스 출구 면적 (mm²)", 1.0, 200.0, 20.0, "t1_gasarea", 1.0)
    with c3:
        K = _num("Lubanska 상수 K (장비 보정값)", 1.0, 200.0, 40.0, "t1_k", 1.0)
        sig_g = _num("입도분포 폭 σg (로그정규)", 1.2, 4.0, 2.0, "t1_sig", 0.1)
        t_min = _num("목표 입도 하한 (µm)", 0.0, 200.0, 15.0, "t1_dmin", 1.0)
        t_max = _num("목표 입도 상한 (µm)", 1.0, 500.0, 40.0, "t1_dmax", 1.0)

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
    sync_on = st.checkbox(
        "연동 사용 — 앞 공정 값과 자동으로 연동", key="h_sync",
        help="켜면 값이 모든 탭에서 양방향으로 공유됩니다. 여기서 고친 봉 지름·코일 출력·"
             "코일 형상도 1 공정 계산과 용탕 유량, 복사열에 바로 반영됩니다. "
             "끄면 각 탭이 자기 값을 그대로 씁니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        rod_d = _num("봉 지름 (mm)", 10.0, 100.0, 60.0, "t2_rod_d", 1.0)
        feed = _num("봉 공급 속도 (mm/s)", 0.1, 20.0, 2.0, "t2_feed", 0.1)
        rpm = _num("봉 회전 속도 (rpm)", 0.0, 500.0, 60.0, "t2_rpm", 1.0)
    with c2:
        P_coil = _num("코일 출력 (kW)", 1.0, 500.0, 80.0, "t2_pcoil", 1.0)
        eff = _num("코일 효율", 0.1, 1.0, 0.6, "t2_eff", 0.05)
        turns = int(_num("코일 감은 횟수 (턴)", 1.0, 50.0, 5.0, "g_turns", 1.0))
        coil_len = float(st.session_state["g_len"])
        _shape_now = str(st.session_state.get("g_shape", "봉 형상 따라가기 (콘 밀착)"))
        if "따라가기" in _shape_now or "follow" in _shape_now.lower():
            coil_top = coil_bot = rod_d + 2.0 * float(st.session_state["g_gap"])
        else:
            coil_top = float(st.session_state["g_top"])
            coil_bot = float(st.session_state["g_bot"])
        st.caption(f"코일 {turns}턴 · 길이 {coil_len:.0f} mm · 상부 {coil_top:.0f} / "
                   f"하부 {coil_bot:.0f} mm — `2(b) 코일 형상`의 위치·간극·턴수에서 "
                   f"자동 계산됩니다.")
    with c3:
        tip_shape = _sel("팁 형상", ["평탄", "둥근", "샤프"], "t2_tip")
        fall_h = _num("팁→노즐(가스 영역) 낙하 높이 (mm)", 0.0, 1000.0, 200.0, "fall_mm_2a", 1.0, link="fall_mm")
        T_melt2 = _num("용탕 온도 (°C) ",
                       float(alloy["T_liquidus"] - 273.15) - 50,
                       float(alloy["T_liquidus"] - 273.15) + 300,
                       float(alloy["T_liquidus"] - 273.15) + 50, "t2_tmelt", 10.0,
                       help="`1 공정`의 금속 온도가 연동됩니다. 녹는점(액상선)이 아니라 "
                            "점도·표면장력·용탕 생성량을 계산할 때 쓰는 온도입니다.")
        _unlink_ui("t2_tmelt")
        lo_th = _num("이탈모드 하한 We", 0.5, 20.0, 4.0, "t2_lo", 0.5)
        hi_th = _num("이탈모드 상한 We", 1.0, 50.0, 12.0, "t2_hi", 0.5)
        taper_q = _num("테이퍼 지수 q (집속 강도)", 0.0, 1.0, 0.5, "t2_q", 0.05)

    T_melt2_K = T_melt2 + 273.15
    m_dot = _CHAIN["m_dot"]        # 1 공정·2탭 입력으로 미리 계산한 값과 같은 값
    v_fall = math.sqrt(2.0 * 9.81 * fall_h / 1000.0)
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
    m4.metric("이탈 모드", i18n.tr(mode))
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


    st.divider()
    st.subheader("2(b). 코일 형상 — 봉 팁 콘·코일 단면과 가열 계산")
    st.write("봉은 위에서 아래로 공급되고, 아래 끝에 콘(테이퍼) 팁이 있습니다. "
             "고주파 전류는 표피 효과로 봉 표면층에만 열을 넣고, 열은 전도로 안쪽으로 퍼집니다. "
             "코일이 봉 단면을 따라 같이 좁아지면 같은 출력이 팁 근처의 작은 단면에 집중되어 "
             "팁이 더 뜨거워집니다. 봉 팁 콘의 크기와 코일의 내경·깊이·간극·축방향 위치를 "
             "아래에서 모두 조절할 수 있습니다.")
    rod_d_h = rod_d
    feed_h = feed
    P_coil_h = P_coil
    eff_h = eff
    turns_h = turns
    c1, c2, c3 = st.columns(3)
    with c1:
        cone_h = _num("봉 팁 콘 높이 (mm)", 0.0, 300.0, 40.0, "g_cone", 5.0,
                      help="0이면 콘 없이 직선 팁입니다.")
        tip_d = _num("봉 팁 지름 (mm)", 0.0, 100.0, 1.0, "g_tip", 1.0,
                     help="콘 끝의 지름. 0이면 뾰족한 팁(절단 없음), 0보다 크면 그 지름으로 잘린 절두 원뿔입니다.")
        rod_len = _num("봉 길이 (mm)", 20.0, 400.0, 100.0, "g_rodlen", 5.0,
                       help="팁 끝부터 봉 상단까지의 길이입니다. 코일 위치(팁 기준)와 이 길이로 "
                            "그림에 보이는 봉 구간이 정해집니다.")
        fall_h = _num("팁→노즐(가스 영역) 낙하 높이 (mm)", 0.0, 1000.0, 200.0, "fall_mm_coil", 1.0, link="fall_mm",
                      help="팁 끝에서 가스 제트가 모이는 지점(노즐 보어)까지의 거리입니다. 이 거리 동안 용탕류가 "
                           "가속되며 가늘어지고, 모세관 불안정성과 경합합니다. "
                           "2(a) 탭의 낙하 높이와 같은 값입니다.")
        gas_acc = _num("가스·압력차 추가 가속 (m/s²)", 0.0, 5000.0, 0.0, "g_gasacc", 10.0,
                       help="중력 외에 용탕류를 잡아늘리는 가속도입니다. 가스 항력과 챔버 간 압력차 흡입을 "
                            "합친 값으로, 0이면 중력만으로 떨어진다고 봅니다. "
                            "가스 제트가 강하면 수백 m/s²까지 커집니다.")
        coil_shape = _sel(
            "코일 형상",
            ["봉 형상 따라가기 (콘 밀착)", "직선", "원뿔 (선형 테이퍼)", "곡선 테이퍼 (지수)"],
            "g_shape")
        st.caption("‘봉 형상 따라가기’는 코일 내경 = 봉 반경 + 간극으로, 콘 구간에서 코일도 함께 좁아집니다.")
    with c2:
        coil_start = _num("코일 시작 위치 (팁 기준, mm)", -300.0, 300.0, 90.0, "g_cstart", 5.0,
                          help="봉 팁 끝단을 0으로 둔 위치입니다. +는 팁 위, −는 팁 아래"
                               "(금속보다 더 아래)까지 가능합니다.")
        coil_end = _num("코일 끝 위치 (팁 기준, mm)", -300.0, 300.0, -10.0, "g_cend", 5.0,
                        help="코일 마지막 턴의 위치. −로 두면 코일이 금속 팁보다 아래로 내려갑니다 "
                             "(기본 −10 mm = 팁 아래로 한 턴 더).")
        crop_top = _num("위쪽 잘라내기 (봉 상단에서, mm)", 0.0, 300.0, 0.0, "g_crop", 5.0,
                        help="그림에서 봉 상단부터 이만큼 잘라냅니다. 0이면 봉 전체가 보입니다.")
        coil_gap = _num("코일–봉 간극 (mm)", 1.0, 50.0, 20.0, "g_gap", 1.0,
                        help="코일 내면과 봉 표면 사이 거리. '봉 형상 따라가기'에서는 코일 내경을 "
                             "봉 지름 + 간극 2배로 잡고, 다른 형상에서도 최소 간극으로 적용됩니다.")
        couple_mode = _sel("코일 결합 모델",
                           ["반경비² (기존)", "간극 기준 (신규)", "자계 강화 (신규)"],
                           "g_couple",
                           help="결합 모델은 셋 중 하나만 선택합니다 (동시에 적용하지 않음). "
                                "반경비²는 결합을 (봉 반경 / 코일 반경)² 으로 봅니다 — 가는 팁에서는 "
                                "결합이 급격히 약해져 꼭지점이 덜 녹습니다. "
                                "간극 기준은 원주 2πR 에 간극 효율 1/(1+(간극/코일 반경)²) 을 곱해, "
                                "표면적이 있는 만큼은 가열되도록 봅니다. "
                                "자계 강화는 단위 길이당 흡수 전력을 원주 × 자계² 으로 봅니다 "
                                "(자계 ∝ 1/코일 반경) — 코일이 좁아질수록 표면 가열이 세집니다.")
        axial_on = st.checkbox(
            "축방향 전도 포함", key="g_axial", value=False,
            help="축방향 열전도를 에너지 수지에 추가합니다. 봉을 따라 열이 퍼져 코일 위쪽 찬 봉이 "
                 "예열되지만, 팁 온도는 용융 구간에 묶여 거의 변하지 않습니다. 계산이 다소 느려집니다.")
        compare_on = st.checkbox(
            "기준과 비교", key="g_compare", value=False,
            help="왼쪽은 기준(반경비², 축방향 전도 OFF), 오른쪽은 현재 선택(결합 모델 + 축방향 전도)을 "
                 "나란히 표시합니다.")
        sect_h = _sel("코일 단면 형상", ["원형", "직사각형"], "g_sect",
                      help="실제 유도 코일은 보통 원형 단면(동관·동선)입니다. "
                           "단면 형상과 무관하게 코일 위치·출력 계산은 동일합니다.")
        wire_d = _num("코일선 지름 (mm)", 1.0, 30.0, 6.0, "g_wire", 0.5,
                      help="원형 단면의 지름입니다.")
        if sect_h == "직사각형":
            wire_w = _num("코일선 폭 (mm, 반경방향)", 1.0, 30.0, 8.0, "g_ww", 0.5)
            wire_h = _num("코일선 두께 (mm, 축방향)", 1.0, 30.0, 6.0, "g_wh", 0.5)
        else:
            wire_w = wire_h = wire_d
    with c3:
        if coil_shape == "봉 형상 따라가기 (콘 밀착)":
            coil_top_h = rod_d_h + 2.0 * coil_gap
            coil_bot_h = coil_top_h
            shape_p = 1.0
            st.caption(f"코일 내경은 봉 지름 + 간극 2배 = {coil_top_h:.0f} mm 로 자동 결정됩니다.")
        else:
            coil_top_h = _num("코일 상부 내경 (mm)", 20.0, 200.0, 80.0, "g_top", 1.0)
            if coil_shape == "원뿔 (선형 테이퍼)":
                coil_bot_h = _num("코일 하부 내경 (mm)", 20.0, 200.0, 60.0, "g_bot", 1.0)
                shape_p = 1.0
            elif coil_shape == "곡선 테이퍼 (지수)":
                coil_bot_h = _num("코일 하부 내경 (mm)", 20.0, 200.0, 60.0, "g_bot", 1.0)
                shape_p = _num("테이퍼 지수 p", 0.2, 3.0, 2.0, "g_shape_p", 0.1,
                               help="p > 1: 아래쪽에서 급격히 좁아짐(팁 집중형), "
                                    "p < 1: 위쪽에서 급격히 좁아짐, p = 1: 원뿔")
            else:
                coil_bot_h = coil_top_h
                shape_p = 1.0
        freq = _num("주파수 (kHz)", 1.0, 500.0, 30.0, "g_freq", 1.0)
        T_feed_h = _num("봉 공급 온도 (°C)", 0.0, 500.0, 25.0, "g_tfeed", 5.0)

    R = rod_d_h / 2000.0
    r_tip = min(max(tip_d, 0.0) / 2000.0, R)
    gap_r = coil_gap / 1000.0
    # 코일 위치 기준은 봉 팁(아래): +는 팁 위, −는 팁 아래
    c_start_m = coil_start / 1000.0
    c_end_m = coil_end / 1000.0
    H = max(abs(coil_start - coil_end), 1.0) / 1000.0     # 코일 축방향 길이
    L = max(rod_len / 1000.0, c_start_m + 1e-3)           # 봉 길이 = 팁 깊이 (입력값)
    shank_m = max(L - max(c_start_m, 0.0), 0.0)           # 코일 위 봉 길이(표시·설명용)
    shank = shank_m * 1000.0
    if c_start_m > L + 1e-9:
        st.warning("코일 시작 위치가 봉 상단보다 위입니다 — 봉 길이를 늘리거나 코일을 내리세요.")
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

    def solve_heat(rc_func, couple="ratio", axial=False):
        """코일 반경 함수 → 봉 단면 온도장 (Nz x Nr).

        couple="ratio": 결합 ∝ (봉 반경 / 코일 반경)²  — 기존 방식
        couple="gap":   결합 ∝ 원주 2πR × 1/(1 + (간극/코일 반경)²) — 간극 기준
        couple="field": 결합 ∝ 봉 반경 / 코일 반경² — 자계 강화 (원주 × 자계², 자계 ∝ 1/코일 반경)
        axial=True면 축방향 열전도를 더한 음함수 풀이를 씁니다 (기본값은 전도 없는 행진 풀이).
        """
        w2 = np.zeros(Nz)
        for i, zz in enumerate(z):
            if z1 <= zz <= z2:
                rc = max(rc_func(zz), Rz[i] * 1.02)
                if couple == "gap":
                    gap_i = max(rc - Rz[i], 1e-6)
                    w2[i] = (2.0 * math.pi * Rz[i]) / (1.0 + (gap_i / rc) ** 2)
                elif couple == "field":
                    w2[i] = Rz[i] / rc ** 2
                else:
                    w2[i] = (Rz[i] / rc) ** 2     # 가까운 코일일수록 결합이 세짐
        w2 = w2 * ripple
        s = w2.sum()
        qp = P_rod * w2 / (s * dz) if s > 0 else np.zeros(Nz)
        if axial:
            Tax = ph.rod_descent_temperature_axial(
                z, qp, feed_h / 1000.0, alloy["rho_melt"], alloy["cp"],
                T_feed_h + 273.15, alloy["T_liquidus"], alloy["Lf"], Rz, k_th)
        else:
            Tax = ph.rod_descent_temperature_var(z, qp, feed_h / 1000.0,
                                                 alloy["rho_melt"], alloy["cp"],
                                                 T_feed_h + 273.15, alloy["T_liquidus"],
                                                 alloy["Lf"], Rz)
        Tg, _ = ph.radial_temperature_field_var(Tax, qp, Rz, delta, k_th, Nr=33)
        return Tg

    couple_key = {"반경비² (기존)": "ratio",
                  "간극 기준 (신규)": "gap",
                  "자계 강화 (신규)": "field"}.get(couple_mode, "ratio")
    Tg = solve_heat(coil_radius, couple_key, axial=axial_on)
    r_sc = coil_radius(z1)           # 같은 상부 내경의 직선 코일 기준값
    Tg_s = solve_heat(lambda zz: r_sc, couple_key, axial=axial_on)
    Tg_alt = solve_heat(coil_radius, "ratio", axial=False)   # 기준: 반경비², 전도 OFF
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
    _alt_surf_C = Tg_alt[:, -1] - 273.15
    alt_tip_C = float(_alt_surf_C[-1])
    alt_melt_len = melt_len_from_tip(_alt_surf_C)
    if tip_C > T_feed_h:
        P_min = P_coil_h * (T_liq_C - T_feed_h) / (tip_C - T_feed_h)
    else:
        P_min = float("inf")
    melt_len_s = melt_len_from_tip(Tg_s[:, -1] - 273.15)
    tip_s_C = Tg_s[-1, -1] - 273.15
    alpha = k_th / (alloy["rho_melt"] * alloy["cp"])
    t_res = H / (feed_h / 1000.0)
    t_diff = R ** 2 / alpha

    # ---- 팁 이탈 모드 v2 (낙하-신장 모델) — 팁을 노즐 출구로 보던 v1 We 판정 대체
    # v1은 용융량을 팁 면적으로 나눈 속도(= 노즐 출구 속도)로 We를 계산했지만,
    # 실제 봉 끝은 노즐이 아니라 용탕이 고였다 떨어지는 펜던트 넥이다.
    # v2: 넥 형성(질량수지 + 모세관 속도) → 낙하 가속·신장(중력 + 가스 + ΔP) → 가스 영역 도달 시 연속 여부.
    T_melt_K = max(tip_C, T_liq_C) + 273.15
    m_pow = ph.melt_rate_from_power(P_coil_h, eff_h, alloy, T_melt_K)      # kg/s
    m_feed = alloy["rho_melt"] * math.pi * R ** 2 * (feed_h / 1000.0)       # kg/s
    m_dot_melt = min(m_pow, m_feed) if m_feed > 0 else m_pow
    sigma_melt = ph.melt_surface_tension(alloy, T_melt_K)
    det0 = ph.stream_detachment(m_dot_melt, alloy["rho_melt"], sigma_melt,
                                r_tip, fall_h / 1000.0, 9.81 + gas_acc)
    # 보어 흡입 (3탭 값에서 자동 계산): 용탕이 보어를 막을수록 가스 통로가 좁아져
    # 가스가 빨라지고 흡입이 커지는 벤투리 피드백 + 챔버 압력차. 흡입은 낙하 말단에서
    # 작용하므로 낙하 시간은 그대로 두고 보어 입구 속도만 높이고 류는 가늘어진다.
    _ss = st.session_state
    _D_bore = float(_ss.get("t3_bore", 18.0)) / 1000.0
    _dP_ch = float(_ss.get("t3_dp", 0.5)) * 1e5
    _Pc = float(_ss.get("t3_pc", 1.5)) * 1e5
    _rho_gas = _Pc / (R_gas * 300.0) if R_gas > 0 else 0.0
    _m_gas = float(_CHAIN.get("m_gas", 0.0)) / 60.0
    suc = ph.bore_suction(det0["d_gas"], _D_bore, _m_gas, _rho_gas,
                          alloy["rho_melt"], _dP_ch)
    det = ph.stream_detachment(m_dot_melt, alloy["rho_melt"], sigma_melt,
                               r_tip, fall_h / 1000.0, 9.81 + gas_acc,
                               v_boost=suc["v_boost"])
    mode_m = det["mode"]
    mode_txt_m = det["explanation"]
    We_tip_m = det["We_neck"]      # 하위 표시 호환용: 넥 Weber 수
    d_exit_m = det["d_neck"]       # 그림용 류 직경: 분리 직후 넥 지름
    v_exit = det["v_cap"]          # 분리 직후 속도(모세관 속도 규모)
    d_gas_m = det["d_gas"]         # 가스 영역 도달 시 류 직경
    v_gas_m = det["v_gas"]         # 가스 영역 도달 시 속도
    t_fall_m = det["t_fall"]       # 낙하 시간
    t_break_m = det["t_break"]     # 모세관 붕괴 시간 규모
    tate_m = det["tate_d"]         # 펜던트 한 방울 상당 지름
    growth_m = det["growth"]       # 낙하 중 모세관 성장 누적값 (신장 반영)
    growth_crit_m = det["growth_crit"]  # 임계값 0.34*C_break
    stretch_m = det["stretch_ratio"]    # 가스 영역 신장률/오그라듦 속도

    # ---- 표면막-실 (film-thread) — 표면만 녹고 속은 고체인 경우, 막이 모여 가는 실이 된다
    # v2는 뚱뚱한 캡에서 떨어지는 줄기를 보지만, 막-실은 표면막의 수렴을 본다.
    # 막 판정: 팁 표면 ≥ 액상선 AND 팁 중심 < 고상선. 실 판정: v2와 같은 신장-인식 G 적분 (< 10.2).
    T_sol_C = float(alloy["T_solidus"] - 273.15)
    center_tip_C = float(Tg[-1, 0] - 273.15)
    film_on = bool(tip_molten and tip_C >= T_liq_C and center_tip_C < T_sol_C)
    film_res = None
    film_thread_on = False
    if film_on and melt_len > 0 and m_dot_melt > 0:
        film_res = ph.film_thread(m_dot_melt, alloy["rho_melt"], sigma_melt,
                                  melt_len / 1000.0, fall_h / 1000.0, 9.81 + gas_acc,
                                  _D_bore, _m_gas, _rho_gas, _dP_ch)
        film_thread_on = film_res["mode"] == "thread"

    # 코일 형상을 2 봉·코일 탭의 표시용으로 저장하고(다음 실행에서 반영),
    # 팁 표면 온도를 복사열 탭으로 연동합니다.
    # 코일 길이만 2탭 표시용으로 저장합니다. g_top/g_bot은 위젯 키라 여기서 다시 쓰면
    # (위젯이 이미 만들어졌을 때) Streamlit 오류가 나므로 건드리지 않습니다.
    st.session_state["g_len"] = float(_clamp(H * 1000.0, 10.0, 500.0))
    _push("rad_thot", tip_C, 100.0, 2500.0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("표피 깊이", f"{delta * 1000:.2f} mm")
    m2.metric("팁 표면 온도", f"{tip_C:.0f} °C")
    m3.metric("용융 캡 길이", f"{melt_len:.0f} mm")
    m4.metric("용탕 생성 임계 출력 (근사)", f"{P_min:.1f} kW" if P_min != float("inf") else "—")
    st.caption(f"녹는점(액상선) {T_liq_C:.0f} °C · 팁 표면 {tip_C:.0f} °C → 여유 "
               f"{tip_C - T_liq_C:+.0f} °C — 팁 표면이 액상선 이상이면 용탕이 생깁니다.")
    tip_label = "뾰족(Ø0)" if r_tip <= 1e-9 else f"Ø{r_tip * 2000:.1f} mm"
    st.caption(f"형상: 봉 Ø{rod_d_h:.0f} mm → 콘 {cone_h:.0f} mm 구간에서 팁 {tip_label}, "
               f"코일 {coil_shape}·{sect_h} 단면 {wire_w:.1f}×{wire_h:.1f} mm·"
               f"길이 {H * 1000:.0f} mm·{turns_h}턴, "
               f"코일은 팁 기준 {coil_start:+.0f} mm ~ {coil_end:+.0f} mm (+위/−아래). "
               f"봉 길이 {L * 1000:.0f} mm, 코일 상단은 봉 위에서 {shank:.0f} mm 내려온 지점입니다.")
    _cur_cap = (i18n.tr(couple_mode)
                + (f" + {i18n.tr('축방향 전도')}" if axial_on else "")
                + f": {i18n.tr('팁 표면 ')}{tip_C:.0f} °C, "
                + f"{i18n.tr('용융 캡 ')}{melt_len:.0f} mm")
    if couple_key == "ratio" and not axial_on:
        st.caption(i18n.tr("결합 모델 비교 — ") + _cur_cap)
    else:
        st.caption(i18n.tr("결합 모델 비교 — ") + _cur_cap + "  |  "
                   + i18n.tr("반경비² (기존)") + f" ({i18n.tr('기준')}): "
                   + f"{i18n.tr('팁 표면 ')}{alt_tip_C:.0f} °C, "
                   + f"{i18n.tr('용융 캡 ')}{alt_melt_len:.0f} mm")
    if tip_molten:
        st.success(f"팁 표면이 액상선 이상입니다. 용탕 생성 가능 — 이탈 모드: {mode_m} "
                   f"(넥 Weber 수 {We_tip_m:.1f}, 넥 지름 {d_exit_m * 1000:.2f} mm → "
                   f"가스 영역 Ø{d_gas_m * 1000:.2f} mm, 낙하 {t_fall_m * 1000:.0f} ms / "
                   f"붕괴 {t_break_m * 1000:.0f} ms, 성장 G {growth_m:.1f} / 임계 {growth_crit_m:.1f}, "
                   f"신장률/오그라듦 {stretch_m:.2f}, 펜던트 한 방울 Ø{tate_m * 1000:.1f} mm, "
                   f"용탕량 {m_dot_melt * 60:.2f} kg/min)")
        st.info(mode_txt_m)
        st.caption(i18n.tr(f"보어 흡입 (3탭 보어 Ø{_D_bore * 1000:.0f} mm, 챔버 ΔP "
                           f"{float(_ss.get('t3_dp', 0.5)):.2f} bar, 가스 {_m_gas * 60:.1f} kg/min): "
                           f"벤투리 ΔP {suc['dP_venturi'] / 1e5:.2f} bar → "
                           f"보어 입구 속도 +{suc['v_boost']:.1f} m/s, "
                           f"보어 입구 Ø{d_gas_m * 1000:.2f} mm. "
                           f"판정에는 이 보어 흡입 가속이 포함되어 있습니다."))
        if film_on and film_res is not None:
            if film_thread_on:
                st.success(f"표면막-실: 실 모드 — 표면 {tip_C:.0f} °C / 중심 {center_tip_C:.0f} °C (표면막) · "
                           f"팁 Ø{film_res['d_tip'] * 1000:.2f} mm → 보어 Ø{film_res['d_bore'] * 1000:.2f} mm · "
                           f"성장 G {film_res['growth']:.2f} / 임계 {film_res['growth_crit']:.1f}")
            else:
                st.warning(f"표면막이지만 낙하 중 끊어짐 — 표면 {tip_C:.0f} °C / 중심 {center_tip_C:.0f} °C (표면막) · "
                           f"팁 Ø{film_res['d_tip'] * 1000:.2f} mm → 보어 Ø{film_res['d_bore'] * 1000:.2f} mm · "
                           f"성장 G {film_res['growth']:.2f} / 임계 {film_res['growth_crit']:.1f}")
        else:
            st.caption(f"표면막 조건이 아닙니다 — 팁 표면 {tip_C:.0f} °C / 중심 {center_tip_C:.0f} °C "
                       f"(막: 표면 ≥ 액상선 {T_liq_C:.0f} °C 이고 중심 < 고상선 {T_sol_C:.0f} °C).")
        with st.expander("왜 물방울 모드 / 실 모드로 갈리나? (점도·표면장력 이야기)"):
            st.markdown(i18n.doc("droplet",
                "판정은 세 단계로 합니다 (v2 낙하-신장 모델).\n\n"
                "- **1단계 — 넥 형성.** 팁은 노즐이 아니라 용탕이 고였다 떨어지는 곳입니다. "
                "분리 직후 류 지름은 모세관 속도 `v_cap = √(σ/(ρ·R))` 에서의 질량수지로 정해집니다: "
                "`d_neck = √(4·m_dot/(π·ρ·v_cap))`. 넥 Weber 수 `We_neck = d_neck/R` 가 낮으면(< 2) "
                "연속 기둥이 유지되지 못하고 팁에서 바로 물방울로 떨어집니다.\n"
                "- **2단계 — 낙하 신장.** 류는 팁→가스 영역 거리 동안 중력 + 가스 항력 + 챔버 압력차 흡입으로 "
                "가속되고, 연속식 때문에 가늘어집니다 (`v = √(v_cap² + 2·a·H)`, `d ∝ 1/√v`). "
                "팁이 좁다고 자동으로 실이 되는 게 아닙니다 — 떨어지면서 늘어나는 과정이 핵심입니다.\n"
                "- **3단계 — 생존.** 가스 영역에 닿기 전에 모세관 불안정성(Rayleigh-Plateau)으로 끊기는지 봅니다. "
                "낙하 중 모세관 성장 누적값 `G = ∫ωdt − ln(v_gas/v_cap)` 이 임계 `0.34·C_break ≈ 10.2` 에 "
                "도달하면 도중에 물방울이 됩니다. 당김(신장률)이 오그라듦 속도보다 크면 성장이 상쇄되어 "
                "실이 유지됩니다 (치즈 늘리기 효과).\n"
                "- **녹았는지와는 별개입니다.** 팁이 액상선을 넘어 완전히 녹아도, 넥이 유지되지 않거나 "
                "낙하 중 끊기면 물방울 모드입니다.\n"
                "- 실 모드로 가려면: 용탕량↑(출력·공급속도↑), 낙하 거리↓, 가스·압력차 가속↑, 과열↑(σ↓).\n"
                "- **보어 흡입.** 용탕이 보어를 막을수록 가스 통로가 좁아져 가스가 빨라지고 흡입이 커집니다 "
                "(벤투리 피드백: 용탕이 내려갈 때 흡입이 더 강해짐). 흡입은 보어 진입과 미립화에는 도움이 되지만, "
                "보어 입구 류를 가늘게 만들지만 낙하 말단에서 작용하므로 성장 누적값 G는 바꾸지 않아 낙하 생존에는 중립입니다.\n"
                "- 점도는 `Oh = μ/√(ρ·σ·d)` 로 영향을 줍니다. 점성이 크면 경계가 물방울 쪽으로 넓어집니다. "
                "다만 mm급이면 Oh ≈ 0.002로 영향이 1 % 미만이고, 마이크로 오리피스·고점도 용탕에서 "
                "중요해집니다 (현재 판정식은 넥 We와 낙하 시간만 사용 — 한계).\n"
                "- v2의 임계값(넥 We 2/4, 붕괴 계수 30)은 문헌 규모에서 온 휴리스틱으로, "
                "실제 장비 기록으로 보정해야 합니다."))

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
    zcrop = crop_m                               # 봉 상단에서 이만큼 자름 (0 = 봉 전체)
    if turns_h > 0:                              # 첫 턴보다 10 mm 위까지는 데이터도 그립니다
        zcrop = min(zcrop, z1 + 0.5 * (H / turns_h) - 0.010)
    zcrop = max(zcrop, 0.0)
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
    turn_y_mm = [(z1 + (i + 0.5) * (H / turns_h)) * 1000.0
                 for i in range(int(turns_h))] if turns_h > 0 else []
    if turn_y_mm:                                  # 위쪽 코일 위치보다 10 mm 더 보이게
        top_mm = max(0.0, min(top_mm, min(turn_y_mm) - 10.0))
    if wire_h > pitch_mm + 1e-9:
        st.warning(f"코일선 두께({wire_h:.1f} mm)가 턴 간격({pitch_mm:.1f} mm)보다 커서 "
                   "그림에서 턴이 겹칩니다. 선재 치수를 줄이거나 턴 수를 늘리세요.")
    shapes = []
    for yc in turn_y_mm:
        rc = clear_radius(yc / 1000.0) * 1000.0
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
        y_low = max(bottom_mm - 3.0, y_tip_mm + 6.0)
        if film_on and film_res is not None:
            # 막-실: 계산된 실 지름 그대로(실제 mm) 그린 가늘어지는 실. 조건마다 두께가 다르다.
            _a_film = 9.81 + gas_acc
            _v0_f = film_res["v0"]
            _d0_f = film_res["d_tip"] * 1000.0
            _pts = []
            for _s in range(9):
                _yy = y_tip_mm + (y_low - y_tip_mm) * _s / 8.0
                _vv = math.sqrt(_v0_f ** 2 + 2 * _a_film * ((_yy - y_tip_mm) / 1000.0))
                _dd = _d0_f * math.sqrt(_v0_f / _vv) if _vv > 0 else _d0_f
                _pts.append((_dd / 2.0, _yy))
            _path = "M " + " L ".join(f"{-hw:.3f} {yy:.2f}" for hw, yy in _pts)
            _path += " L " + " L ".join(f"{hw:.3f} {yy:.2f}" for hw, yy in reversed(_pts)) + " Z"
            shapes.append(dict(type="path", layer="above", path=_path,
                               line=dict(color="#0d47a1", width=0.5),
                               fillcolor="#1e88e5"))
            if not film_thread_on:
                _rd = max(_pts[-1][0] * 1.8, 1.7)
                shapes.append(dict(type="circle", layer="above",
                                   x0=-_rd, x1=_rd,
                                   y0=y_low + 1.5 - _rd, y1=y_low + 1.5 + _rd,
                                   line=dict(color="#0d47a1", width=0.5),
                                   fillcolor="#1e88e5"))
            anno_metal = ((f"표면막-실 (G {film_res['growth']:.1f}, "
                           f"팁 Ø{_d0_f:.2f} → 보어 Ø{film_res['d_bore'] * 1000:.2f} mm)")
                          if film_thread_on else
                          (f"표면막-실 끊어짐 (G {film_res['growth']:.1f}, "
                           f"팁 Ø{_d0_f:.2f} → 보어 Ø{film_res['d_bore'] * 1000:.2f} mm)"))
        else:
            d_met_mm = max(d_exit_m * 1000.0, 1.2)
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
    xmax = max(float(rc_curve.max()), float(Rk.max())) + 10.0   # 코일 바깥 10 mm 여유
    for _zz in (z_start, z_end):
        shapes.append(dict(type="line", layer="above", xref="paper", yref="y",
                           x0=0.0, x1=1.0, y0=_zz * 1000.0, y1=_zz * 1000.0,
                           line=dict(color="#8a6d00", width=1, dash="dash")))

    fig = go.Figure()
    fig.add_trace(go.Heatmap(
        x=x_mm, y=zk, z=Zplot, colorscale="Inferno", connectgaps=False,
        hoverongaps=False,
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
                customdata=Tk[molten, -1],
                hovertemplate=i18n.tr("액상선 이상<br>깊이 %{y:.1f} mm"
                                      "<br>표면 온도 %{customdata:.0f} °C<extra></extra>"),
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
    for i, yc in enumerate(turn_y_mm):             # 1턴 … N턴 번호
        rc = clear_radius(yc / 1000.0) * 1000.0
        anno.append(dict(x=rc + wire_w * 0.9, y=yc, xref="x", yref="y",
                         text=str(i + 1), showarrow=False, xanchor="left",
                         font=dict(color="#8a6d00", size=9)))
    if tip_molten:
        _anno_txt = anno_metal if (film_on and film_res is not None) else \
            f"{anno_metal} (넥 We {We_tip_m:.1f}, 가스 영역 Ø{d_gas_m * 1000:.2f} mm)"
        _anno_col = "#0d47a1" if (film_on and film_res is not None) else "#cf1d1d"
        anno.append(dict(x=0.015, y=y_tip_mm + 5.0, xref="paper", yref="y",
                         text=i18n.tr(_anno_txt),
                         showarrow=False, xanchor="left", yanchor="top",
                         font=dict(color=_anno_col, size=10),
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
    st.caption(f"노란 원 {len(turn_y_mm)}개 = 코일 {int(turns_h)}턴 "
               f"(턴 간격 {pitch_mm:.1f} mm). 노란 점선은 코일 내경 경로입니다.")

    if tip_molten and film_on and film_res is not None:
        # 막-실 형상도: 위쪽은 봉 표면의 용융막(위쪽 직경), 아래쪽은 낙하 실(도착 직경).
        # 파란 막 두께는 모식(실제 막 두께는 모델에 없음). 지름 수치는 계산값.
        # 위쪽(봉)은 실제 축척, 아래쪽(실)은 확대 축척이라 두 패널의 가로 축척이 다르다.
        from plotly.subplots import make_subplots
        _H_f = float(fall_h)
        _v0_f = film_res["v0"]
        _d0_f = film_res["d_tip"] * 1000.0
        _d_grav_f = film_res["d_grav"] * 1000.0
        _d_bore_f = film_res["d_bore"] * 1000.0
        _a_film = 9.81 + gas_acc
        _tip_depth = float(L * 1000.0)
        _melt_start_depth = _tip_depth - float(melt_len)
        _z_film = np.linspace(_melt_start_depth / 1000.0, L, 40)
        _r_film = np.array([rod_radius(zz) for zz in _z_film]) * 1000.0
        _dep_film = _z_film * 1000.0
        _upper_d = 2.0 * float(_r_film[0])
        _band = 2.5  # 파란 막 두께 (모식, 보기용)
        _fig_f = make_subplots(rows=2, cols=1, vertical_spacing=0.03,
                               subplot_titles=(f"용융막 — 봉 표면 (위쪽 Ø{_upper_d:.1f} mm)",
                                               f"낙하 실 — 팁 Ø{_d0_f:.2f} → 보어 Ø{_d_bore_f:.2f} mm "
                                               f"(성장 G {film_res['growth']:.2f} / 임계 {film_res['growth_crit']:.1f})"
                                               + ("" if film_thread_on else " — 끊어짐")))
        # 위쪽: 봉(회색) + 표면막(파란 띠, 양쪽)
        _fig_f.add_trace(go.Scatter(x=np.concatenate([-_r_film[::-1], _r_film]),
                                    y=np.concatenate([_dep_film[::-1], _dep_film]),
                                    fill="toself", line=dict(color="#616161", width=1),
                                    fillcolor="#e0e0e0", hoverinfo="skip", showlegend=False),
                         row=1, col=1)
        for _sgn in (-1, 1):
            _xo = _sgn * (_r_film + _band)
            _xi = _sgn * _r_film
            _fig_f.add_trace(go.Scatter(x=np.concatenate([_xo[::-1], _xi]),
                                        y=np.concatenate([_dep_film[::-1], _dep_film]),
                                        fill="toself", line=dict(color="#0d47a1", width=1),
                                        fillcolor="#1e88e5", hoverinfo="skip", showlegend=False),
                             row=1, col=1)
        _fig_f.add_shape(type="line", x0=-_r_film[0], x1=_r_film[0],
                         y0=_dep_film[0], y1=_dep_film[0],
                         line=dict(color="#0d47a1", width=1.5), row=1, col=1)
        _fig_f.add_annotation(x=0.0, y=_dep_film[0], text=f"위쪽 Ø{_upper_d:.1f} mm",
                              showarrow=False, yshift=-16, font=dict(color="#0d47a1", size=11),
                              row=1, col=1)
        # 아래쪽: 낙하 실 (파란색)
        _zs = np.linspace(0.0, _H_f, 60)
        _vs = np.sqrt(_v0_f ** 2 + 2 * _a_film * (_zs / 1000.0))
        _ds = _d0_f * np.sqrt(_v0_f / _vs)
        _xs = np.concatenate([-_ds[::-1] / 2.0, _ds / 2.0])
        _ys = np.concatenate([_zs[::-1], _zs])
        _fig_f.add_trace(go.Scatter(x=_xs, y=_ys, fill="toself",
                                    line=dict(color="#0d47a1", width=1),
                                    fillcolor="#1e88e5", hoverinfo="skip", showlegend=False),
                         row=2, col=1)
        if film_thread_on:
            _fig_f.add_trace(go.Scatter(
                x=[-_d_bore_f / 2.0, _d_bore_f / 2.0, _d_bore_f / 2.0,
                   -_d_bore_f / 2.0, -_d_bore_f / 2.0],
                y=[_H_f, _H_f, _H_f + 8.0, _H_f + 8.0, _H_f],
                fill="toself", line=dict(color="#0d47a1", width=1),
                fillcolor="#64b5f6", hoverinfo="skip", showlegend=False),
                             row=2, col=1)
            _fig_f.add_shape(type="line", x0=-_d_bore_f / 2.0, x1=_d_bore_f / 2.0,
                             y0=_H_f + 8.0, y1=_H_f + 8.0,
                             line=dict(color="#0d47a1", width=1.5), row=2, col=1)
            _fig_f.add_annotation(x=0.0, y=_H_f + 8.0, text=f"도착 Ø{_d_bore_f:.2f} mm",
                                  showarrow=False, yshift=12, font=dict(color="#0d47a1", size=11),
                                  row=2, col=1)
        else:
            _rd_f = max(_d_grav_f * 0.9, 1.7)
            _fig_f.add_shape(type="circle", x0=-_rd_f, x1=_rd_f,
                             y0=_H_f + 4.0 - _rd_f, y1=_H_f + 4.0 + _rd_f,
                             line=dict(color="#0d47a1", width=0.5), fillcolor="#1e88e5",
                             row=2, col=1)
        _half = max(5.0, (_d0_f / 2.0) * 1.4)
        _xmax1 = float(_r_film[0] + _band + 5.0)
        _fig_f.update_layout(height=760, margin=dict(l=60, r=30, t=70, b=44),
                             title=dict(text="막-실 형상도 (파란 막 두께는 모식, 지름 수치는 계산값)",
                                        font=dict(size=13)),
                             plot_bgcolor="white")
        _fig_f.update_xaxes(title_text="반경 (mm)", range=[-_xmax1, _xmax1],
                            zeroline=False, showgrid=False, row=1, col=1)
        _fig_f.update_yaxes(title_text="깊이 (mm, 아래로 갈수록 팁)",
                            range=[_tip_depth, _melt_start_depth], showgrid=False, row=1, col=1)
        _fig_f.update_xaxes(title_text="반경 (mm, 확대)", range=[-_half, _half],
                            zeroline=False, showgrid=False, row=2, col=1)
        _fig_f.update_yaxes(title_text="팁에서 낙하 거리 (mm)",
                            range=[_H_f + 14.0, -4.0], showgrid=False, row=2, col=1)
        st.plotly_chart(_fig_f, width="stretch")
        st.caption(f"위쪽 직경 Ø{_upper_d:.1f} mm = 용융 시작 지점(깊이 {_melt_start_depth:.0f} mm)의 봉 지름. "
                   f"도착 직경 Ø{_d_bore_f:.2f} mm = 보어 도착 실 지름(흡입 포함). "
                   f"파란 막 두께는 실제 막 두께가 아니라 보기 위한 모식입니다. "
                   f"위쪽(봉)은 실제 축척, 아래쪽(실)은 확대 축척이라 두 패널의 가로 축척이 다릅니다. "
                   f"조건이 바뀌면 위쪽·도착 직경이 바뀌어 그림 모양이 달라집니다.")

    if compare_on:
        st.markdown(i18n.tr("**기준과 비교 — 같은 조건**"))
        _zmin = float(np.nanmin(Zplot))
        _zmax = float(np.nanmax(Zplot))
        _colA, _colB = st.columns(2)
        _cur_name = i18n.tr(couple_mode) + (f" + {i18n.tr('축방향 전도')}" if axial_on else "")
        for _col, _Tf, _nm in ((_colA, Tg_alt, "반경비² (기존)"),
                               (_colB, Tg, _cur_name)):
            _Tcc = _Tf[keep] - 273.15
            _Zc2 = np.full((len(zk), len(r_common)), np.nan)
            for _i2 in range(len(zk)):
                _pr = np.interp(r_common, xi * Rk[_i2], _Tcc[_i2], left=_Tcc[_i2][0])
                _pr[r_common > Rk[_i2] + 1e-9] = np.nan
                _Zc2[_i2] = _pr
            _Zp2 = np.concatenate([_Zc2[:, ::-1], _Zc2[:, 1:]], axis=1)
            _fc = go.Figure(go.Heatmap(
                x=x_mm, y=zk, z=_Zp2, colorscale="Inferno", zmin=_zmin, zmax=_zmax,
                hoverongaps=False,
                colorbar=dict(title="°C", len=0.68, thickness=12),
                hovertemplate=i18n.tr("반경 %{x:.1f} mm<br>깊이 %{y:.1f} mm"
                                      "<br>온도 %{z:.0f} °C<extra></extra>")))
            _fc.add_trace(go.Contour(
                x=x_mm, y=zk, z=_Zp2,
                contours=dict(type="constraint", operation=">", value=float(T_liq_C)),
                fillcolor="rgba(0,229,255,0.20)", line=dict(color="cyan", width=1.5),
                showscale=False, hoverinfo="skip", name=i18n.tr("액상 영역 (T ≥ 액상선)")))
            for _sgn in (-1, 1):
                _fc.add_trace(go.Scatter(x=_sgn * rc_curve, y=zc * 1000.0, mode="lines",
                                         line=dict(color="#e8c400", width=1, dash="dot"),
                                         hoverinfo="skip", showlegend=False))
            _fc.update_layout(
                height=430, margin=dict(l=54, r=56, t=40, b=40), plot_bgcolor="white",
                title=dict(text=i18n.tr(_nm), font=dict(size=12)),
                xaxis=dict(title=i18n.tr("반경 (mm)"), range=[-xmax, xmax]),
                yaxis=dict(title="", range=[bottom_mm, top_mm], scaleanchor="x",
                           scaleratio=1, constrain="domain"))
            _tipc = float(_Tf[-1, -1]) - 273.15
            _capc = melt_len_from_tip(_Tf[:, -1] - 273.15)
            with _col:
                st.plotly_chart(_fc, width="stretch")
                st.caption(f"{i18n.tr(_nm)} — {i18n.tr('팁 표면 ')}{_tipc:.0f} °C, "
                           f"{i18n.tr('용융 캡 ')}{_capc:.0f} mm")

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

    # ---- 2(c) 절단면 보기 (기준점을 팁에서 위로 옮겨가며)
    st.subheader("2(c). 절단면 보기 — 팁 기준 위치에서 XY / XZ / YZ")
    st.caption("기준점을 금속 팁(0 mm)에서 위로 옮겨가며 그 높이의 단면을 봅니다. "
               "계산은 축대칭(r, z) 모델이라 XZ·YZ 단면은 같게 나옵니다 "
               "(실제 나선 코일에서는 턴 위치 때문에 원주 방향으로 조금 달라질 수 있습니다).")
    st.caption("액상 영역은 액상선(등온선) 기준으로만 칠해집니다. 이 모델은 잠열과 용융 경계를 "
               "넣지 않아 표면 온도가 액상선보다 높게(과대평가) 나올 수 있습니다.")
    _Nr3 = Tg.shape[1]
    _xi3 = np.linspace(0.0, 1.0, _Nr3)
    _Tc3 = Tg - 273.15
    _zmm3 = z * 1000.0
    _Rmm3 = Rz * 1000.0
    _Lmm3 = float(_zmm3[-1])

    def _prof3(i3, r_mm3):
        """깊이 인덱스 i3에서 반경 r_mm3(mm)의 온도(°C)."""
        return np.interp(r_mm3, _xi3 * _Rmm3[i3], _Tc3[i3],
                         left=_Tc3[i3][0], right=_Tc3[i3][-1])

    def _liq_r3(i3):
        """그 높이에서 액상선에 도달하는 반경(mm). 용융 없으면 None."""
        rr = np.linspace(0.0, float(_Rmm3[i3]), 240)
        tt = _prof3(i3, rr)
        if tt[-1] >= T_liq_C:
            return float(rr[-1])
        if tt[0] < T_liq_C:
            return None
        below = np.where(tt < T_liq_C)[0]
        k = int(below[0])
        t0, t1 = tt[k - 1], tt[k]
        f = 0.0 if t1 == t0 else (T_liq_C - t0) / (t1 - t0)
        return float(rr[k - 1] + f * (rr[k] - rr[k - 1]))

    _c4, _c5 = st.columns([2, 1])
    with _c4:
        s3_plane = st.selectbox("절단면",
                                ["XY (축에 수직, 단면)", "XZ (축 포함, 세로)",
                                 "YZ (축 포함, 세로)"], key="s3_plane")
    with _c5:
        st.caption(f"봉 길이 {_Lmm3:.0f} mm (팁 기준)")
    s3_pos = st.slider("팁 기준 위치 (mm) — 0 = 팁 끝, 위로 갈수록 증가",
                       0.0, float(_Lmm3), 0.0, 1.0, key="s3_pos",
                       help="금속 끝(팁)을 0으로 두고 위로 올라가며 단면을 확인합니다. "
                            "코일 시작/끝 위치와 같은 기준입니다.")
    _z3 = _Lmm3 - float(s3_pos)                       # 봉 상단 기준 깊이(mm)
    _i3 = int(np.clip(np.abs(_zmm3 - _z3).argmin(), 0, len(_zmm3) - 1))
    _rl3 = _liq_r3(_i3)
    _m1, _m2, _m3, _m4 = st.columns(4)
    _m1.metric("표면 온도", f"{_Tc3[_i3][-1]:.0f} °C")
    _m2.metric("중심 온도", f"{_Tc3[_i3][0]:.0f} °C")
    _m3.metric("표면 − 액상선", f"{_Tc3[_i3][-1] - T_liq_C:+.0f} °C")
    _m4.metric("용융 반경 (액상선)",
               "—" if _rl3 is None else f"{_rl3:.1f} / {_Rmm3[_i3]:.1f} mm")
    st.caption(f"이 높이의 봉 반경 {_Rmm3[_i3]:.1f} mm · 코일 반경 "
               f"{clear_radius(z[_i3]) * 1000.0:.1f} mm (팁 기준 {s3_pos:.0f} mm)")

    _th3 = np.linspace(0.0, 2.0 * np.pi, 200)
    if s3_plane.startswith("XY"):
        _Rp = max(float(_Rmm3[_i3]), 0.2)
        _xs3 = np.linspace(-_Rp, _Rp, 121)
        _Xg, _Yg = np.meshgrid(_xs3, _xs3)
        _Rg = np.hypot(_Xg, _Yg)
        _Tm3 = np.where(_Rg <= _Rp, _prof3(_i3, _Rg), np.nan)
        fig3 = go.Figure(go.Heatmap(
            x=_xs3, y=_xs3, z=_Tm3, colorscale="Inferno", zsmooth="best",
            hoverongaps=False,
            colorbar=dict(title="°C", len=0.72, thickness=14),
            hovertemplate=i18n.tr("x %{x:.1f} mm<br>y %{y:.1f} mm<br>%{z:.0f} °C<extra></extra>")))
        _rc3 = clear_radius(z[_i3]) * 1000.0
        fig3.add_trace(go.Scatter(x=_rc3 * np.cos(_th3), y=_rc3 * np.sin(_th3),
                                  mode="lines", line=dict(color="#e8c400", dash="dot"),
                                  name=i18n.tr("코일"), hoverinfo="skip"))
        if _rl3 is not None and _rl3 > 0:
            fig3.add_trace(go.Scatter(x=_rl3 * np.cos(_th3), y=_rl3 * np.sin(_th3),
                                      mode="lines", line=dict(color="cyan", width=2),
                                      fill="toself", fillcolor="rgba(0,229,255,0.20)",
                                      name=i18n.tr("액상 영역 (T ≥ 액상선)"),
                                      hoverinfo="skip"))
        fig3.update_layout(
            height=470, margin=dict(l=64, r=30, t=48, b=48), plot_bgcolor="white",
            title=dict(text=i18n.tr(f"XY 단면 — 팁 기준 {s3_pos:.0f} mm "
                                    f"(봉 상단에서 {_z3:.0f} mm)"), font=dict(size=13)),
            xaxis=dict(title="x (mm)", scaleanchor="y", constrain="domain"),
            yaxis=dict(title="y (mm)"))
        st.plotly_chart(fig3, width="stretch")
    else:
        _hname = "x" if s3_plane.startswith("XZ") else "y"
        _hmax = float(np.max(_Rmm3)) * 1.15
        _hx = np.linspace(-_hmax, _hmax, 141)
        _Tm3 = np.empty((len(_zmm3), len(_hx)))
        for _k3 in range(len(_zmm3)):
            _row = _prof3(_k3, np.abs(_hx))
            _row[np.abs(_hx) > _Rmm3[_k3]] = np.nan
            _Tm3[_k3] = _row
        fig3 = go.Figure(go.Heatmap(
            x=_hx, y=_zmm3, z=_Tm3, colorscale="Inferno", zsmooth="best",
            hoverongaps=False,
            colorbar=dict(title="°C", len=0.72, thickness=14),
            hovertemplate=i18n.tr(f"{_hname} %{{x:.1f}} mm<br>깊이 %{{y:.1f}} mm"
                                  f"<br>%{{z:.0f}} °C<extra></extra>")))
        _Tmol = np.where(_Tm3 >= T_liq_C, _Tm3, np.nan)
        if np.isfinite(_Tmol).any():
            fig3.add_trace(go.Heatmap(
                x=_hx, y=_zmm3, z=_Tmol, hoverongaps=False, showscale=False,
                colorscale=[[0.0, "rgba(0,229,255,0.18)"], [1.0, "rgba(0,229,255,0.18)"]],
                hovertemplate=i18n.tr(f"{_hname} %{{x:.1f}} mm<br>깊이 %{{y:.1f}} mm"
                                      f"<br>%{{z:.0f}} °C<extra></extra>"),
                name=i18n.tr("액상 영역 (T ≥ 액상선)")))
        fig3.add_trace(go.Contour(
            x=_hx, y=_zmm3, z=_Tm3,
            contours=dict(type="constraint", operation=">", value=float(T_liq_C)),
            fillcolor="rgba(0,0,0,0)", line=dict(color="cyan", width=2),
            showscale=False, hoverinfo="skip",
            name=i18n.tr("액상선")))
        _inc = (_zmm3 >= z1 * 1000.0 - 1e-9) & (_zmm3 <= z2 * 1000.0 + 1e-9)
        _cz = _zmm3[_inc]
        _cx = np.array([clear_radius(zz) * 1000.0 for zz in z[_inc]])
        for _sgn, _show in ((-1, True), (1, False)):
            fig3.add_trace(go.Scatter(x=_sgn * _cx, y=_cz, mode="lines",
                                      line=dict(color="#e8c400", dash="dot", width=1),
                                      name=i18n.tr("코일"), showlegend=_show, hoverinfo="skip"))
        _ty = np.array([(z1 + (_i + 0.5) * (H / turns_h)) for _i in range(int(turns_h))])
        _ty = _ty[_ty <= z[-1] + 1e-9]
        if _ty.size:
            _tx = np.array([clear_radius(zz) * 1000.0 for zz in _ty])
            for _sgn, _show in ((-1, True), (1, False)):
                fig3.add_trace(go.Scatter(x=_sgn * _tx, y=_ty * 1000.0, mode="markers",
                                          marker=dict(color="#e8c400", size=8,
                                                      line=dict(color="black", width=0.6)),
                                          name=i18n.tr("코일 턴"), showlegend=_show,
                                          hoverinfo="skip"))
        fig3.add_trace(go.Scatter(x=[float(_hx.min()), float(_hx.max())],
                                  y=[_zmm3[_i3], _zmm3[_i3]], mode="lines",
                                  line=dict(color="#ff4d4d", width=1.5, dash="dash"),
                                  name=i18n.tr("기준 위치")))
        fig3.update_layout(
            height=520, margin=dict(l=64, r=30, t=48, b=48), plot_bgcolor="white",
            title=dict(text=i18n.tr(f"{_hname.upper()}Z 단면 — 기준 위치 팁 기준 "
                                    f"{s3_pos:.0f} mm"), font=dict(size=13)),
            xaxis=dict(title=f"{_hname} (mm)"),
            yaxis=dict(title=i18n.tr("깊이 (mm, 아래로 갈수록 팁)"), autorange="reversed"))
        st.plotly_chart(fig3, width="stretch")

    expl_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                             "cone-vs-straight-explainer.png")
    if os.path.exists(expl_path):
        st.image(expl_path,
                 caption="원뿔 vs 직선 코일 — 왜 원뿔이 팁을 더 뜨겁게 만드는가 "
                         "(실제 계산 결과, 316L·50kW·효율 0.6·공급 2.0mm/s)")

# ---------------------------------------------------------------- tab 3
with tab3:
    st.header("3. 노즐 — 상부→하부챔버 통과 중 분쇄")
    st.write("용탕은 노즐 중심 구멍을 타고 상부챔버에서 하부챔버로 이동하며, "
             "그 통과 구간에서 노즐 고압가스에 맞아 분쇄됩니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        bore_d = _num("노즐 보어 지름 (mm)", 0.5, 20.0, 18.0, "t3_bore", 0.1)
        if bore_d <= 16.0:
            st.warning("노즐 보어가 16mm 이하이면 막힘 위험이 있습니다. 16mm를 초과하는 값을 쓰세요 (기본값 18mm).")
        bore_len = _num("노즐 보어 길이 (mm)", 1.0, 50.0, 20.0, "t3_blen", 1.0)
        nozzle_type = _sel("가스 분사 형태", ["환형 슬릿", "개별 홀"], "t3_type")
        jet_angle = _num("가스 분사각 (° , 축 기준)", 0.0, 90.0, 30.0, "t3_angle", 1.0)
        if nozzle_type == "환형 슬릿":
            pitch_d = _num("슬릿 피치 지름 (mm)", 5.0, 100.0, 30.0, "t3_pitch", 1.0)
            slit_w = _num("슬릿 폭 (mm)", 0.1, 5.0, 0.5, "t3_slit", 0.05)
            gas_area3 = ph.annular_slit_area(pitch_d / 1000.0, slit_w / 1000.0) * 1e6
            coverage = 1.0
        else:
            pitch_d = _num("홀 피치 지름 (mm)", 5.0, 100.0, 30.0, "t3_pitch", 1.0)
            n_holes = _num("홀 개수", 1, 100, 12, "t3_holes", 1)
            hole_d = _num("홀 지름 (mm)", 0.2, 5.0, 1.5, "t3_hole", 0.1)
            gas_area3 = ph.holes_area(int(n_holes), hole_d / 1000.0) * 1e6
            coverage = ph.jet_coverage(int(n_holes), hole_d / 1000.0, pitch_d / 1000.0)
    with c2:
        P0 = _num("가스 공급압력 (bar) ", 1.0, 300.0, 35.0, "t3_p0", 1.0,
                  help="`1 공정`의 가스 공급압력이 연동됩니다.")
        _unlink_ui("t3_p0")
        Pc = _num("챔버 압력 (bar) ", 0.1, 10.0, 1.5, "t3_pc", 0.1,
                  help="`1 공정`의 챔버 압력이 연동됩니다.")
        _unlink_ui("t3_pc")
        dP = _num("상하부 압력차 (bar)", 0.0, 5.0, 0.5, "t3_dp", 0.05)
        bore_profile = _sel("보어 형상", ["직선 (초크, Mach 1)", "디 라발 (초음속)"],
                            "t3_profile")
        if bore_profile == "디 라발 (초음속)":
            exit_d = _num("디 라발 출구 지름 (mm)", 1.0, 100.0, 10.0, "t3_exit", 0.5)
    with c3:
        m_dot_in = _num("용탕 유량 (kg/min)", 0.1, 100.0, 2.0, "t3_meltflow", 0.1,
                        help="`2 봉·코일`에서 계산된 용탕 생성량이 연동됩니다.")
        _unlink_ui("t3_meltflow")
        v0 = _num("용탕 초기 속도 (m/s)", 0.0, 10.0, 0.5, "t3_v0", 0.1)
        Cd = _num("노즐 유량계수 Cd", 0.5, 1.0, 0.9, "t3_cd", 0.05)

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
        d_drop = _num("액적 직경 (µm)", 1.0, 500.0, 40.0, "t4_drop", 1.0)
        v_drop = _num("액적 비행 속도 (m/s)", 0.1, 50.0, 5.0, "t4_vdrop", 0.1)
        ch_h = _num("챔버 높이 (m)", 0.5, 5.0, 1.5, "t4_chh", 0.1)
    with c2:
        T_drop = _num("액적 초기 온도 (°C)", 1000.0, 2500.0, 1500.0, "t4_tdrop", 10.0,
                      help="`1 공정`의 금속 온도가 연동됩니다.")
        _unlink_ui("t4_tdrop")
        T_gas4 = _num("챔버 가스 온도 (°C)", 0.0, 500.0, 25.0, "t4_tgas", 5.0)
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
        D50_in = _num("분말 D50 (µm)", 1.0, 500.0, 39.5, "t4_d50", 1.0,
                      help="`1 공정`에서 계산된 D50이 연동됩니다.")
        _unlink_ui("t4_d50")
    with c4:
        t_ox = _num("산화층 두께 가정 (nm)", 0.0, 100.0, 5.0, "t4_ox", 0.5)
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
        sig_g_in = _num("입도분포 폭 σg", 1.2, 4.0, 2.0, "t4_sig", 0.1,
                        help="`1 공정`의 분포 폭이 연동됩니다.")
        _unlink_ui("t4_sig")
    with c6:
        fine_th = _num("미분 기준 (µm)", 1.0, 50.0, 10.0, "t4_fines", 1.0)
    fines = ph.lognormal_cdf(fine_th * 1e-6, D50_in * 1e-6, sig_g_in)
    st.write(f"미분(<{fine_th:.0f}µm) 분율: {fines * 100:.1f}%")
    good = sum([D50_in >= 20, fines < 0.2, shape_ok])
    rating = "양호" if good == 3 else ("보통" if good == 2 else "불량 가능")
    st.metric("유동성 등급 (휴리스틱)", i18n.tr(rating))
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
        y_dmin = _num("합격 하한 (µm)", 0.0, 500.0, 15.0, "t5_dmin", 1.0,
                      help="`1 공정`의 목표 입도 하한이 연동됩니다.")
        _unlink_ui("t5_dmin")
        y_dmax = _num("합격 상한 (µm)", 0.0, 500.0, 40.0, "t5_dmax", 1.0,
                      help="`1 공정`의 목표 입도 상한이 연동됩니다.")
        _unlink_ui("t5_dmax")
        y_melt = _num("용탕 유량 (kg/min, 수율 환산 기준)", 0.1, 100.0, 2.0,
                      "t5_melt", 0.05,
                      help="`2 봉·코일`의 용탕 생성량이 연동됩니다.")
        _unlink_ui("t5_melt")
    with yc2:
        y_d50 = _num("분포 D50 (µm)", 1.0, 500.0, 39.5, "t5_d50", 0.1,
                     help="`1 공정`에서 계산된 D50이 연동됩니다.")
        _unlink_ui("t5_d50")
        y_sig = _num("분포 폭 σg", 1.2, 4.0, 2.0, "t5_sig", 0.1,
                     help="`1 공정`의 분포 폭이 연동됩니다.")
        _unlink_ui("t5_sig")
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

# ---------------------------------------------------------------- 복사열
with tab_rad:
    st.header("복사열 — 주변(챔버 벽) 온도 변화")
    st.write("봉과 코일이 뜨거워지면 표면에서 복사로 주변 벽에 열을 보냅니다. 벽은 열용량 때문에 "
             "서서히 데워지고, 가스 대류와 외부 냉각·재복사로 열을 잃습니다. 고온부 온도·면적·복사율, "
             "벽 재질·두께·면적, 시간을 바꿔가며 **주변 온도가 시간에 따라** 어떻게 오르는지 봅니다.")
    c1, c2, c3 = st.columns(3)
    with c1:
        T_hot_C = _num("고온부(봉·코일) 표면 온도 (°C)", 100.0, 2500.0, 1500.0, "rad_thot", 10.0,
                       help="`2(b) 코일 형상`의 팁 표면 온도가 연동됩니다.")
        _unlink_ui("rad_thot")
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
        t_end = st.number_input("관찰 시간 (s)", 10.0, 7200.0, 1800.0, 10.0, key="r_tend")
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

**팁 이탈 모드(물방울 vs 실) — 왜 갈리나 (v2 낙하-신장 모델)**
- 판정은 세 단계입니다. **1단계 넥 형성:** 팁은 노즐이 아니라 용탕이 고였다 떨어지는 곳입니다. 분리 직후 류 지름은 모세관 속도 `v_cap = √(σ/(ρ·R))` 에서의 질량수지로 정해지고, 넥 Weber 수 `We_neck = d_neck/R` 가 2 미만이면 팁에서 바로 물방울로 떨어집니다.
- **2단계 낙하 신장:** 류는 팁→가스 영역 거리 동안 중력 + 가스 항력 + 챔버 압력차 흡입으로 가속되고 연속식 때문에 가늘어집니다. 팁이 좁다고 자동으로 실이 되는 게 아닙니다 — 떨어지면서 늘어나는 과정이 핵심입니다.
- **3단계 생존 (신장 반영):** 낙하 중 모세관 성장 누적값 `G = ∫ωdt − ln(v_gas/v_cap)` 이 임계 `0.34·C_break ≈ 10.2` 에 도달하면 가스 영역에 닿기 전에 끊겨 물방울이 됩니다. 당김(신장률)이 오그라듦 속도보다 크면 성장이 상쇄되어 실이 유지됩니다 (치즈 늘리기 효과). 보어 흡입은 낙하 말단에서 작용하므로 G를 바꾸지 않아 생존에는 중립입니다.
- **녹았는지 여부와는 별개**입니다. 팁이 액상선을 넘어 완전히 녹아도, 넥이 유지되지 않거나 낙하 중 끊기면 물방울 모드입니다.
- 실 모드로 가려면: 용탕량↑(출력·공급속도↑), 낙하 거리↓, 가스·압력차 가속↑, 과열↑(σ↓).
- **점도**는 `Oh = μ/√(ρ·σ·d)` 로 들어갑니다. 점성이 크면 경계가 물방울 쪽으로 넓어집니다. 다만 mm급이면 `Oh ≈ 0.002` 로 영향이 1 % 미만이고, 마이크로 오리피스나 고점도 용탕에서 중요해집니다. **현재 판정식은 넥 We와 낙하 시간만 사용합니다(한계).**
- σ는 온도가 오르면 줄어 We_neck이 커집니다 → 같은 조건이라도 과열이 크면 실 쪽으로 갑니다.

**복사열 탭**
- 고온부는 `q = ε·σ·A_hot·F·(T_hot⁴ − T_wall⁴)` 로 벽에 복사 열을 보냅니다.
- 벽은 열용량 `m·cp` 만큼 서서히 데워지고, 가스 대류(`h·A·(T−T_gas)`)와 외부 냉각·재복사로 열을 잃습니다.
- 시간 상수는 대략 `τ = m·cp/(4εσA·T³ + h·A)` 이고, ‘90 % 도달 시간’으로 확인합니다.
- 물 냉각 벽(h_out ↑)은 온도가 낮게 유지되고, 진공·단열이면 수백 도까지 오릅니다.

**핵심 식**
- Lubanska 상관식: D50/D = K·√[(νm/νg)·(1/We)·(1+M/A)], We는 용탕 밀도 기준
- 입도분포: 로그정규 분포 (σg 기본값 2.0)
- 가스: 초크(음속) 조건에서 음속 제트, 질량유량은 초크 유량식
- 팁 이탈 모드: 낙하-신장 모델(v2) — 임계값은 경험으로 보정 필요

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
