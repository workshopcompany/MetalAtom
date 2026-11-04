# -*- coding: utf-8 -*-
"""Bilingual (English default / Korean) UI layer for MetalAtom.

app.py is written with Korean literals. ``install(st)`` wraps the Streamlit
API so those literals are rendered through :func:`tr`, which maps them to
English while the language is "en" (the default).

* exact matches in ``EN`` are used for labels and full sentences
* f-strings (numbers already baked in) fall back to longest-first
  substitution from ``TERM``
* long markdown blocks go through :func:`doc` with an explicit key
"""

import hashlib
import sys

import streamlit as st

DEFAULT_LANG = "en"

EN = {
    # ------------------------------------------------------------ tabs / nav
    "1 공정": "1 Process",
    "2 봉·코일": "2 Rod & Coil",
    "3 노즐": "3 Nozzle",
    "4 분말 품질": "4 Powder Quality",
    "5 수율 계산": "5 Yield",
    "코일 가열 보기": "Coil Heating View",
    "복사열": "Radiation",
    "사용법·한계": "Usage & Limits",
    "공통 설정": "Common settings",
    "합금": "Alloy",
    "분무 가스": "Atomizing gas",
    "MetalAtom — EIGA 아토마이저 시뮬레이터": "MetalAtom — EIGA atomizer simulator",

    # ------------------------------------------------------------ tab 1
    "EIGA 금속분말 아토마이저 시뮬레이터 — 오픈소스 간이 모델. CFD가 아니라 규칙과 한계를 찾는 도구입니다. 모든 물성은 대표값이며, 본인 장비 데이터로 보정해서 쓰세요.":
        "EIGA metal powder atomizer simulator — an open-source reduced model. It is not CFD: "
        "it is a tool for finding rules and limits. All properties are representative values; "
        "calibrate them with your own equipment data.",
    "1. 공정부분 — 조건 조절에 따른 입도분포와 외관형상":
        "1. Process — size distribution and tip behaviour vs. conditions",
    "용탕 온도 (°C) ": "Melt temperature (°C)",
    "용탕류 직경 (mm)": "Melt stream diameter (mm)",
    "가스 공급압력 (bar) ": "Gas supply pressure (bar)",
    "챔버 압력 (bar) ": "Chamber pressure (bar)",
    "가스 온도 (K)": "Gas temperature (K)",
    "Lubanska 상수 K (장비 보정값)": "Lubanska constant K (equipment calibration)",
    "계산 GMR": "Computed GMR",
    "가스 제트 속도": "Gas jet velocity",
    "초크(음속) 상태": "Choked (sonic)",
    "아음속 상태": "Subsonic",
    "초음속 제트": "Supersonic jet",
    "가스 유량": "Gas flow",
    "분말 D50 (µm)": "Powder D50 (µm)",
    "입도분포 (로그정규 모델)": "Size distribution (log-normal model)",
    "분포 D50 (µm)": "Distribution D50 (µm)",
    "분포 폭 σg": "Spread σg",
    "입도분포 폭 σg": "Spread σg",
    "질량분율 (%)": "Mass fraction (%)",
    "누적 질량분율": "Cumulative mass fraction",
    "누적 질량분율 (이 크기 이하)": "Cumulative mass fraction (below this size)",
    "입자 직경 (µm)": "Particle diameter (µm)",
    "공정 윈도우 — 가스 압력 × 용탕 유량": "Operating window — gas pressure × melt flow",
    "가스 공급압력": "Gas supply pressure",
    "용탕 유량": "Melt flow",
    "D50 (µm) — 색이 진할수록 굵은 분말": "D50 (µm) — darker means coarser powder",
    "파라미터 스윕 — 규칙 찾기": "Parameter sweep — find the rules",
    "스윕 변수": "Sweep variable",
    "스윕 최소값": "Sweep minimum",
    "스윕 최대값": "Sweep maximum",
    "스윕 점 개수": "Sweep points",
    "주의: 가스 압력은 제트 속도가 아니라 가스 유량→GMR을 통해 입도에 작용합니다. 초크(음속) 상태에서는 속도가 포화되므로, 압력을 올려도 속도는 안 올라가고 유량만 늘어납니다. 그래서 압력 효과가 보이려면 GMR을 입력값이 아니라 가스 유량/용탕 유량으로 계산해야 합니다.":
        "Note: gas pressure does not act through jet velocity but through gas flow → GMR. "
        "Once choked (sonic), velocity saturates, so raising pressure only adds mass flow. "
        "That is why the pressure effect only appears when GMR is computed from gas flow / melt flow "
        "instead of being an input.",

    # ------------------------------------------------------------ tab 2
    "2(a). 봉·코일 — 용탕 생성과 팁 이탈 모드":
        "2(a). Rod & coil — melt generation and tip detachment mode",
    "봉 지름 (mm)": "Rod diameter (mm)",
    "봉 공급 속도 (mm/s)": "Rod feed rate (mm/s)",
    "봉 회전 속도 (rpm)": "Rod rotation (rpm)",
    "코일 출력 (kW)": "Coil power (kW)",
    "코일 효율": "Coil efficiency",
    "코일 감은 횟수": "Coil turns",
    "코일 길이 (mm)": "Coil length (mm)",
    "코일 상부 내경 (mm)": "Coil top inner diameter (mm)",
    "코일 하부 내경 (mm)": "Coil bottom inner diameter (mm)",
    "팁 형상": "Tip geometry",
    "평탄": "Flat",
    "둥근": "Rounded",
    "샤프": "Sharp",
    "팁→노즐 낙하 높이 (mm)": "Tip → nozzle fall height (mm)",
    "용탕 온도 (°C)": "Melt temperature (°C)",
    "이탈모드 하한 We": "Detachment lower We",
    "이탈모드 상한 We": "Detachment upper We",
    "테이퍼 지수 q (집속 강도)": "Taper exponent q (focusing strength)",
    "용탕 생성량": "Melt rate",
    "용탕류 직경(추정)": "Stream diameter (est.)",
    "팁 Weber 수": "Tip Weber number",
    "이탈 모드": "Detachment mode",
    "물방울 모드": "Droplet mode",
    "실(연속류) 모드": "Thread (continuous) mode",
    "전이 영역": "Transition",
    "정지 가스 5~20, 순환 가스 50~200.": "Still gas 5–20, circulating gas 50–200.",
    "스케치 테스트: 상부 내경 = 하부 내경이면 직선 코일(왼쪽 그림), 하부 내경을 줄이면 깔때기 코일(오른쪽 그림)입니다. 테이퍼 지수 q는 집속 강도 보정값입니다 (0 = 집속 없음, 1 = 완전 기하 집속).":
        "Sketch test: equal top/bottom inner diameters give a straight coil (left figure); "
        "shrinking the bottom gives a funnel coil (right figure). The taper exponent q is a "
        "focusing correction (0 = no focusing, 1 = full geometric focusing).",
    "참고: 이탈 모드 판정은 경험식 기반 휴리스틱(v1)입니다. 하한/상한 We 임계값은 본인 장비 경험으로 보정하세요.":
        "Note: the detachment mode is an empirical heuristic (v1). Calibrate the lower/upper We "
        "thresholds against your own equipment experience.",

    # ------------------------------------------------------------ tab 3
    "3. 노즐 — 상부→하부챔버 통과 중 분쇄":
        "3. Nozzle — breakup while passing from the upper to the lower chamber",
    "용탕은 노즐 중심 구멍을 타고 상부챔버에서 하부챔버로 이동하며, 그 통과 구간에서 노즐 고압가스에 맞아 분쇄됩니다.":
        "The melt flows through the nozzle bore from the upper to the lower chamber, and is "
        "atomized by the high-pressure gas in that passage.",
    "노즐 보어 지름 (mm)": "Nozzle bore diameter (mm)",
    "노즐 보어 길이 (mm)": "Nozzle bore length (mm)",
    "가스 분사 형태": "Gas injection type",
    "환형 슬릿": "Annular slit",
    "개별 홀": "Individual holes",
    "가스 분사각 (° , 축 기준)": "Gas injection angle (° from axis)",
    "슬릿 피치 지름 (mm)": "Slit pitch diameter (mm)",
    "슬릿 폭 (mm)": "Slit width (mm)",
    "홀 피치 지름 (mm)": "Hole pitch diameter (mm)",
    "홀 개수": "Number of holes",
    "홀 지름 (mm)": "Hole diameter (mm)",
    "가스 공급압력 (bar)": "Gas supply pressure (bar)",
    "챔버 압력 (bar)": "Chamber pressure (bar)",
    "상하부 압력차 (bar)": "Upper/lower pressure difference (bar)",
    "보어 형상": "Bore type",
    "직선 (초크, Mach 1)": "Straight (choked, Mach 1)",
    "디 라발 (초음속)": "De Laval (supersonic)",
    "디 라발 출구 지름 (mm)": "De Laval exit diameter (mm)",
    "용탕 유량 (kg/min)": "Melt flow (kg/min)",
    "용탕 초기 속도 (m/s)": "Initial melt velocity (m/s)",
    "노즐 유량계수 Cd": "Nozzle discharge coefficient Cd",
    "가스 출구 면적 (mm²)": "Gas exit area (mm²)",
    "노즐 통과 시간": "Nozzle residence time",
    "과팽창 상태입니다 (출구 압력 < 챔버 압력). 노즐 출구 부근에 충격파가 생길 수 있습니다.":
        "Over-expanded (exit pressure < chamber pressure). A shock may form near the nozzle exit.",
    "부족팽창 상태입니다 (출구 압력 > 챔버 압력). 출구 후 제트가 추가로 팽창합니다.":
        "Under-expanded (exit pressure > chamber pressure). The jet expands further after the exit.",
    "적정팽창 상태입니다 (출구 압력 ≈ 챔버 압력).":
        "Ideally expanded (exit pressure ≈ chamber pressure).",
    "홀 사이 빈틈이 큽니다. 빈틈 부분의 용탕은 분쇄가 약해져 균일성이 떨어질 수 있습니다.":
        "The gap between holes is large; melt in those gaps is weakly atomized, which can hurt uniformity.",
    "가스 공급압력이 150 bar를 넘습니다. 실린더 공급 상한을 확인하세요.":
        "Gas supply pressure exceeds 150 bar. Check the cylinder supply limit.",
    "가스 공급압력이 150 bar를 넘습니다. 실린더 공급 상한(약 150~200 bar)을 넘으면 실현이 어려울 수 있습니다 — 장비의 한계로 기록하세요.":
        "Gas supply pressure exceeds 150 bar. Above the cylinder limit (about 150–200 bar) this may "
        "not be feasible — record it as an equipment limit.",
    "해석: 분사각이 클수록 횡방향 속도 성분이 커져 분쇄 Weber 수가 커집니다 (30°→60°에서 약 3배). 축방향 성분은 용탕 가속에 쓰입니다. 0°에서는 횡방향 분쇄가 없어 전단 분쇄만 남습니다 (v1에서는 횡방향 성분만 계상). 통과 시간이 짧을수록 분쇄가 노즐 구간에 집중되고, 상하부 압력차가 클수록 용탕 통과 속도가 빨라져 가스와 만나는 시간이 짧아집니다.":
        "Interpretation: a larger injection angle increases the transverse velocity component and "
        "therefore the breakup Weber number (about 3× from 30° to 60°). The axial component "
        "accelerates the melt. At 0° there is no transverse breakup, only shear breakup "
        "(v1 counts the transverse component only). A shorter residence time concentrates breakup in "
        "the nozzle region, and a larger pressure difference speeds the melt up so it meets the gas "
        "for less time.",

    # ------------------------------------------------------------ tab 4
    "4. 분말 품질 — 상변화·산화·점도·유동성 (2단계)":
        "4. Powder quality — phase change, oxidation, viscosity, flowability (stage 2)",
    "액적 직경 (µm)": "Droplet diameter (µm)",
    "응고까지 냉각 시간": "Cooling time to solidification",
    "액적 초기 온도 (°C)": "Initial droplet temperature (°C)",
    "챔버 가스 온도 (°C)": "Chamber gas temperature (°C)",
    "응고 완료까지 비행 거리": "Flight distance to full solidification",
    "액적 비행 속도 (m/s)": "Droplet flight velocity (m/s)",
    "챔버 높이 (m)": "Chamber height (m)",
    "냉각·응고 거리": "Cooling / solidification distance",
    "상변화 (응고 구간)": "Phase change (solidification range)",
    "산화 (표면 산화층 모델)": "Oxidation (surface oxide model)",
    "산화층 두께 가정 (nm)": "Assumed oxide thickness (nm)",
    "산소 함량 추정": "Estimated oxygen content",
    "구형화 (점도 vs 표면장력)": "Spheroidization (viscosity vs surface tension)",
    "유동성 (휴리스틱 등급)": "Flowability (heuristic grade)",
    "유동성 등급 (휴리스틱)": "Flowability grade (heuristic)",
    "양호": "Good",
    "보통": "Fair",
    "불량 가능": "Likely poor",
    "챔버 높이 안에서 응고가 완료되는 것으로 예측됩니다.":
        "Solidification is predicted to complete inside the chamber height.",
    "응고 완료 거리가 챔버 높이보다 깁니다. 벽/바닥에 닿기 전에 굳지 못해 불규칙 입자·스플랫 위험이 있습니다.":
        "The solidification distance is longer than the chamber height: droplets may hit the wall or "
        "floor before freezing, risking irregular particles and splats.",
    "응고 구간이 좁아 급속 응고에 유리합니다.":
        "The solidification range is narrow, which favours rapid solidification.",
    "응고 구간이 넓습니다. 머시(mushy) 상태가 길어져 불규칙 형상 위험이 커집니다.":
        "The solidification range is wide; a longer mushy zone increases the risk of irregular shapes.",
    "오더 추정 모델입니다. 산소량은 1/D에 비례하므로 분말이 가늘수록 산화에 민감합니다. 실제 산화량은 노출 시간, 온도 이력, 챔버 산소 농도에도 좌우됩니다.":
        "This is an order-of-magnitude model. Oxygen scales as 1/D, so finer powder is more oxidation "
        "sensitive. Real oxygen pickup also depends on exposure time, thermal history and the "
        "chamber oxygen level.",
    "구형화가 냉각보다 훨씬 빨라 구형 입자가 예상됩니다.":
        "Spheroidization is much faster than cooling, so spherical particles are expected.",
    "구형화가 냉각보다 느려 불규칙 형상이 남을 수 있습니다. 산화막이 있으면 구형화가 더 방해받습니다.":
        "Spheroidization is slower than cooling, so irregular shapes may remain. An oxide film "
        "hinders spheroidization further.",
    "판정 근거: D50 20µm 이상, 미분 20% 미만, 구형화 완료 — 3개 중 충족 개수. 실측(Hall flow 등)으로 검증이 필요한 추정치입니다.":
        "Basis: D50 ≥ 20 µm, fines < 20 %, spheroidization complete — how many of the three are met. "
        "This is an estimate that needs validation with real measurements (e.g. Hall flow).",

    # ------------------------------------------------------------ tab 5
    "5. 수율 계산 — 합격 입도 범위로 공정 수율 구하기":
        "5. Yield — process yield for a given acceptance size window",
    "분말을 어느 입도 범위로 쓸지 정하면, 그 범위에 들어가는 질량분율이 곧 공정 수율입니다. 예를 들어 10~45 µm만 합격으로 보면, 전체 용탕 중 몇 %가 합격 분말이 되는지 바로 나옵니다. 아래 숫자는 모두 직접 수정할 수 있습니다.":
        "Pick the size window you need: the mass fraction inside it is the process yield. For "
        "example, accepting only 10–45 µm immediately shows what share of the melt becomes saleable "
        "powder. Every number below can be edited.",
    "합격 하한 (µm)": "Accept lower limit (µm)",
    "합격 상한 (µm)": "Accept upper limit (µm)",
    "분말 D50 (µm, 기본값은 1 공정 결과)": "Powder D50 (µm, default from tab 1)",
    "입도분포 폭 σg (로그정규)": "Spread σg (log-normal)",
    "용탕 유량 (kg/min, 수율 환산 기준)": "Melt flow (kg/min, yield basis)",
    "기본값은 `1 공정` 탭의 계산 결과(D50·σg)입니다. 실측 입도분석 값이 있으면 덮어쓰세요.":
        "Defaults are the values computed in tab 1 (D50, σg). Overwrite them with measured sieve "
        "or laser data if you have it.",
    "합격 수율": "Acceptable yield",
    "미달 (너무 작음)": "Undersize (too fine)",
    "과대 (너무 큼)": "Oversize (too coarse)",
    "합격품 평균 입도": "Mean size of accepted powder",
    "합격 분말 생산량": "Saleable powder output",
    "합격 구간이 전체 수율에서 차지하는 비율":
        "Share of the total yield that falls inside the acceptance window",
    "합격 구간만 남겼을 때의 질량 가중 산술평균 입도입니다. 범위를 좁히거나 하한을 올리면 이 값도 함께 올라갑니다.":
        "Mass-weighted mean size of the accepted fraction only. Narrowing the window or raising the "
        "lower limit pushes this value up.",
    "구간": "Band",
    "생산량 (kg/h)": "Output (kg/h)",
    "구간별 분해": "Breakdown by band",
    "합계": "Total",
    "합격 상한이 하한보다 커야 합니다. 숫자를 다시 확인하세요.":
        "The upper limit must be larger than the lower limit. Please check the numbers.",
    "수율 = Φ[ln(상한/D50)/lnσg] − Φ[ln(하한/D50)/lnσg] (로그정규·질량 기준). 합격 범위를 좁힐수록 수율은 떨어지고, D50을 합격 구간 가운데로 옮기면 수율이 올라갑니다. 실제 공정 수율은 분급기 효율, 벽 부착, 산화·오염 손실 때문에 이 값보다 낮습니다.":
        "Yield = Φ[ln(upper/D50)/lnσg] − Φ[ln(lower/D50)/lnσg] (log-normal, mass basis). A narrower "
        "window lowers yield; centring D50 in the window raises it. Real plant yield is lower than "
        "this because of classifier efficiency, wall sticking and oxidation/contamination losses.",

    # ------------------------------------------------------------ coil tab
    "코일 가열 보기 — 봉 팁 콘 + 코일 형상 단면":
        "Coil heating view — rod tip cone + coil cross-section",
    "봉은 위에서 아래로 공급되고, 아래 끝에 콘(테이퍼) 팁이 있습니다. 고주파 전류는 표피 효과로 봉 표면층에만 열을 넣고, 열은 전도로 안쪽으로 퍼집니다. 코일이 봉 단면을 따라 같이 좁아지면 같은 출력이 팁 근처의 작은 단면에 집중되어 팁이 더 뜨거워집니다. 봉 팁 콘의 크기와 코일의 내경·깊이·간극·축방향 위치를 아래에서 모두 조절할 수 있습니다.":
        "The rod is fed downward and ends in a conical (tapered) tip. The high-frequency current "
        "deposits heat only in the surface skin (skin effect) and conduction spreads it inward. If "
        "the coil narrows with the rod, the same power concentrates in the small tip section, "
        "making the tip hotter. Cone size, coil inner diameter, depth, gap and axial position are "
        "all adjustable below.",
    "봉 팁 콘 높이 (mm)": "Tip cone height (mm)",
    "봉 팁 지름 (mm)": "Tip diameter (mm)",
    "코일 형상": "Coil profile",
    "봉 형상 따라가기 (콘 밀착)": "Follow rod profile (hug the cone)",
    "직선": "Straight",
    "원뿔 (선형 테이퍼)": "Cone (linear taper)",
    "곡선 테이퍼 (지수)": "Curved taper (exponential)",
    "‘봉 형상 따라가기’는 코일 내경 = 봉 반경 + 간극으로, 콘 구간에서 코일도 함께 좁아집니다.":
        "‘Follow rod profile’ sets the coil inner radius to rod radius + gap, so the coil narrows "
        "with the cone too.",
    "코일 시작 위치 (팁 기준, mm)": "Coil start position (from tip, mm)",
    "코일 끝 위치 (팁 기준, mm)": "Coil end position (from tip, mm)",
    "위쪽 잘라내기 (코일 상단에서, mm)": "Crop from coil top (mm)",
    "코일–봉 간극 (mm)": "Coil–rod gap (mm)",
    "코일 감은 횟수 (턴)": "Number of turns",
    "코일 단면 형상": "Coil cross-section",
    "원형": "Round",
    "직사각형": "Rectangular",
    "코일선 지름 (mm)": "Coil wire diameter (mm)",
    "코일선 폭 (mm, 반경방향)": "Coil wire width (mm, radial)",
    "코일선 두께 (mm, 축방향)": "Coil wire thickness (mm, axial)",
    "주파수 (kHz)": "Frequency (kHz)",
    "봉 공급 온도 (°C)": "Rod feed temperature (°C)",
    "코일 위 봉 길이 (mm)": "Rod length above the coil (mm)",
    "테이퍼 지수 p": "Taper exponent p",
    "표피 깊이": "Skin depth",
    "팁 표면 온도": "Tip surface temperature",
    "용융 캡 길이": "Melt cap length",
    "용탕 생성 임계 출력 (근사)": "Melt onset power (approx.)",
    "뾰족(Ø0)": "sharp (Ø0)",
    "0이면 콘 없이 직선 팁입니다.": "0 = straight tip with no cone.",
    "콘 끝의 지름. 0이면 뾰족한 팁(절단 없음), 0보다 크면 그 지름으로 잘린 절두 원뿔입니다.":
        "Diameter at the cone end. 0 = sharp tip (no truncation); larger values truncate the cone "
        "to that diameter.",
    "봉 지름. 코일–봉 간극과 함께 코일이 봉에서 열마나 떨어지는지를 결정합니다.":
        "Rod diameter. Together with the coil–rod gap it sets how far the coil sits from the rod.",
    "봉 팁 끝단을 0으로 둔 위치입니다. +는 팁 위, −는 팁 아래(금속보다 더 아래)까지 가능합니다.":
        "Position measured from the rod tip (0). + is above the tip, − is below it (even below the metal).",
    "코일 마지막 턴의 위치. −로 두면 코일이 금속 팁보다 아래로 내려갑니다 (기본 −10 mm = 팁 아래로 한 턴 더).":
        "Position of the last turn. Negative puts the coil below the metal tip "
        "(default −10 mm = one turn below the tip).",
    "그림에서 코일 상단부터 이만큼 아래를 위쪽 경계로 씁니다.":
        "The top of the chart starts this far below the coil top.",
    "코일 내면과 봉 표면 사이 거리. '봉 형상 따라가기'에서는 코일 내경을 봉 지름 + 간극 2배로 잡고, 다른 형상에서도 최소 간극으로 적용됩니다.":
        "Distance between the coil inner face and the rod surface. In ‘follow rod profile’ the coil "
        "inner diameter is rod diameter + 2×gap; other profiles keep at least this gap.",
    "실제 유도 코일은 보통 원형 단면(동관·동선)입니다. 단면 형상과 무관하게 코일 위치·출력 계산은 동일합니다.":
        "Real induction coils usually have a round section (copper tube/wire). Position and power "
        "calculations are identical for either section.",
    "원형 단면의 지름입니다.": "Diameter of the round section.",
    "턴별 리플(0.3)은 예시 크기입니다. 턴 간격이 좁을수록 리플이 촘촘해져 가열이 균일해집니다.":
        "The turn-to-turn ripple (0.3) is an illustrative magnitude. Tighter turn spacing makes the "
        "ripple finer and the heating more uniform.",
    "팁 표면이 액상선에 못 미칩니다. 출력을 올리거나 코일을 팁에 가깝게 해야 용탕이 생깁니다.":
        "The tip surface stays below the liquidus. Raise the power or bring the coil closer to the "
        "tip to create melt.",
    "p > 1: 아래쪽에서 급격히 좁아짐(팁 집중형), p < 1: 위쪽에서 급격히 좁아짐, p = 1: 원뿔":
        "p > 1: narrows sharply at the bottom (tip-focused); p < 1: narrows sharply at the top; p = 1: cone",
    "봉 Ø60 mm·코일 간극 20 mm 기본 조건에서 팁이 액상선을 넘으려면 약 80 kW가 필요합니다.":
        "With rod Ø60 mm and a 20 mm gap, about 80 kW is needed for the tip to pass the liquidus.",
    "왜 물방울 모드 / 실 모드로 갈리나? (점도·표면장력 이야기)":
        "Why droplet mode vs. thread mode? (viscosity and surface tension)",
    "원뿔 vs 직선 코일 — 왜 원뿔이 팁을 더 뜨겁게 만드는가 (실제 계산 결과, 316L·50kW·효율 0.6·공급 2.0mm/s)":
        "Conical vs straight coil — why the cone makes the tip hotter "
        "(computed, 316L · 50 kW · 0.6 efficiency · 2.0 mm/s feed)",
    "가열 단면": "Heating cross-section",
    "반경 (mm)": "Radius (mm)",
    "깊이 (mm, 아래로 갈수록 팁)": "Depth (mm, deeper = closer to tip)",
    "깊이 (mm)": "Depth (mm)",
    "온도": "Temperature",
    "액상선": "Liquidus",
    "표면 온도": "Surface temperature",
    "중심 온도": "Centre temperature",
    "콘 시작": "Cone start",
    "코일 시작": "Coil start",
    "코일 끝": "Coil end",
    "반경 %{x:.1f} mm<br>깊이 %{y:.1f} mm<br>온도 %{z:.0f} °C<extra></extra>":
        "Radius %{x:.1f} mm<br>Depth %{y:.1f} mm<br>Temperature %{z:.0f} °C<extra></extra>",
    "액상선 이상<br>깊이 %{y:.1f} mm<extra></extra>":
        "Above liquidus<br>Depth %{y:.1f} mm<extra></extra>",
    "참고: 속도를 초기 속도로 유지한 상한 추정치입니다. 실제 액적은 항력으로 감속하므로 실제 비행 거리는 이보다 짧습니다.":
        "Upper estimate that keeps the initial velocity. Real droplets decelerate, so the actual "
        "flight distance is shorter.",

    # ------------------------------------------------------------ radiation tab
    "복사열 — 주변(챔버 벽) 온도 변화": "Radiation — surrounding (chamber wall) temperature",
    "봉과 코일이 뜨거워지면 표면에서 복사로 주변 벽에 열을 보냅니다. 벽은 열용량 때문에 서서히 데워지고, 가스 대류와 외부 냉각·재복사로 열을 잃습니다. 고온부 온도·면적·복사율, 벽 재질·두께·면적, 시간을 바꿔가며 **주변 온도가 시간에 따라** 어떻게 오르는지 봅니다.":
        "Once the rod and coil are hot they radiate to the surrounding wall. The wall heats slowly "
        "because of its heat capacity, and loses heat by gas convection, outer cooling and "
        "re-radiation. Change the hot-body temperature/area/emissivity, the wall material, "
        "thickness and area, and the time span to see **how the surroundings heat up over time**.",
    "고온부(봉·코일) 표면 온도 (°C)": "Hot body (rod/coil) surface temperature (°C)",
    "고온부 표면적 (m²)": "Hot body surface area (m²)",
    "복사율 ε": "Emissivity ε",
    "형상 계수 F (고온부→벽)": "View factor F (hot body → wall)",
    "주변 벽 면적 (m²)": "Wall area (m²)",
    "벽 두께 (mm)": "Wall thickness (mm)",
    "벽 재질": "Wall material",
    "스테인리스 (ρ 7900, cp 500)": "Stainless steel (ρ 7900, cp 500)",
    "탄소강 (ρ 7850, cp 470)": "Carbon steel (ρ 7850, cp 470)",
    "알루미늄 (ρ 2700, cp 900)": "Aluminium (ρ 2700, cp 900)",
    "구리 (ρ 8960, cp 385)": "Copper (ρ 8960, cp 385)",
    "가스 대류 계수 h (W/m²·K)": "Gas convection coefficient h (W/m²·K)",
    "벽 외부 냉각 계수 (W/m²·K)": "Wall outer cooling coefficient (W/m²·K)",
    "벽 초기 온도 (°C)": "Initial wall temperature (°C)",
    "가스(챔버) 온도 (°C)": "Gas (chamber) temperature (°C)",
    "관찰 시간 (s)": "Observation time (s)",
    "벽은 두께 방향으로 온도가 균일(집중 열용량)하다고 가정합니다.":
        "The wall is assumed uniform through its thickness (lumped heat capacity).",
    "예: 봉 Ø60 mm × 120 mm ≈ 0.023 m², 코일 턴까지 더하면 약 0.03 m².":
        "e.g. rod Ø60 mm × 120 mm ≈ 0.023 m²; adding the coil turns gives about 0.03 m².",
    "산화된 금속 0.7~0.9, 광택 금속 0.1~0.3.": "Oxidized metal 0.7–0.9, polished metal 0.1–0.3.",
    "고온부가 벽을 보는 비율(기하). 챔버가 클수록 작습니다.":
        "Fraction of the wall seen by the hot body (geometry). Smaller in a large chamber.",
    "물 재킷이면 500~3000, 진공·단열이면 작게(0~20).":
        "Water jacket 500–3000; vacuum/insulated → keep it small (0–20).",
    "초기 복사 열유속": "Initial radiative heat flux",
    "평형(정상상태) 벽 온도": "Equilibrium (steady) wall temperature",
    "90 % 도달 시간": "Time to 90 %",
    "벽 온도": "Wall temperature",
    "복사 열유량": "Radiative heat flow",
    "시간 (s)": "Time (s)",
    "벽 온도 (°C)": "Wall temperature (°C)",
    "복사 열유량 (kW)": "Radiative heat flow (kW)",
    "주변 벽 온도와 복사 열유량 (시간에 따라)":
        "Surrounding wall temperature and radiative heat flow over time",
    "t = %{x:.0f} s<br>벽 %{y:.0f} °C<extra></extra>":
        "t = %{x:.0f} s<br>wall %{y:.0f} °C<extra></extra>",
}

