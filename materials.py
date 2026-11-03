# -*- coding: utf-8 -*-
"""Material property data for the EIGA atomizer simulator.

All values are TYPICAL literature values, not measured data for a specific
batch. Every value is editable from the app UI, and the user should replace
them with their own alloy/gas data when available. In particular the melt
viscosity of an alloy is a first-order limit on atomization: a melt that is
too viscous will not break up no matter how good the heating is.
"""

ALLOYS = {
    "316L 스테인리스": {
        "rho_melt": 7000.0,      # kg/m3, liquid density
        "sigma_ref": 1.70,       # N/m, surface tension at T_ref
        "dsigma_dT": -0.0004,    # N/m/K
        "mu_ref": 0.0060,        # Pa*s, dynamic viscosity at T_ref
        "T_ref": 1723.0,         # K, reference temperature (liquidus)
        "T_liquidus": 1723.0,    # K
        "T_solidus": 1658.0,     # K
        "cp": 720.0,             # J/kg/K
        "Lf": 270000.0,          # J/kg, latent heat of fusion
        "k_thermal": 25.0,       # W/m/K, thermal conductivity (hot)
        "rho_e": 1.0e-6,         # ohm*m, electrical resistivity (hot)
    },
    "17-4PH": {
        "rho_melt": 7100.0,
        "sigma_ref": 1.75,
        "dsigma_dT": -0.0004,
        "mu_ref": 0.0062,
        "T_ref": 1723.0,
        "T_liquidus": 1723.0,
        "T_solidus": 1623.0,
        "cp": 700.0,
        "Lf": 270000.0,
        "k_thermal": 25.0,
        "rho_e": 1.0e-6,
    },
    "Ti-6Al-4V": {
        "rho_melt": 4100.0,
        "sigma_ref": 1.50,
        "dsigma_dT": -0.0003,
        "mu_ref": 0.0050,
        "T_ref": 1923.0,
        "T_liquidus": 1923.0,
        "T_solidus": 1873.0,
        "cp": 800.0,
        "Lf": 360000.0,
        "k_thermal": 15.0,
        "rho_e": 1.7e-6,
    },
    "Inconel 718": {
        "rho_melt": 7500.0,
        "sigma_ref": 1.80,
        "dsigma_dT": -0.0004,
        "mu_ref": 0.0065,
        "T_ref": 1613.0,
        "T_liquidus": 1613.0,
        "T_solidus": 1533.0,
        "cp": 650.0,
        "Lf": 270000.0,
        "k_thermal": 20.0,
        "rho_e": 1.2e-6,
    },
    "저합금강 (Fe-2Ni)": {
        "rho_melt": 7000.0,
        "sigma_ref": 1.85,
        "dsigma_dT": -0.0004,
        "mu_ref": 0.0060,
        "T_ref": 1800.0,
        "T_liquidus": 1800.0,
        "T_solidus": 1723.0,
        "cp": 720.0,
        "Lf": 270000.0,
        "k_thermal": 30.0,
        "rho_e": 1.0e-6,
    },
}

# Gas data: molar mass (kg/mol), heat capacity ratio, dynamic viscosity (Pa*s)
GASES = {
    "Ar (아르곤)": {"M": 0.03995, "gamma": 1.66, "mu": 2.2e-5},
    "N2 (질소)": {"M": 0.02801, "gamma": 1.40, "mu": 1.76e-5},
    "He (헬륨)": {"M": 0.00400, "gamma": 1.66, "mu": 1.96e-5},
}

R_UNIVERSAL = 8.314  # J/mol/K
