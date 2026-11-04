# -*- coding: utf-8 -*-
"""Physics core for the simplified EIGA atomizer simulator.

Design rule: every formula is a named, published or textbook relation, and
every simplification is labelled where it is used. Nothing here is CFD.
The point of the program is to find RULES and LIMITS (parameter sweeps,
regime boundaries), not to reproduce one ANSYS run.

Key relations
-------------
- Lubanska correlation (Lubanska 1970, as cited in current reviews):
    D50 / D = K * sqrt( (nu_m / nu_g) * (1 / We) * (1 + M / A) )
  with We built on MELT density, as in Lubanska's original form:
    We = rho_m * v_gas^2 * D / sigma
  K is an equipment-dependent constant (nozzle geometry). Default 40 is a
  literature-typical value; calibrate it against your own equipment data.
- Gas-atomized powders are approximately lognormally distributed with a
  geometric standard deviation sigma_g around 2.0.
- Choked (sonic) gas flow through the nozzle throat when the supply /
  chamber pressure ratio exceeds the critical ratio ((gamma+1)/2)^(gamma/(gamma-1)).
"""

import math

from materials import R_UNIVERSAL


# ---------------------------------------------------------------- gases
def gas_density(P_Pa, T_K, M):
    """Ideal-gas density (kg/m3)."""
    return P_Pa * M / (R_UNIVERSAL * T_K)


def gas_specific_R(M):
    return R_UNIVERSAL / M


def sound_speed(gamma, R_specific, T_K):
    return math.sqrt(gamma * R_specific * T_K)


def critical_pressure_ratio(gamma):
    return ((gamma + 1.0) / 2.0) ** (gamma / (gamma - 1.0))


def gas_jet_velocity(P0_Pa, Pc_Pa, T0_K, gamma, R_specific):
    """Estimate the gas jet velocity at the nozzle exit (m/s).

    Choked (sonic) flow if P0/Pc exceeds the critical ratio; otherwise a
    Bernoulli-type estimate. This is an approximation, not a nozzle CFD.
    Returns (velocity, is_choked).
    """
    if Pc_Pa <= 0:
        Pc_Pa = 1.0e5
    ratio = P0_Pa / Pc_Pa
    crit = critical_pressure_ratio(gamma)
    if ratio >= crit:
        # Throat temperature under isentropic expansion.
        T_star = T0_K * 2.0 / (gamma + 1.0)
        return sound_speed(gamma, R_specific, T_star), True
    # Subsonic: Bernoulli estimate with the chamber density.
    rho_c = Pc_Pa / (R_specific * T0_K)
    return math.sqrt(2.0 * max(P0_Pa - Pc_Pa, 0.0) / rho_c), False


def gas_mass_flow_choked(P0_Pa, T0_K, area_m2, Cd, gamma, R_specific):
    """Choked mass flow through an orifice (kg/s), standard formula."""
    if area_m2 <= 0:
        return 0.0
    term = (2.0 / (gamma + 1.0)) ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))
    return Cd * area_m2 * P0_Pa * math.sqrt(gamma / (R_specific * T0_K)) * term


# ---------------------------------------------------------------- melts
def melt_viscosity(alloy, T_K, B=4000.0):
    """Andrade-type temperature dependence, anchored at the alloy's T_ref.

    mu(T) = mu_ref * exp(B * (1/T - 1/T_ref)). B ~ 4000 K is typical for
    liquid metals; the app exposes it as an adjustable parameter.
    """
    return alloy["mu_ref"] * math.exp(B * (1.0 / T_K - 1.0 / alloy["T_ref"]))


def melt_surface_tension(alloy, T_K):
    return alloy["sigma_ref"] + alloy["dsigma_dT"] * (T_K - alloy["T_ref"])


def melt_kinematic_viscosity(alloy, T_K):
    return melt_viscosity(alloy, T_K) / alloy["rho_melt"]


# ---------------------------------------------------------------- atomization
def weber_melt(rho_m, v_gas, D_m, sigma):
    """Lubanska-form Weber number (melt density), dimensionless."""
    if sigma <= 0 or D_m <= 0:
        return 0.0
    return rho_m * v_gas ** 2 * D_m / sigma


def weber_gas(rho_g, v_gas, D_m, sigma):
    """Aerodynamic Weber number (gas density), for the nozzle interaction."""
    if sigma <= 0 or D_m <= 0:
        return 0.0
    return rho_g * v_gas ** 2 * D_m / sigma


def lubanska_D50(K, D_m, nu_m, nu_g, We, M_dot, A_dot):
    """Mass-median particle diameter (m) from the Lubanska correlation."""
    if We <= 0 or nu_g <= 0 or D_m <= 0:
        return float("nan")
    return K * D_m * math.sqrt((nu_m / nu_g) * (1.0 / We) * (1.0 + M_dot / A_dot))