# Korean fragment -> English (f-string parts, longest-first substitution)
TERM = {
    # long tails
    " s — 체류 시간이 확산 시간보다 짧으면 중심까지 열이 다 퍼지기 전에 팁이 나가므로 표면 위주 가열이 됩니다 (정상상태 근사라 실제보다 균일하게 보일 수 있음).":
        " s — when the residence time is shorter than the diffusion time, the tip leaves before heat "
        "reaches the centre, so heating is surface-dominated (steady-state approximation, so it may "
        "look more uniform than reality).",
    " kJ/K — 무거운 벽일수록 천천히 데워집니다. 초기 복사 열유속은 벽이 차가울 때 가장 크고, 벽이 데워지면 T⁴ 차이가 줄어 급격히 떨어집니다(파란 점선).":
        " kJ/K — a heavier wall heats more slowly. The initial radiative flux is largest while the "
        "wall is cold and falls quickly as the T⁴ difference shrinks (blue dotted line).",
    " — 팁 형상보다 코일이 금속을 어떻게 녹이는지가 지배적이라는 점을 기억하세요. 팁 형상은 현 버전에서는 정성 변수로만 기록됩니다.":
        " — remember that how the coil melts the metal dominates over tip shape. Tip shape is "
        "recorded only as a qualitative variable in this version.",
    " mm). 그림은 겹치지 않게 보정해 그립니다. 코일 내경을 키우거나 간극을 조정하세요.":
        " mm). The drawing is corrected so they do not overlap. Increase the coil inner diameter or "
        "adjust the gap.",
    " mm)보다 커서 그림에서 턴이 겹칩니다. 선재 치수를 줄이거나 턴 수를 늘리세요.":
        " mm) is larger than the turn pitch (",
    " mm — 원뿔 코일은 열을 팁 쪽에 집중시켜 같은 출력에서 팁이 더 뜨겁습니다.":
        " mm — the conical coil concentrates heat near the tip, so the tip is hotter at the same power.",
    " m/s (가스 속도가 지배해서 각도 영향이 작음), 횡방향 속도(분사각 ":
        " m/s (gas velocity dominates, so the angle effect is small), transverse velocity (angle ",
    "% — 제트는 하류에서 확산되므로 실제 커버율은 이보다 높습니다.":
        " % — the jet spreads downstream, so the real coverage is higher.",
    "팁 표면이 액상선 이상입니다. 용탕 생성 가능 — 이탈 모드: ":
        "Tip surface is above the liquidus. Melt forms — detachment mode: ",
    " · 위쪽 비가열부 생략 (색 = 온도, 마우스를 올리면 값)":
        " · non-heated top omitted (colour = temperature, hover for values)",
    "직선 코일(상=하 내경) 비교: 팁 표면 온도 ":
        "Straight coil (equal top/bottom ID) comparison: tip surface temperature ",
    "비교 — 직선 코일(테이퍼 없음): 류 직경 ":
        "Comparison — straight coil (no taper): stream diameter ",
    " kg/h. 참고 D10/D50/D90 = ": " kg/h. Reference D10/D50/D90 = ",
    " m/s, 횡방향 상호작용 Weber 수: ": " m/s, transverse interaction Weber number: ",
    "코일 내경은 봉 지름 + 간극 2배 = ": "Coil inner diameter = rod diameter + 2× gap = ",
    " kg/min, 가스 제트 속도: ": " kg/min, gas jet velocity: ",
    " mm (+위/−아래). 봉 길이 ": " mm (+above/−below). Rod length ",
    "제트 원주 커버율(출구면 기준): ": "Jet circumferential coverage (exit plane): ",
    " mm, 코일 상단은 봉 위에서 ": " mm; the coil top is ",
    "가스 출구 면적(형상 계산): ": "Gas exit area (geometry): ",
    "코일이 봉을 파고듭니다 (깊이 ": "The coil cuts into the rod (at depth ",
    " / 테이퍼 적용: 류 직경 ": " / with taper: stream diameter ",
    " m²/s, Weber 수: ": " m²/s, Weber number: ",
    " N/m) vs 냉각 시간 ": " N/m) vs cooling time ",
    " mm 로 자동 결정됩니다.": " mm is set automatically.",
    " mm, 팁 Weber 수 ": " mm, tip Weber number ",
    "°C), 평균 냉각 속도: ": " °C), mean cooling rate: ",
    " N/m, 용탕 동점도: ": " N/m, melt kinematic viscosity: ",
    " kg/h 중 합격 분말 ": " kg/h of which saleable powder is ",
    " mm 내려온 지점입니다.": " mm below the rod top.",
    " m/s, 상대 속도: ": " m/s, relative velocity: ",
    " mm², 가스 흐름: ": " mm², gas flow: ",
    " s vs 열확산 시간 ": " s vs thermal diffusion time ",
    "벽 열용량 m·cp = ": "Wall heat capacity m·cp = ",
    " (팁 Weber 수 ": " (tip Weber number ",
    " Pa·s, 표면장력 ": " Pa·s, surface tension ",
    " mm², 출구 면적 ": " mm², exit area ",
    " mm에서 코일 반경 ": " mm the coil radius ",
    ", 용탕 통과 속도: ": ", melt passage velocity: ",
    "턴, 코일은 팁 기준 ": "turns, coil from tip ",
    " mm ≤ 봉 반경 ": " mm ≤ rod radius ",
    " mm 구간에서 팁 ": " mm section, tip ",
    " mm)가 턴 간격(": " mm) is larger than the turn pitch (",
    " µs (용탕 점도 ": " µs (melt viscosity ",
    "구형화 시간 척도: ": "Spheroidization time scale: ",
    "디 라발: 목 면적 ": "De Laval: throat area ",
    "시간당 기준: 용탕 ": "Per hour: melt ",
    " m/s, 용탕량 ": " m/s, melt flow ",
    " mm, 팁 형상 ": " mm, tip geometry ",
    " mm², 면적비 ": " mm², area ratio ",
    " °C, 용융 캡 ": " °C, melt cap ",
    ", 출구 Mach ": ", exit Mach ",
    " bar (챔버 ": " bar (chamber ",
    " s 뒤 벽 온도": " s wall temperature",
    "), 표면장력: ": "), surface tension: ",
    "°C ~ 고상선 ": " °C to solidus ",
    "코일 감은 횟수 ": "coil turns ",
    "회, 코일 길이 ": " turns, coil length ",
    " K (액상선 ": " K (liquidus ",
    " mm → 콘 ": " mm → cone ",
    " mm, 속도 ": " mm, velocity ",
    ", 출구 압력 ": ", exit pressure ",
    "µm) 분율: ": " µm) fraction: ",
    "가열 단면 — ": "Heating cross-section — ",
    " mm·길이 ": " mm·length ",
    ", 류 직경 ": ", stream diameter ",
    "가스 유량: ": "Gas flow: ",
    "응고 구간: ": "Solidification range: ",
    "코일선 두께(": "Coil wire thickness (",
    "합격 수율 (": "Acceptable yield (",
    "형상: 봉 Ø": "Shape: rod Ø",
    "µm) 수율": " µm) yield",
    "과대 (> ": "Oversize (> ",
    "목표 범위(": "Target window (",
    "미달 (< ": "Undersize (< ",
    "체류 시간 ": "Residence time ",
    "합격 구간 ": "Accept window ",
    ", 모드 ": ", mode ",
    ", 코일 ": ", coil ",
    " 단면 ": " section ",
    "미분(<": "Fines (<",
    "합격 (": "Accept (",
    "수율 ": "Yield ",
    "평형 ": "Equilibrium ",
    " mm, ": " mm, ",
    "  ↑ 위로 계속": "  ↑ continues above",
    " mm": " mm",
}

