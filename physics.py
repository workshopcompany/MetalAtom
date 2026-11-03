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