# ---------------------------------------------------------------- PSD (lognormal)
def _phi(z):
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def lognormal_cdf(d, D50, sigma_g):
    """Mass fraction finer than diameter d (m)."""
    if d <= 0 or D50 <= 0 or sigma_g <= 1.0:
        return 0.0
    return _phi(math.log(d / D50) / math.log(sigma_g))


def lognormal_D_at(D50, sigma_g, frac):
    """Diameter (m) at cumulative mass fraction frac (0..1)."""
    from statistics import NormalDist
    if frac <= 0.0:
        return 0.0
    if frac >= 1.0:
        return float("inf")
    z = NormalDist().inv_cdf(frac)
    return D50 * (sigma_g ** z)


def D_values(D50, sigma_g):
    """(D10, D50, D90) in metres from the lognormal model."""
    return (
        lognormal_D_at(D50, sigma_g, 0.10),
        D50,
        lognormal_D_at(D50, sigma_g, 0.90),
    )


def yield_in_range(D50, sigma_g, d_min, d_max):
    """Mass fraction inside [d_min, d_max] (m)."""
    if d_max <= d_min:
        return 0.0
    return lognormal_cdf(d_max, D50, sigma_g) - lognormal_cdf(d_min, D50, sigma_g)


def mean_diameter_in_range(D50, sigma_g, d_min, d_max):
    """Mass-weighted mean diameter (m) of the fraction inside [d_min, d_max].

    E[d | d_min <= d <= d_max] for the lognormal mass distribution:
    exp(mu + sigma^2/2) * [Phi(z_hi) - Phi(z_lo)] / mass fraction in range,
    with z = (ln d - mu - sigma^2) / sigma.
    """
    if D50 <= 0 or sigma_g <= 1.0 or d_max <= d_min:
        return 0.0
    mu = math.log(D50)
    sig = math.log(sigma_g)
    frac = yield_in_range(D50, sigma_g, d_min, d_max)
    if frac <= 0.0:
        return 0.0
    z_lo = 0.0 if d_min <= 0 else _phi((math.log(d_min) - mu - sig ** 2) / sig)
    z_hi = _phi((math.log(d_max) - mu - sig ** 2) / sig)
    return math.exp(mu + 0.5 * sig ** 2) * (z_hi - z_lo) / frac


# ---------------------------------------------------------------- rod & coil (EIGA)
def melt_rate_from_power(P_kW, efficiency, alloy, T_melt_K, T_feed_K=300.0):
    """Melt mass rate (kg/s) from a power balance.

    eta * P = m_dot * (cp * (T_melt - T_feed) + Lf).
    """
    energy_per_kg = alloy["cp"] * (T_melt_K - T_feed_K) + alloy["Lf"]
    if energy_per_kg <= 0:
        return 0.0
    return efficiency * P_kW * 1000.0 / energy_per_kg


def stream_diameter(m_dot, rho, velocity):
    """Melt stream diameter (m) from continuity, m_dot = rho * A * v."""
    if rho <= 0 or velocity <= 0:
        return 0.0
    return math.sqrt(4.0 * m_dot / (math.pi * rho * velocity))


def tip_velocity(v_axial, rpm, rod_radius_m):
    """Total tip speed: axial fall plus the rotational (tangential) part."""
    omega = rpm * 2.0 * math.pi / 60.0
    v_tan = omega * rod_radius_m
    return math.sqrt(v_axial ** 2 + v_tan ** 2)


def detachment_mode(We_tip, lo=4.0, hi=12.0):
    """Heuristic v1 regime for melt detachment at the rod tip.

    Low tip Weber number -> the melt hangs and detaches as DROPLETS
    (dripping: broad PSD, uniformity risk). High tip Weber number ->
    a thin continuous THREAD (jetting: uniform atomization).
    Thresholds are adjustable and must be calibrated against experience.
    Returns (mode, explanation).
    """
    if We_tip < lo:
        return ("droplet (물방울 모드)",
                "팁 Weber 수가 낮아 용탕이 물방울로 똑똑 떨어지는 경향. "
                "분무가 불균일해져 입도분포가 넓어지고 굵은 입자/위성분말 위험이 큼.")
    if We_tip > hi:
        return ("thread (실 모드)",
                "팁 Weber 수가 높아 용탕이 가늘게 실처럼 이어지며 떨어지는 경향. "
                "균일한 분무에 유리한 영역.")
    return ("transition (전이 영역)",
            "물방울 모드와 실 모드의 경계. 작은 조건 변화에도 모드가 바뀔 수 있어 "
            "공정 안정성이 떨어지는 구간.")