DOCS = {
    "usage": """\n**How to use**
1. Pick the alloy and gas in the sidebar.
2. In `1 Process` change the conditions and watch D50, the size distribution and yield; use the sweep and operating window to find the rules.
3. In `2 Rod & Coil` check the melt rate and the tip detachment mode (droplet / thread).
4. In `3 Nozzle` look at gas flow, GMR and residence time to see the nozzle's influence.
5. In `4 Powder Quality` check whether the solidification distance fits inside the chamber.
6. In `5 Yield` set the acceptance size window (e.g. 10–45 µm) and see what share of the total yield falls inside it.
7. In `Radiation` see how the hot body heats the surrounding wall over time.

**Tip detachment mode (droplet vs thread) — why it splits (v2 falling-stream model)**
- The decision has three stages. **Stage 1 — neck formation:** the tip is not a nozzle; melt pools there and detaches through a pendant neck. The stream diameter right after detachment follows from the mass balance at the capillary velocity `v_cap = √(σ/(ρ·R))`, and if the neck Weber number `We_neck = d_neck/R` is below 2, the tip drips droplets directly.
- **Stage 2 — fall stretching:** over the tip-to-gas-zone distance the stream accelerates under gravity + gas drag + chamber ΔP suction and thins by continuity. A narrow tip alone does not make a thread — the stretching during the fall is the key step.
- **Stage 3 — survival:** if the fall time `t_fall` exceeds the capillary breakup time scale `t_b ≈ 30·√(ρ·(d/2)³/σ)`, the column breaks before reaching the gas zone and arrives as droplets.
- It is **independent of whether the metal is molten**. Even when the tip is fully above the liquidus, a neck that cannot hold together, or a column that breaks during the fall, gives droplet mode.
- To move toward thread mode: higher melt flow (power/feed rate), shorter fall distance, stronger gas/ΔP acceleration, more superheat (lower σ).
- **Viscosity** enters as `Oh = μ/√(ρ·σ·d)`. Higher viscosity widens the droplet side. For a mm-scale neck `Oh ≈ 0.002`, i.e. well under 1 % influence; it matters for micro-orifices or high-viscosity melts. **The current criterion uses neck We and fall time only (a known limitation).**
- σ falls as temperature rises, so We_neck rises: at the same flow, more superheat pushes toward thread mode.

**Radiation tab**
- The hot body radiates to the wall as `q = ε·σ·A_hot·F·(T_hot⁴ − T_wall⁴)`.
- The wall heats by its heat capacity `m·cp` and loses heat by gas convection (`h·A·(T−T_gas)`), outer cooling and re-radiation.
- The time constant is roughly `τ = m·cp/(4εσA·T³ + h·A)`; read it from the ‘time to 90 %’ metric.
- A water-cooled wall (large h_out) stays cool; vacuum/insulation lets it climb hundreds of degrees.

**Core equations**
- Lubanska correlation: D50/D = K·√[(νm/νg)·(1/We)·(1+M/A)], We based on melt density
- Size distribution: log-normal (default σg = 2.0)
- Gas: sonic jet under choked conditions; mass flow from the choked-flow equation
- Tip detachment mode: falling-stream model (v2) — thresholds need calibration

**Limits (honestly)**
- This is not CFD. Turbulence, flow inside the nozzle and real 3-D geometry are not solved.
- Properties are representative values. Replace them with your own alloy data.
- K, coil efficiency and the detachment thresholds are equipment-dependent calibration parameters.
- Phase change, oxidation and flowability are added in stage 2.

**Next steps**
- With historical ALD operating records, calibrate K, the detachment thresholds and the taper exponent q.
- Load the target nozzle geometry as the first test case.
- Extend the sweep/window search to nozzle geometry (bore, spray angle, slit form) combined with coil taper.
""",
    "droplet": """The decision has three stages (v2 falling-stream model).

- **Stage 1 — neck formation.** The tip is not a nozzle; melt pools there and detaches through a pendant neck. The stream diameter right after detachment follows from the mass balance at the capillary velocity `v_cap = √(σ/(ρ·R))`: `d_neck = √(4·m_dot/(π·ρ·v_cap))`. If the neck Weber number `We_neck = d_neck/R` is low (< 2), no continuous column survives and the tip drips droplets directly.
- **Stage 2 — fall stretching.** Over the tip-to-gas-zone distance the stream accelerates under gravity + gas drag + chamber ΔP suction and thins by continuity (`v = √(v_cap² + 2·a·H)`, `d ∝ 1/√v`). A narrow tip alone does not make a thread — the stretching during the fall is the key step.
- **Stage 3 — survival.** Whether the stream breaks up by capillary (Rayleigh-Plateau) instability before reaching the gas zone: if the fall time `t_fall` exceeds the breakup time scale `t_b ≈ 30·√(ρ·(d/2)³/σ)`, it arrives as droplets.
- **It is independent of whether the metal is molten.** Even when the tip is fully above the liquidus, a neck that cannot hold together, or a column that breaks during the fall, gives droplet mode.
- To move toward thread mode: higher melt flow (power/feed rate), shorter fall distance, stronger gas/ΔP acceleration, more superheat (lower σ).
- Viscosity enters as `Oh = μ/√(ρ·σ·d)`. Higher viscosity widens the droplet side. For a mm-scale neck Oh ≈ 0.002 (under 1 % influence); it matters for micro-orifices and high-viscosity melts (current criterion uses neck We and fall time only — a limitation).
- The v2 thresholds (neck We 2/4, breakup factor 30) are literature-scale heuristics and need calibration against equipment records.""",
}

