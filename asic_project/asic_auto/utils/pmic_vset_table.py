# pmic_vset_table.py
# MCP16701 VSET[7:0] voltage lookup table
# Built from Table 2-3: VSET[7:5] selects range, VSET[4:0] selects row

# Full table: {vset_code (int): voltage_mv (float)}
VSET_TO_MV = {}

# Column definitions: (vset_upper_3bits, base_mv, step_mv, max_mv)
# VSET[7:5] = 001 : 12.5 mV steps, LDO max 1600 mV, buck clamped to 600 mV for rows 0-15
# VSET[7:5] = 010 : 12.5 mV steps, 800 - 1187.5 mV
# VSET[7:5] = 011 : 12.5 mV steps, 1200 - 1587.5 mV
# VSET[7:5] = 100 : 25   mV steps, 1600 - 2375 mV
# VSET[7:5] = 101 : 25   mV steps, 2400 - 3175 mV
# VSET[7:5] = 110 : 25   mV steps, 3200 - 3800 mV (truncated)

COLUMNS = [
    # (upper_bits, base_mv, step_mv, hard_min_mv, hard_max_mv)
    (0b001, 600.0,  12.5, 600.0,  787.5),   # rows 0-15 clamped to 0.6V for buck
    (0b010, 800.0,  12.5, 800.0,  1187.5),
    (0b011, 1200.0, 12.5, 1200.0, 1587.5),
    (0b100, 1600.0, 25.0, 1600.0, 2375.0),
    (0b101, 2400.0, 25.0, 2400.0, 3175.0),
    (0b110, 3200.0, 25.0, 3200.0, 3800.0),
]

for upper, base, step, hard_min, hard_max in COLUMNS:
    for row in range(32):  # VSET[4:0] = 0..31
        vset_code = (upper << 5) | row
        voltage = base + row * step
        # clamp
        if voltage < hard_min:
            voltage = hard_min
        if voltage > hard_max:
            voltage = hard_max
        VSET_TO_MV[vset_code] = round(voltage, 4)

# Reverse: mv -> best vset code
MV_TO_VSET = {}
for code, mv in VSET_TO_MV.items():
    if mv not in MV_TO_VSET:
        MV_TO_VSET[mv] = code


def vset_from_voltage(target_mv, is_ldo=False):
    """
    Find the VSET code closest to target_mv.
    LDOs are limited to 1600 mV max.
    Returns (vset_code, actual_mv, warning_str)
    """
    limit = 1600.0 if is_ldo else 3800.0
    floor_v = 600.0

    if target_mv < floor_v:
        target_mv = floor_v
        warn = f"Clamped to minimum {floor_v} mV"
    elif target_mv > limit:
        target_mv = limit
        warn = f"Clamped to maximum {limit} mV"
    else:
        warn = ""

    best_code = None
    best_diff = float("inf")
    for code, mv in VSET_TO_MV.items():
        if mv > limit:
            continue
        diff = abs(mv - target_mv)
        if diff < best_diff:
            best_diff = diff
            best_code = code

    actual_mv = VSET_TO_MV[best_code]
    return best_code, actual_mv, warn


def voltage_from_vset(vset_code):
    """Return voltage in mV for a given VSET code."""
    return VSET_TO_MV.get(vset_code & 0xFF, None)