def stream_detachment(m_dot, rho, sigma, R_tip, fall_m, a_eff, C_break=30.0):
    """Falling-stream detachment model (v2) for the rod tip.

    Replaces the v1 tip-exit Weber criterion, which treated the tip as a
    nozzle (v = m_dot / (rho * A_tip)). A melting rod tip is not a nozzle:
    the melt pools at the tip and detaches through a pendant neck, and a
    thread forms only if that neck survives the fall to the gas zone.

    Stage 1 — neck at detachment. The stream leaves the tip through a neck
    whose diameter follows from the mass balance at the capillary velocity
    scale v_cap = sqrt(sigma / (rho * R_tip)):
        d_neck = sqrt(4 * m_dot / (pi * rho * v_cap))
    The neck Weber number We_neck = rho * v_cap^2 * d_neck / sigma reduces
    to d_neck / R_tip. Below ~2 the neck cannot sustain a continuous column
    and the tip drips (pendant drops, Tate scale ~ 2 * pi * R * sigma / g).

    Stage 2 — fall stretching. Over the tip-to-gas-zone distance the stream
    accelerates (gravity + gas drag + chamber dP suction, lumped into a_eff)
    and thins by continuity:
        v_gas = sqrt(v_cap^2 + 2 * a_eff * fall_m)
        d_gas = d_neck * sqrt(v_cap / v_gas)
        t_fall = (v_gas - v_cap) / a_eff

    Stage 3 — survival. Rayleigh-Plateau breakup time at the gas-zone
    diameter, t_b = C_break * sqrt(rho * (d_gas / 2)^3 / sigma).
    C_break ~ 30 is the undisturbed-jet literature scale
    (ln(R / delta0) / 0.34); a disturbed jet breaks sooner, so this is the
    optimistic end. Thresholds (neck We 2 / 4, C_break) are heuristics and
    still need calibration against ALD operating records.

    Returns a dict with the numbers, the mode label (same "droplet" /
    "transition" / "thread" prefixes the coil view's drawing logic keys on),
    the gate that decided it, and a short explanation.
    """
    g = 9.81
    sig = max(sigma, 0.1) if sigma is not None else 0.1
    R_eff = max(R_tip, 0.0005)  # sharp tip (R = 0) behaves like a 1 mm neck scale
    if m_dot is None or m_dot <= 0 or rho <= 0:
        return {"mode": "droplet (물방울 모드)", "gate": "no-flow",
                "explanation": "용탕 유량이 없어 류가 형성되지 않습니다.",
                "v_cap": 0.0, "d_neck": 0.0, "We_neck": 0.0,
                "v_gas": 0.0, "d_gas": 0.0, "t_fall": 0.0, "t_break": 0.0,
                "tate_d": 0.0}
    v_cap = math.sqrt(sig / (rho * R_eff))
    d_neck = math.sqrt(4.0 * m_dot / (math.pi * rho * v_cap))
    We_neck = d_neck / R_eff
    a = a_eff if a_eff and a_eff > 0 else 0.0
    fall = max(fall_m, 0.0)
    if a > 0.0 and fall > 0.0:
        v_gas = math.sqrt(v_cap ** 2 + 2.0 * a * fall)
        t_fall = (v_gas - v_cap) / a
    else:
        v_gas = v_cap
        t_fall = 0.0
    d_gas = d_neck * math.sqrt(v_cap / v_gas) if v_gas > 0 else d_neck
    t_break = C_break * math.sqrt(rho * (d_gas / 2.0) ** 3 / sig)
    m_tate = 2.0 * math.pi * R_eff * sig / g
    tate_d = (6.0 * m_tate / (math.pi * rho)) ** (1.0 / 3.0) if rho > 0 else 0.0
    if We_neck < 2.0:
        return {"mode": "droplet (물방울 모드)", "gate": "tip",
                "explanation": "넥 Weber 수가 낮아 팁에서 연속 기둥이 유지되지 못하고 "
                "물방울로 똑똑 떨어지는 경향. 분무가 불균일해져 입도분포가 넓어지고 "
                "굵은 입자/위성분말 위험이 큼.",
                "v_cap": v_cap, "d_neck": d_neck, "We_neck": We_neck,
                "v_gas": v_gas, "d_gas": d_gas, "t_fall": t_fall,
                "t_break": t_break, "tate_d": tate_d}
    if t_fall > t_break:
        return {"mode": "droplet (물방울 모드)", "gate": "fall",
                "explanation": "팁에서는 연속류가 나오지만 낙하 거리가 길어 가스 영역에 닿기 전에 "
                "모세관 불안정성으로 끊어져 물방울이 되는 경향. 낙하 거리를 줄이거나 "
                "가스·압력차 가속을 키우면 실 쪽으로 갑니다.",
                "v_cap": v_cap, "d_neck": d_neck, "We_neck": We_neck,
                "v_gas": v_gas, "d_gas": d_gas, "t_fall": t_fall,
                "t_break": t_break, "tate_d": tate_d}
    if We_neck < 4.0:
        return {"mode": "transition (전이 영역)", "gate": "marginal",
                "explanation": "넥 Weber 수가 경계에 있어 작은 조건 변화에도 모드가 바뀔 수 있는 구간. "
                "공정 안정성이 떨어집니다.",
                "v_cap": v_cap, "d_neck": d_neck, "We_neck": We_neck,
                "v_gas": v_gas, "d_gas": d_gas, "t_fall": t_fall,
                "t_break": t_break, "tate_d": tate_d}
    return {"mode": "thread (실 모드)", "gate": "survived",
            "explanation": "넥이 연속 기둥을 유지하고 낙하 신장을 버텨 가스 영역까지 실처럼 도착하는 경향. "
            "균일한 분무에 유리한 영역.",
            "v_cap": v_cap, "d_neck": d_neck, "We_neck": We_neck,
            "v_gas": v_gas, "d_gas": d_gas, "t_fall": t_fall,
            "t_break": t_break, "tate_d": tate_d}