_TERM_KEYS = None


def _term_keys():
    global _TERM_KEYS
    if _TERM_KEYS is None:
        _TERM_KEYS = sorted(TERM.keys(), key=len, reverse=True)
    return _TERM_KEYS


def get_lang():
    """Current UI language: "en" (default) or "ko"."""
    return st.session_state.get("lang", DEFAULT_LANG)


def set_lang(code):
    """Switch language; drop cached string widget values (they are language-bound)."""
    new = "ko" if code == "ko" else "en"
    if st.session_state.get("lang", DEFAULT_LANG) != new:
        for key, val in list(st.session_state.items()):
            if key != "lang" and isinstance(val, str):
                del st.session_state[key]
    st.session_state["lang"] = new


def doc(key, ko_text):
    """Long markdown block: English version when the UI language is English."""
    if get_lang() == "ko":
        return ko_text
    return DOCS.get(key, ko_text)


def tr(text):
    """Translate one Korean string to English when the language is English."""
    if not isinstance(text, str) or not text.strip():
        return text
    if get_lang() != "en":
        return text
    hit = EN.get(text)
    if hit is not None:
        return hit
    out = text
    for key in _term_keys():
        if key in out:
            out = out.replace(key, TERM[key])
    return out


# ---------------------------------------------------------------- st wrapping
_TEXT_FUNCS = ("title", "header", "subheader", "markdown", "write", "caption",
               "info", "success", "warning", "error", "text", "code")
_WIDGET_FUNCS = ("button", "download_button", "checkbox", "number_input", "slider",
                 "text_input", "text_area", "form_submit_button", "file_uploader",
                 "toggle", "color_picker", "date_input", "time_input")
_SELECT_FUNCS = ("selectbox", "radio")


def _auto_key():
    """Stable per-call-site widget key (translated labels can collide)."""
    fr = sys._getframe(2)
    return "i18n_" + hashlib.md5(f"{fr.f_code.co_filename}:{fr.f_lineno}".encode()).hexdigest()[:10]


def _tr_first_str(args):
    """Translate the first string positional argument (skips `self` of class methods)."""
    for i, a in enumerate(args):
        if isinstance(a, str):
            return args[:i] + (tr(a),) + args[i + 1:]
    return args


def _fmt_option(opt):
    return tr(opt) if isinstance(opt, str) else opt


def _wrap(fn, kind):
    def wrapper(*args, **kwargs):
        if kind == "text":
            args = tuple(tr(a) if isinstance(a, str) else a for a in args)
            for k in ("body", "help", "caption"):
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
        elif kind == "widget":
            args = _tr_first_str(args)
            if "key" not in kwargs:
                kwargs["key"] = _auto_key()
            for k in ("label", "help", "placeholder"):
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
        elif kind == "select":
            opts = None
            label_i = next((i for i, a in enumerate(args) if isinstance(a, str)), None)
            if (label_i is not None and len(args) > label_i + 1
                    and isinstance(args[label_i + 1], (list, tuple))):
                opts = list(args[label_i + 1])
                disp = [tr(o) if isinstance(o, str) else o for o in opts]
                args = args[:label_i + 1] + (disp,) + args[label_i + 2:]
            elif isinstance(kwargs.get("options"), (list, tuple)):
                opts = list(kwargs["options"])
                kwargs["options"] = [tr(o) if isinstance(o, str) else o for o in opts]
            args = _tr_first_str(args)
            for k in ("label", "help"):
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
            res = fn(*args, **kwargs)
            if opts is not None and isinstance(res, str):
                for o in opts:
                    if isinstance(o, str) and tr(o) == res:
                        return o
            return res
        elif kind in ("metric", "expander"):
            args = _tr_first_str(args)
            for k in ("label", "help"):
                if isinstance(kwargs.get(k), str):
                    kwargs[k] = tr(kwargs[k])
        elif kind == "tabs":
            if args and isinstance(args[0], (list, tuple)):
                seq = [tr(x) if isinstance(x, str) else x for x in args[0]]
                args = (type(args[0])(seq),) + args[1:]
        elif kind == "image":
            if isinstance(kwargs.get("caption"), str):
                kwargs["caption"] = tr(kwargs["caption"])
        elif kind == "dataframe":
            if args and isinstance(args[0], dict):
                args = ({tr(k) if isinstance(k, str) else k: v
                         for k, v in args[0].items()},) + args[1:]
        elif kind == "page_config":
            if isinstance(kwargs.get("page_title"), str):
                kwargs["page_title"] = tr(kwargs["page_title"])
        return fn(*args, **kwargs)

    wrapper._i18n_wrapped = True
    return wrapper