def apply_coil_taper(d0_m, v0, D_top_m, D_bottom_m, q=0.5):
    """Funnel-coil focusing (v1 model).

    A coil tapering from inner diameter D_top to D_bottom funnels the
    melt toward the axis. The stream diameter shrinks as
        d_eff = d0 * (D_bottom / D_top) ** q
    and by continuity the velocity rises as v_eff = v0 * (d0 / d_eff) ** 2.
    Because We ~ v^2 * d, the Weber number scales as 1/d^3 at fixed mass
    flow, so focusing pushes the tip toward thread (jetting) mode.
    q is a calibration exponent (0 = no focusing, 1 = full geometric
    funneling); default 0.5. A bottom wider than the top widens the
    stream and lowers We (same formula, opposite direction).
    Returns (d_eff, v_eff).
    """
    if D_top_m <= 0 or D_bottom_m <= 0 or d0_m <= 0 or v0 <= 0:
        return d0_m, v0
    ratio = D_bottom_m / D_top_m
    d_eff = d0_m * (ratio ** q)
    v_eff = v0 * (d0_m / d_eff) ** 2 if d_eff > 0 else v0
    return d_eff, v_eff


def relative_velocity(v_gas, v_melt, angle_deg):
    """Relative speed between gas jet and falling melt (m/s).

    angle_deg is the gas jet angle from the downward vertical (melt
    direction): 0 = parallel co-flow (|v_g - v_m|), 90 = cross-flow,
    180 = directly opposing (v_g + v_m). From the law of cosines.
    """
    th = math.radians(angle_deg)
    v2 = v_gas ** 2 + v_melt ** 2 - 2.0 * v_gas * v_melt * math.cos(th)
    return math.sqrt(max(v2, 0.0))


def annular_slit_area(D_pitch_m, width_m):
    """Gas exit area (m2) of an annular slit: circumference x width."""
    if D_pitch_m <= 0 or width_m <= 0:
        return 0.0
    return math.pi * D_pitch_m * width_m


def holes_area(n_holes, d_hole_m):
    """Gas exit area (m2) of N discrete round holes."""
    if n_holes <= 0 or d_hole_m <= 0:
        return 0.0
    return n_holes * math.pi * d_hole_m ** 2 / 4.0


def jet_coverage(n_holes, d_hole_m, D_pitch_m):
    """Fraction of the jet-ring circumference covered by discrete holes.

    1.0 = full ring coverage (like an annular slit). Below ~0.9 the gaps
    between jets can leave parts of the melt stream weakly atomized,
    which hurts uniformity. Annular slits have coverage 1.0 by definition.
    """
    if D_pitch_m <= 0:
        return 0.0
    return min(1.0, n_holes * d_hole_m / (math.pi * D_pitch_m))


def cross_flow_velocity(v_gas, angle_deg):
    """Transverse (breakup-driving) gas velocity component (m/s).

    The gas jet angle is measured from the melt axis: the transverse
    component v_gas * sin(angle) is what crosses the melt stream and
    drives breakup. The axial component accelerates the melt instead.
    At 0 deg (parallel co-flow) there is no transverse breakup, only
    shear breakup, which v1 does not model.
    """
    return v_gas * math.sin(math.radians(angle_deg))


def mach_from_area_ratio(A_ratio, gamma):
    """Supersonic Mach number from the isentropic area ratio A/A*.

    A/A* = (1/M) * [(2/(gamma+1)) * (1 + (gamma-1)/2 * M^2)]
           ^((gamma+1)/(2*(gamma-1))).
    Solved by bisection on the supersonic branch (M > 1). Returns 1.0
    for A_ratio <= 1 (no supersonic expansion possible).
    """
    if A_ratio <= 1.0:
        return 1.0

    def area_ratio(M):
        term = (2.0 / (gamma + 1.0)) * (1.0 + (gamma - 1.0) / 2.0 * M ** 2)
        return (1.0 / M) * term ** ((gamma + 1.0) / (2.0 * (gamma - 1.0)))

    lo, hi = 1.0, 5.0
    for _ in range(100):
        mid = 0.5 * (lo + hi)
        if area_ratio(mid) < A_ratio:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def supersonic_exit(P0_Pa, T0_K, M, gamma, R_specific):
    """Isentropic exit state at Mach M. Returns (v, T, P)."""
    denom = 1.0 + (gamma - 1.0) / 2.0 * M ** 2
    T_exit = T0_K / denom
    P_exit = P0_Pa / denom ** (gamma / (gamma - 1.0))
    a_exit = math.sqrt(gamma * R_specific * T_exit)
    return M * a_exit, T_exit, P_exit