def install(st_mod):
    """Patch Streamlit's text/widget functions to translate Korean literals."""
    if getattr(st_mod, "_i18n_installed", False):
        return
    targets = [st_mod]
    seen = set()
    try:
        import streamlit.delta_generator as dg
        for obj in list(vars(dg).values()) + [dg.DeltaGenerator]:
            if isinstance(obj, type) and id(obj) not in seen:
                seen.add(id(obj))
                targets.append(obj)
    except Exception:
        pass
    try:
        cls = type(st_mod.sidebar)
        if id(cls) not in seen:
            targets.append(cls)
    except Exception:
        pass
    plan = [("text", _TEXT_FUNCS), ("widget", _WIDGET_FUNCS),
            ("select", _SELECT_FUNCS), ("metric", ("metric",)),
            ("expander", ("expander",)), ("tabs", ("tabs",)),
            ("image", ("image",)), ("dataframe", ("dataframe",)),
            ("page_config", ("set_page_config",))]
    for kind, names in plan:
        for name in names:
            for tgt in targets:
                fn = getattr(tgt, name, None)
                if callable(fn) and not getattr(fn, "_i18n_wrapped", False):
                    try:
                        setattr(tgt, name, _wrap(fn, kind))
                    except Exception:
                        pass
    st_mod._i18n_installed = True


def language_switch(container=None):
    """Language buttons: English (default) / 한국어."""
    box = container if container is not None else st
    cur = get_lang()
    c1, c2 = box.columns(2)
    if c1.button("English", key="lang_btn_en", use_container_width=True,
                 type="primary" if cur == "en" else "secondary"):
        set_lang("en")
        st.rerun()
    if c2.button("한국어", key="lang_btn_ko", use_container_width=True,
                 type="primary" if cur == "ko" else "secondary"):
        set_lang("ko")
        st.rerun()


# ---------------------------------------------------------------- physics texts
EN.update({
    "팁 Weber 수가 낮아 용탕이 물방울로 똑똑 떨어지는 경향. 분무가 불균일해져 입도분포가 넓어지고 굵은 입자/위성분말 위험이 큼.":
        "Low tip Weber number: the melt tends to drip as droplets. Atomization becomes uneven, the "
        "size distribution widens and the risk of coarse particles/satellites grows.",
    "팁 Weber 수가 높아 용탕이 가늘게 실처럼 이어지며 떨어지는 경향. 균일한 분무에 유리한 영역.":
        "High tip Weber number: the melt leaves as a thin continuous thread. This is the favourable "
        "region for uniform atomization.",
    "물방울 모드와 실 모드의 경계. 작은 조건 변화에도 모드가 바뀔 수 있어 공정 안정성이 떨어지는 구간.":
        "Boundary between droplet and thread mode. Small changes can flip the mode, so process "
        "stability is poor here.",
})
EN.update({
    "팁→가스 영역 낙하 거리 (mm)": "Tip-to-gas-zone fall distance (mm)",
    "가스·압력차 추가 가속 (m/s²)": "Extra acceleration from gas drag + ΔP (m/s²)",
    "넥 Weber 수가 낮아 팁에서 연속 기둥이 유지되지 못하고 물방울로 똑똑 떨어지는 경향. 분무가 불균일해져 입도분포가 넓어지고 굵은 입자/위성분말 위험이 큼.":
        "Low neck Weber number: the tip cannot sustain a continuous column, so the melt drips as droplets. "
        "Atomization becomes uneven, the size distribution widens and the risk of coarse particles/satellites grows.",
    "팁에서는 연속류가 나오지만 낙하 거리가 길어 가스 영역에 닿기 전에 모세관 불안정성으로 끊어져 물방울이 되는 경향. 낙하 거리를 줄이거나 가스·압력차 가속을 키우면 실 쪽으로 갑니다.":
        "A continuous stream leaves the tip, but the fall is long, so capillary instability breaks it into droplets "
        "before it reaches the gas zone. Shorten the fall distance or raise the gas/ΔP acceleration to move toward thread mode.",
    "넥 Weber 수가 경계에 있어 작은 조건 변화에도 모드가 바뀔 수 있는 구간. 공정 안정성이 떨어집니다.":
        "Neck Weber number is at the boundary: small changes can flip the mode, so process stability is poor here.",
    "넥이 연속 기둥을 유지하고 낙하 신장을 버텨 가스 영역까지 실처럼 도착하는 경향. 균일한 분무에 유리한 영역.":
        "The neck sustains a continuous column and survives the fall stretching, arriving at the gas zone as a thread. "
        "This is the favourable region for uniform atomization.",
    "용탕 유량이 없어 류가 형성되지 않습니다.":
        "No melt flow, so no stream forms.",
})
TERM.update({
    "droplet (물방울 모드)": "droplet",
    "thread (실 모드)": "thread",
    "transition (전이 영역)": "transition",
    "물방울 모드 (We": "droplet mode (We",
    "넥 Weber 수": "neck Weber number",
    "넥 지름": "neck diameter",
    "넥 We": "neck We",
    "가스 영역": "gas zone",
    "펜던트 한 방울": "pendant drop",
    "실(연속류) 모드": "thread (continuous) mode",
})
_TERM_KEYS = None

EN.update({
    "316L 스테인리스": "316L stainless steel",
    "저합금강 (Fe-2Ni)": "Low-alloy steel (Fe-2Ni)",
    "Ar (아르곤)": "Ar (argon)",
    "N2 (질소)": "N2 (nitrogen)",
    "He (헬륨)": "He (helium)",
    "금속 온도 (°C)": "Metal temperature (°C)",
})
TERM.update({
    "초크(음속) 상태": "choked (sonic)",
    "아음속 상태": "subsonic",
    "초음속 제트": "supersonic jet",
    "평탄": "flat",
    "둥근": "rounded",
    "샤프": "sharp",
    "계산 GMR": "Computed GMR",
})
_TERM_KEYS = None

TERM.update({
    "봉 형상 따라가기 (콘 밀착)": "follow rod profile",
    "원뿔 (선형 테이퍼)": "cone (linear taper)",
    "곡선 테이퍼 (지수)": "curved taper (exponential)",
    "직선": "straight",
    "원뿔": "cone",
})
_TERM_KEYS = None

TERM.update({"원형": "round", "직사각형": "rectangular"})
_TERM_KEYS = None

EN.update({
    "목표 입도 하한 (µm)": "Target lower size (µm)",
    "목표 입도 상한 (µm)": "Target upper size (µm)",
    "미분 기준 (µm)": "Fines threshold (µm)",
})
_TERM_KEYS = None

EN.update({
    "연동 사용 — 이 탭의 코일 설정을 앞 탭에 적용":
        "Link — apply this tab's coil settings to the earlier tabs",
    "켜면 봉 지름·공급 속도·코일 출력/효율/턴수/길이/내경·용탕 생성량·팁 온도가 "
    "2 봉·코일, 1·3 탭 용탕 유량, 5 수율, 복사열 탭으로 자동 전달됩니다. "
    "끈 상태에서는 각 탭이 자기 값을 그대로 씁니다.":
        "When on, rod diameter, feed rate, coil power/efficiency/turns/length/inner diameter, "
        "melt rate and tip temperature are pushed to 2 Rod & Coil, the melt flow inputs of "
        "1 Process and 3 Nozzle, 5 Yield and the Radiation tab. When off, each tab keeps its own values.",
    "연동 중 — 2 봉·코일, 1·3 탭 용탕 유량, 5 수율, 복사열 탭에 이 값이 적용됩니다.":
        "Linked — these values are applied to 2 Rod & Coil, the melt flow inputs of 1 & 3, "
        "5 Yield and the Radiation tab.",
    "코일이 금속을 녹여 만든 용탕의 온도(가정값)입니다. 녹는점(액상선)이 아니라 점도·표면장력·용탕 생성량을 "
    "계산할 때 쓰는 온도입니다.":
        "Assumed temperature of the melt the coil produces. This is not the melting point "
        "(liquidus); it is the temperature used for viscosity, surface tension and melt-rate estimates.",
})
TERM.update({
    "녹는점(액상선) ": "Melting point (liquidus) ",
    " °C · 팁 표면 ": " °C · tip surface ",
    " °C → 여유 ": " °C → margin ",
    " °C — 팁 표면이 액상선 이상이면 용탕이 생깁니다.":
        " °C — melt forms once the tip surface is at or above the liquidus.",
})
_TERM_KEYS = None


# ---------------------------------------------------------------- linking UI
EN.update({
    "연동 사용 — 앞 공정 값과 자동으로 연동":
        "Link — follow the upstream process values automatically",
    "켜면 1 공정·2 봉·코일의 값이 모든 탭에 자동으로 들어가고, 이 탭의 봉 지름·"
    "공급 속도·코일 출력/효율은 2 봉·코일 값을 그대로 표시합니다. "
    "연동된 값을 직접 고치려 하면 연동 해제를 물어봅니다. "
    "끄면 각 탭이 자기 값을 그대로 씁니다.":
        "When on, values from 1 Process and 2 Rod & Coil flow into every tab, and the rod "
        "diameter, feed rate, coil power and efficiency shown here are copied from 2 Rod & Coil. "
        "Editing a linked value asks whether to unlink it. When off, each tab keeps its own values.",
    "이 값은 앞 탭에서 연동된 값입니다. 직접 입력하려면 연동을 해제해야 합니다.":
        "This value is linked from an earlier tab. Unlink it to enter your own value.",
    "연동 해제하고 이 값 사용": "Unlink and use this value",
    "연동값으로 되돌리기": "Restore the linked value",
    "연동 다시 사용": "Link again",
    "연동 해제됨 — 이 탭에서 직접 입력하는 값입니다.":
        "Unlinked — this tab now uses its own value.",
    "연동이 꺼져 있을 때만 이 탭의 값을 씁니다.": "Used only while linking is off.",
    "코일이 녹여 낸 용탕의 온도입니다. 2 봉·코일과 4 분말 품질 탭이 "
    "이 값을 그대로 받아 씁니다.":
        "Melt temperature produced by the coil. 2 Rod & Coil and 4 Powder Quality "
        "use this exact value.",
    "2 봉·코일의 봉 지름·공급 속도·코일 출력에서 계산된 값이 "
    "자동으로 들어옵니다. 직접 입력하려면 연동을 해제하세요.":
        "Filled automatically from the rod diameter, feed rate and coil power in 2 Rod & Coil. "
        "Unlink it to enter your own value.",
    "코일 가열 보기의 팁 표면 온도가 연동됩니다.":
        "Linked from the tip surface temperature in the coil heating view.",
})
TERM.update({
    "봉 Ø": "Rod Ø",
    " mm · 출력 ": " mm · power ",
    " kW · 효율 ": " kW · efficiency ",
    " · 공급 ": " · feed ",
    " mm/s — 2 봉·코일에서 연동됩니다.": " mm/s — linked from 2 Rod & Coil.",
    "코일 ": "Coil ",
    "턴 · 길이 ": " turns · length ",
    " mm · 상부 ": " mm · top ",
    " / 하부 ": " / bottom ",
    " mm — `코일 가열 보기`의 위치·간극·턴수에서 자동 계산됩니다.":
        " mm — computed from the coil position, gap and turns in the coil heating view.",
})

EN.update({
    "2(b). 코일 형상 — 봉 팁 콘·코일 단면과 가열 계산":
        "2(b). Coil geometry — tip cone, coil cross-section and heating",
    "켜면 값이 모든 탭에서 양방향으로 공유됩니다. 여기서 고친 봉 지름·코일 출력·"
    "코일 형상도 1 공정 계산과 용탕 유량, 복사열에 바로 반영됩니다. "
    "끄면 각 탭이 자기 값을 그대로 씁니다.":
        "When on, values are shared in both directions across all tabs. The rod diameter, "
        "coil power and coil geometry set here also update the 1 Process calculation, the melt "
        "rate and the radiation tab. When off, each tab keeps its own values.",
})