def oxide_oxygen_content(D_m, rho_m, t_ox_m, rho_ox=5000.0, o_frac=0.3):
    """Order-of-magnitude oxygen content (wt%) from a surface oxide layer.

    Assumes a uniform oxide shell of thickness t_ox on spherical powder:
    O wt% = (6 / (rho_m * D)) * t_ox * rho_ox * o_frac * 100.
    Scales as 1/D: finer powder is more oxidation-sensitive. This is an
    estimate, not a measurement: real oxidation also depends on exposure
    time, temperature history and chamber O2 level.
    Returns (wt_percent, ppm).
    """
    if D_m <= 0:
        return 0.0, 0.0
    wt = (6.0 / (rho_m * D_m)) * t_ox_m * rho_ox * o_frac * 100.0
    return wt, wt * 10000.0


def spheroidization_time(mu, d_m, sigma):
    """Viscocapillary spheroidization timescale (s): t ~ mu * d / sigma.

    Surface tension pulls a deformed droplet spherical against viscous
    resistance. If this time is much shorter than the cooling time, the
    droplet freezes spherical; if comparable or longer, irregular shapes
    survive. Oxide films can block spheroidization even when this time
    is short, which is why the oxidation section matters too.
    """
    if sigma <= 0:
        return float("inf")
    return mu * d_m / sigma


def skin_depth(rho_e, freq_hz, mu_r=1.0):
    """Electromagnetic skin depth (m): delta = sqrt(2*rho_e / (omega*mu)).

    High-frequency current heats only a surface layer of this thickness.
    mu_r = 1 assumes the hot, non-magnetic state (above the Curie point).
    Magnetic steel below Curie has mu_r >> 1 and a much thinner skin.
    """
    mu0 = 4.0 * math.pi * 1e-7
    if freq_hz <= 0:
        return float("inf")
    return math.sqrt(2.0 * rho_e / (2.0 * math.pi * freq_hz * mu0 * mu_r))


def coil_radius_at(z, z1, z2, r_top, r_bot, p=1.0):
    """Coil inner radius (m) at height z for a tapered coil.

    r(z) = r_top + (r_bot - r_top) * f**p, f = (z - z1) / (z2 - z1).
    p = 1 is a linear cone. p > 1 keeps the coil wide for most of the
    height and narrows sharply near the bottom (tip-focused). p < 1
    narrows quickly near the top. Straight coil: r_top == r_bot.
    """
    if z2 <= z1:
        return r_bot
    f = (z - z1) / (z2 - z1)
    f = min(max(f, 0.0), 1.0)
    return r_top + (r_bot - r_top) * (f ** p)


def rod_descent_temperature(z, q_prime, v_feed, rho, A, cp, T_feed,
                            T_melt, Lf, R, h_conv=50.0, eps=0.8, T_amb=300.0):
    """Temperature (K) of rod material descending through the coil.

    Lagrangian (material-following) model: a slice enters the coil at
    T_feed and heats as it descends at v_feed. Energy balance per unit
    mass along the path, with surface radiation + convection losses:
        de/dz = (q'(z) - loss'(z)) / (rho * A * v_feed)
    Temperature follows from enthalpy with a melting plateau: while
    the accumulated energy is between cp*(T_melt - T_feed) and that
    plus Lf, the slice stays at T_melt (mushy zone); beyond it, the
    liquid superheats. This is the correct frame for EIGA: the rod is
    continuously fed, so a static conduction model (all heat forced
    up a thin rod) gives absurd temperatures. Feed speed and power
    must match: too fast a feed (or too little power) and the tip
    never reaches T_melt.
    """
    import numpy as np
    sigma = 5.67e-8
    Nz = len(z)
    T = np.zeros(Nz)
    e_melt = cp * (T_melt - T_feed)
    e_liq = e_melt + Lf
    e = 0.0
    for i in range(Nz):
        if e < e_melt:
            Ti = T_feed + e / cp
        elif e < e_liq:
            Ti = T_melt
        else:
            Ti = T_melt + (e - e_liq) / cp
        T[i] = Ti
        if i < Nz - 1:
            dz = z[i + 1] - z[i]
            loss = 2.0 * math.pi * R * (
                h_conv * (Ti - T_amb) + eps * sigma * (Ti ** 4 - T_amb ** 4))
            de = (q_prime[i] - loss) * dz / (rho * A * v_feed) \
                if v_feed > 0 else 0.0
            e = max(e + de, 0.0)
    return T


def radial_temperature_field(T_ax, q_prime, R, delta, k, Nr=25):
    """2D temperature field (Nz x Nr) in the rod cross-section.

    Surface heating in a skin layer of thickness delta: the radial
    profile decays exponentially inward from the surface, with the
    surface excess q''*delta/k (heat flux x skin depth / conductivity).
    Each row is corrected so its area-weighted mean equals the axial
    model temperature T_ax. Returns (T_grid, r_grid).
    """
    import numpy as np
    Nz = len(T_ax)
    r = np.linspace(0.0, R, Nr)
    q_surf = q_prime / (2.0 * math.pi * R) if R > 0 else np.zeros(Nz)
    excess = q_surf * delta / k
    prof = np.exp(-(R - r) / delta) if delta > 0 else np.zeros(Nr)
    # Area-weighted mean of prof over the disk (manual trapezoid).
    mean = 0.0
    for i in range(Nr - 1):
        mean += 0.5 * (r[i] * prof[i] + r[i + 1] * prof[i + 1]) * (r[i + 1] - r[i])
    mean = mean * 2.0 / (R ** 2) if R > 0 else 0.0
    T_grid = T_ax[:, None] + excess[:, None] * (prof[None, :] - mean)
    return T_grid, r


def rod_descent_temperature_var(z, q_prime, v_feed, rho, cp, T_feed, T_melt, Lf,
                                R_z, h_conv=50.0, eps=0.8, T_amb=300.0):
    """rod_descent_temperature for a body whose radius varies with depth (cone tip).

    Same Lagrangian energy balance, but the cross-section shrinks along the
    cone: mass conservation gives rho*A(z)*v(z) = rho*A0*v_feed, so the local
    velocity grows as the area shrinks, while the radiating perimeter is the
    local one. Net effect: the cone tip heats with less thermal mass but
    loses more per unit mass, so a too-shallow cone can be cooler than a
    straight rod at the same power.
    """
    import numpy as np
    sigma = 5.67e-8
    Nz = len(z)
    R0 = R_z[0]
    T = np.zeros(Nz)
    e_melt = cp * (T_melt - T_feed)
    e_liq = e_melt + Lf
    e = 0.0
    for i in range(Nz):
        if e < e_melt:
            Ti = T_feed + e / cp
        elif e < e_liq:
            Ti = T_melt
        else:
            Ti = T_melt + (e - e_liq) / cp
        T[i] = Ti
        if i < Nz - 1:
            dz = z[i + 1] - z[i]
            r = R_z[i]
            A = math.pi * r ** 2
            v = v_feed * (R0 / r) ** 2 if r > 0 else v_feed
            loss = 2.0 * math.pi * r * (
                h_conv * (Ti - T_amb) + eps * sigma * (Ti ** 4 - T_amb ** 4))
            de = (q_prime[i] - loss) * dz / (rho * A * v) \
                if (v_feed > 0 and A > 0 and v > 0) else 0.0
            e = max(e + de, 0.0)
    return T