EN.update({
    "코일 가열 보기의 팁 표면 온도가 연동됩니다.":
        "Linked from the tip surface temperature in 2(b) coil geometry.",
})
TERM.update({
    " mm — `2(b) 코일 형상`의 위치·간극·턴수에서 자동 계산됩니다.":
        " mm — computed from the coil position, gap and turns in 2(b).",
})

EN.update({
    "2(c). 절단면 보기 — 팁 기준 위치에서 XY / XZ / YZ":
        "2(c). Cross-sections — XY / XZ / YZ at a position measured from the tip",
    "기준점을 금속 팁(0 mm)에서 위로 옮겨가며 그 높이의 단면을 봅니다. "
    "계산은 축대칭(r, z) 모델이라 XZ·YZ 단면은 같게 나옵니다 "
    "(실제 나선 코일에서는 턴 위치 때문에 원주 방향으로 조금 달라질 수 있습니다).":
        "Move the reference point upward from the metal tip (0 mm) to inspect the "
        "cross-section at that height. The model is axisymmetric (r, z), so the XZ and YZ "
        "sections are identical (a real helical coil varies slightly around the circumference).",
    "절단면": "Cross-section plane",
    "XY (축에 수직, 단면)": "XY (normal to the axis)",
    "XZ (축 포함, 세로)": "XZ (axial, vertical)",
    "YZ (축 포함, 세로)": "YZ (axial, vertical)",
    "팁 기준 위치 (mm) — 0 = 팁 끝, 위로 갈수록 증가":
        "Position from tip (mm) — 0 = tip end, increasing upward",
    "금속 끝(팁)을 0으로 두고 위로 올라가며 단면을 확인합니다. "
    "코일 시작/끝 위치와 같은 기준입니다.":
        "The metal tip end is 0; move upward to inspect sections. "
        "Same reference as the coil start/end positions.",
    "중심 온도": "Centre temperature",
    "표면 − 액상선": "Surface − liquidus",
    "용융 반경 (액상선)": "Molten radius (liquidus)",
    "기준 위치": "Reference position",
})
TERM.update({
    "봉 길이 ": "Rod length ",
    " mm (팁 기준)": " mm (from tip)",
    "이 높이의 봉 반경 ": "Rod radius at this height ",
    " mm · 코일 반경 ": " mm · coil radius ",
    " mm (팁 기준 ": " mm (from tip ",
    "XY 단면 — 팁 기준 ": "XY section — from tip ",
    " mm (봉 상단에서 ": " mm (from rod top ",
    " 단면 — 기준 위치 팁 기준 ": " section — reference from tip ",
    "깊이 ": "depth ",
})

EN.update({
    '2(b). 코일 형상 — 봉 팁 콘·코일 단면과 가열 계산':
        "2(b). Coil geometry — tip cone, coil cross-section and heating",
})
TERM.update({
    "팁 기준 ": "from tip ",
    "봉 상단에서 ": "from rod top ",
})

EN.update({
    "액상 영역 (T ≥ 액상선)": "Molten zone (T ≥ liquidus)",
    "액상선": "Liquidus",
    "코일": "Coil",
})

EN.update({
    "액상 영역은 액상선(등온선) 기준으로만 칠해집니다. 이 모델은 잠열과 용융 경계를 "
    "넣지 않아 표면 온도가 액상선보다 높게(과대평가) 나올 수 있습니다.":
        "The molten zone is shaded strictly by the liquidus isotherm. This model has no "
        "latent heat or melting front, so the surface temperature can overshoot the liquidus.",
})

EN.update({
    "코일 턴": "Coil turns",
})
TERM.update({
    "노란 원 ": "Yellow circles ",
    "개 = 코일 ": " = coil ",
    "턴 (턴 간격 ": " turns (pitch ",
    " mm). 노란 점선은 코일 내경 경로입니다.": " mm). The dotted line is the coil inner-radius path.",
})

EN.update({
    "코일 결합 모델": "Coil coupling model",
    "반경비² (기존)": "Radius ratio² (existing)",
    "간극 기준 (신규)": "Gap-based (new)",
    "기존 방식은 결합을 (봉 반경 / 코일 반경)² 으로 봅니다 — 가는 팁에서는 "
    "결합이 급격히 약해져 꼭지점이 덜 녹습니다. "
    "간극 기준은 원주 2πR 에 간극 효율 1/(1+(간극/코일 반경)²) 을 곱해, "
    "표면적이 있는 만큼은 가열되도록 봅니다. 결과는 아래에 나란히 표시됩니다.":
        "The existing model weights coupling by (rod radius / coil radius)² — on a thin tip "
        "the coupling collapses, so the apex melts less. The gap-based model multiplies the "
        "circumference 2πR by a gap efficiency 1/(1+(gap/coil radius)²), so the surface area "
        "that exists is actually heated. Both results are shown below.",
})
TERM.update({
    "결합 모델 비교 — ": "Coupling model comparison — ",
    "팁 표면 ": "tip surface ",
    "용융 캡 ": "melt cap ",
})

EN.update({
    "봉 길이 (mm)": "Rod length (mm)",
    "팁 끝부터 봉 상단까지의 길이입니다. 코일 위치(팁 기준)와 이 길이로 "
    "그림에 보이는 봉 구간이 정해집니다.":
        "Length from the tip end to the rod top. Together with the coil position "
        "(measured from the tip) this sets the rod span shown in the figure.",
    "위쪽 잘라내기 (봉 상단에서, mm)": "Crop from rod top (mm)",
    "그림에서 봉 상단부터 이만큼 잘라냅니다. 0이면 봉 전체가 보입니다.":
        "Cut this much from the rod top in the figure. 0 shows the whole rod.",
    "코일 시작 위치가 봉 상단보다 위입니다 — 봉 길이를 늘리거나 코일을 내리세요.":
        "The coil start is above the rod top — increase the rod length or lower the coil.",
})

EN.update({
    "두 모델 나란히 비교": "Both models side by side",
    "**결합 모델 비교 — 같은 조건, 두 모델**":
        "**Coupling model comparison — same conditions, both models**",
})

EN.update({
    "자계 강화 (신규)": "Field-strengthened (new)",
    "축방향 전도 포함": "Include axial conduction",
    "축방향 전도": "axial conduction",
    "기준과 비교": "Compare with baseline",
    "기준": "baseline",
    "**기준과 비교 — 같은 조건**": "**Baseline comparison — same conditions**",
    "결합 모델은 셋 중 하나만 선택합니다 (동시에 적용하지 않음). "
    "반경비²는 결합을 (봉 반경 / 코일 반경)² 으로 봅니다 — 가는 팁에서는 "
    "결합이 급격히 약해져 꼭지점이 덜 녹습니다. "
    "간극 기준은 원주 2πR 에 간극 효율 1/(1+(간극/코일 반경)²) 을 곱해, "
    "표면적이 있는 만큼은 가열되도록 봅니다. "
    "자계 강화는 단위 길이당 흡수 전력을 원주 × 자계² 으로 봅니다 "
    "(자계 ∝ 1/코일 반경) — 코일이 좁아질수록 표면 가열이 세집니다.":
        "Select exactly one coupling model (they are not combined). "
        "Radius ratio² weights coupling by (rod radius / coil radius)² — on a thin tip "
        "the coupling collapses, so the apex melts less. Gap-based multiplies the "
        "circumference 2πR by a gap efficiency 1/(1+(gap/coil radius)²), so the surface area "
        "that exists is actually heated. Field-strengthened weights absorbed power per unit "
        "length by circumference × field² (field ∝ 1/coil radius) — surface heating "
        "strengthens as the coil narrows.",
    "축방향 열전도를 에너지 수지에 추가합니다. 봉을 따라 열이 퍼져 코일 위쪽 찬 봉이 "
    "예열되지만, 팁 온도는 용융 구간에 묶여 거의 변하지 않습니다. 계산이 다소 느려집니다.":
        "Adds axial heat conduction to the energy balance. Heat spreads along the rod and "
        "preheats the cold shank above the coil, but the tip temperature barely changes "
        "because it is pinned on the melting plateau. Computation is somewhat slower.",
    "왼쪽은 기준(반경비², 축방향 전도 OFF), 오른쪽은 현재 선택(결합 모델 + 축방향 전도)을 "
    "나란히 표시합니다.":
        "Shows the baseline (radius ratio², axial conduction OFF) on the left and the current "
        "selection (coupling model + axial conduction) on the right, side by side.",
})

EN.update({
    "액상선 이상<br>깊이 %{y:.1f} mm<br>표면 온도 %{customdata:.0f} °C<extra></extra>":
        "Above liquidus<br>Depth %{y:.1f} mm"
        "<br>Surface temperature %{customdata:.0f} °C<extra></extra>",
})