def rod_descent_temperature_axial(z, q_prime, v_feed, rho, cp, T_feed, T_melt, Lf,
                                  R_z, k, h_conv=50.0, eps=0.8, T_amb=300.0):
    """rod_descent_temperature_var + axial heat conduction along the rod.

    Steady balance per unit length (uniform z grid, as built by the caller):
        mdot * de/dz = q'(z) - loss(z) + d/dz [ k*A(z)*dT/dz ]
    with mdot = rho * pi * R_z[0]^2 * v_feed (constant by mass conservation)
    and an adiabatic tip (no conduction flux past the free end).

    The melting plateau pins T at T_melt while e spans [e_melt, e_liq], so
    conducted heat into a plateau cell melts more material instead of raising
    its temperature; conduction mainly preheats the cold shank above the coil.
    Solved implicitly (Newton in enthalpy e with a tridiagonal Jacobian):
    an explicit march is unstable for the stiff conduction term on a fine
    grid. Falls back to rod_descent_temperature_var when there is no feed
    (mdot <= 0) or too few points.
    """
    import numpy as np
    sigma = 5.67e-8
    Nz = len(z)
    R0 = R_z[0] if Nz > 0 else 0.0
    mdot = rho * math.pi * R0 ** 2 * v_feed
    if Nz < 3 or mdot <= 0:
        return rod_descent_temperature_var(z, q_prime, v_feed, rho, cp,
                                           T_feed, T_melt, Lf, R_z,
                                           h_conv, eps, T_amb)
    dz = float(z[1] - z[0])
    e_melt = cp * (T_melt - T_feed)
    e_liq = e_melt + Lf
    kA_half = k * math.pi * ((R_z[:-1] + R_z[1:]) / 2.0) ** 2

    def temp_from_e(e):
        T = np.empty_like(e)
        m1 = e < e_melt
        m2 = (e >= e_melt) & (e <= e_liq)
        m3 = e > e_liq
        T[m1] = T_feed + e[m1] / cp
        T[m2] = T_melt
        T[m3] = T_melt + (e[m3] - e_liq) / cp
        return T

    def dT_de(e):
        d = np.zeros_like(e)
        d[(e < e_melt) | (e > e_liq)] = 1.0 / cp
        return d

    def resid(e):
        T = temp_from_e(e)
        loss = 2.0 * math.pi * R_z * (h_conv * (T - T_amb)
                                      + eps * sigma * (T ** 4 - T_amb ** 4))
        F = np.zeros(Nz - 1)
        for j in range(Nz - 1):
            i = j + 1
            if i < Nz - 1:
                cond = (kA_half[i] * (T[i + 1] - T[i])
                        - kA_half[i - 1] * (T[i] - T[i - 1])) / dz ** 2
            else:
                cond = (0.0 - kA_half[i - 1] * (T[i] - T[i - 1])) / dz ** 2
            F[j] = mdot * (e[i] - e[i - 1]) / dz - q_prime[i] + loss[i] - cond
        return F, T

    # initial guess: conduction-free march in e
    e = np.zeros(Nz)
    for i in range(Nz - 1):
        Ti = temp_from_e(np.array([e[i]]))[0]
        loss = 2.0 * math.pi * R_z[i] * (h_conv * (Ti - T_amb)
                                         + eps * sigma * (Ti ** 4 - T_amb ** 4))
        e[i + 1] = max(e[i] + (q_prime[i] - loss) * dz / mdot, 0.0)
    e[0] = 0.0

    n = Nz - 1
    for _ in range(80):
        F, T = resid(e)
        dtd = dT_de(e)
        dloss = 2.0 * math.pi * R_z * (h_conv + 4.0 * eps * sigma * T ** 3)
        a = np.zeros(n)
        b = np.zeros(n)
        c = np.zeros(n)
        for j in range(n):
            i = j + 1
            if i < Nz - 1:
                dcdi = (kA_half[i] + kA_half[i - 1]) / dz ** 2
                dcdm = -kA_half[i - 1] / dz ** 2
                dcdp = -kA_half[i] / dz ** 2
            else:
                dcdi = kA_half[i - 1] / dz ** 2
                dcdm = -kA_half[i - 1] / dz ** 2
                dcdp = 0.0
            b[j] = mdot / dz + (dloss[i] + dcdi) * dtd[i]
            if j >= 1:
                a[j] = -mdot / dz + dcdm * dtd[i - 1]
            if i < Nz - 1:
                c[j] = dcdp * dtd[i + 1]
        # Thomas algorithm for the tridiagonal Newton step (rhs = -F)
        cp_ = np.zeros(n)
        dp_ = np.zeros(n)
        cp_[0] = c[0] / b[0]
        dp_[0] = -F[0] / b[0]
        for i2 in range(1, n):
            m = b[i2] - a[i2] * cp_[i2 - 1]
            cp_[i2] = c[i2] / m if i2 < n - 1 else 0.0
            dp_[i2] = (-F[i2] - a[i2] * dp_[i2 - 1]) / m
        delta = np.zeros(n)
        delta[-1] = dp_[-1]
        for i2 in range(n - 2, -1, -1):
            delta[i2] = dp_[i2] - cp_[i2] * delta[i2 + 1]
        step = 1.0
        fnorm = float(np.max(np.abs(F)))
        while step > 1e-4:
            e_try = e.copy()
            e_try[1:] += step * delta
            e_try = np.maximum(e_try, 0.0)
            F_try, _ = resid(e_try)
            if float(np.max(np.abs(F_try))) <= fnorm:
                break
            step *= 0.5
        e = e_try
        if float(np.max(np.abs(step * delta))) < 1.0:
            break
    return temp_from_e(e)


def radial_temperature_field_var(T_ax, q_prime, R_z, delta, k, Nr=25):
    """radial_temperature_field for a radius that varies with z (cone tip).

    The radial grid is normalized (xi = r / R(z)), so column 0 is the axis and
    column Nr-1 is the surface for every row. The skin-layer excess uses the
    local surface flux q'/(2*pi*R(z)) and local radius; each row is corrected
    so its area-weighted mean equals the axial model temperature T_ax.
    """
    import numpy as np
    Nz = len(T_ax)
    xi = np.linspace(0.0, 1.0, Nr)
    T_grid = np.zeros((Nz, Nr))
    for i in range(Nz):
        r = R_z[i]
        if r <= 0 or k <= 0:
            T_grid[i] = T_ax[i]
            continue
        q_surf = q_prime[i] / (2.0 * math.pi * r)
        excess = q_surf * delta / k
        prof = np.exp(-(r - xi * r) / delta) if delta > 0 else np.zeros(Nr)
        mean = float(2.0 * np.trapezoid(xi * prof, xi))
        T_grid[i] = T_ax[i] + excess * (prof - mean)
    return T_grid, xi


def transit_velocity(v0, deltaP_Pa, rho):
    """Melt velocity after a pressure-difference driven passage (m/s)."""
    return math.sqrt(v0 ** 2 + 2.0 * max(deltaP_Pa, 0.0) / rho)


# ---------------------------------------------------------------- droplet cooling (preview for phase 2)
def droplet_cooling_time(d_m, rho_m, cp_m, Lf, T0_K, T_gas_K,
                         T_liq_K, T_solid_K,
                         rho_g, v_rel, mu_g, k_g=0.05, Pr=0.7):
    """Cooling + solidification time (s), Ranz-Marshall + lumped capacitance.

    Sensible cooling from T0 to liquidus, then latent-heat removal at
    ~solidus. Very approximate: single droplet, no radiation, no
    undercooling, velocity held constant (real droplets decelerate, so
    the flight distance here is an upper estimate). Used only to compare
    against chamber height (does the droplet freeze before it can hit
    a wall?).
    """
    if d_m <= 0 or T0_K <= T_liq_K:
        return 0.0
    Re = rho_g * v_rel * d_m / mu_g if mu_g > 0 else 0.0
    Nu = 2.0 + 0.6 * math.sqrt(max(Re, 0.0)) * (Pr ** (1.0 / 3.0))
    h = Nu * k_g / d_m
    if h <= 0:
        return 0.0
    tau = rho_m * cp_m * d_m / (6.0 * h)
    t_sens = tau * math.log((T0_K - T_gas_K) / (T_liq_K - T_gas_K))
    dT_lat = max(T_solid_K - T_gas_K, 1.0)
    t_lat = rho_m * Lf * d_m / (6.0 * h * dT_lat)
    return t_sens + t_lat


# ---------------------------------------------------------------- thermal radiation
SIGMA_SB = 5.670374419e-8


def radiation_heat_flux(T_hot_K, T_surr_K, eps=0.8):
    """Net radiative heat flux (W/m2) from a hot surface to a cooler one."""
    return eps * SIGMA_SB * (T_hot_K ** 4 - T_surr_K ** 4)


def wall_temperature_transient(T_hot_K, T_wall0_K, T_gas_K, area_hot, area_wall,
                               view_factor=0.3, eps=0.8, thick_m=0.005,
                               rho_w=7900.0, cp_w=500.0, h_conv=10.0,
                               h_out=50.0, t_end=600.0, n_out=300,
                               T_amb_K=298.15, n_steps=4000):
    """Surrounding wall temperature vs time under radiation from a hot body.

    Lumped-capacitance wall node (uniform temperature across the thickness):
        m cp dT/dt = eps*sig*A_hot*F*(T_hot^4 - T_w^4)
                     - h_conv*A_wall*(T_w - T_gas)
                     - h_out*A_wall*(T_w - T_amb)
                     - eps*sig*A_wall*(T_w^4 - T_amb^4)

    The wall absorbs radiation from the rod/coil, and loses heat on its outer
    side by cooling (h_out, e.g. water jacket) and by re-radiation. Steady
    state is found by bisection on the energy balance.

    Returns (t_s, T_wall_C, Q_rad_W, T_eq_C, t90_s); t90 = time to reach 90 %
    of the rise from the initial temperature to the steady state.
    """
    import numpy as np
    m_cp = max(rho_w * max(thick_m, 1e-4) * max(area_wall, 1e-6) * cp_w, 1.0)

    def balance(T_w):
        q_in = eps * SIGMA_SB * area_hot * view_factor * (T_hot_K ** 4 - T_w ** 4)
        q_loss = (h_conv * (T_w - T_gas_K) + h_out * (T_w - T_amb_K)) * area_wall
        q_loss += eps * SIGMA_SB * area_wall * (T_w ** 4 - T_amb_K ** 4)
        return q_in - q_loss

    lo, hi = min(T_amb_K, T_gas_K), max(T_hot_K, T_amb_K) + 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if balance(mid) > 0.0:
            lo = mid
        else:
            hi = mid
    T_eq = 0.5 * (lo + hi)

    q0 = abs(balance(T_wall0_K))
    dt_stable = 0.25 * m_cp / max(q0 / max(abs(T_eq - T_wall0_K), 1.0), 1e-3)
    n = int(min(max(n_steps, t_end / max(dt_stable, 1e-3) * 4.0), 400000))
    dt = t_end / n
    T = float(T_wall0_K)
    t_out = np.linspace(0.0, t_end, int(n_out))
    T_out = np.empty_like(t_out)
    Q_out = np.empty_like(t_out)
    k = 0
    for i in range(n + 1):
        if k < len(t_out) and i * dt >= t_out[k] - 1e-12:
            T_out[k] = T
            Q_out[k] = eps * SIGMA_SB * area_hot * view_factor * (T_hot_K ** 4 - T ** 4)
            k += 1
            if k >= len(t_out):
                break
        T += dt * balance(T) / m_cp
        if T < 0.0:
            T = 0.0

    t90 = float(t_end)
    target = T_wall0_K + 0.9 * (T_eq - T_wall0_K)
    hit = np.where(T_out >= target)[0]
    if len(hit):
        t90 = float(t_out[hit[0]])
    return t_out, T_out - 273.15, Q_out, T_eq - 273.15, t90
