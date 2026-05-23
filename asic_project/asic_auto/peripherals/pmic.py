# peripherals/pmic.py
# MCP16701 PMIC — ID 0x04
# Packet format: [SOF] 04 04 [CMD] [OPCODE_H] [OPCODE_L] [VALUE]
# CMD: 0xAA for write, 0x55 for read
# Write RX: 5A 5A
# Read  RX: 5A [1 data byte]

import peripherals.uart_handler as uart
from utils.pmic_registers import BUCK_REGS, LDO_REGS, compute_opcodes
from utils.pmic_vset_table import vset_from_voltage, voltage_from_vset

PERIPHERAL_ID = 0x04
CMD_WRITE     = 0xAA
CMD_READ      = 0x55
MAX_CONFIG_ATTEMPTS = 3

BUCK_ENABLE_REGS = {
    1: 0x219,
    2: 0x221,
    3: 0x229,
    4: 0x231,
    5: 0x239,
    6: 0x241,
    7: 0x249,
    8: 0x251,
}

LDO_ENABLE_REGS = {
    1: 0x259,
    2: 0x260,
    3: 0x267,
    4: 0x26E,
}

BUCK_ENABLE_VALUE = 0x81
BUCK_DISABLE_VALUE = 0x80
LDO_ENABLE_VALUE = 0x01
LDO_DISABLE_VALUE = 0x00


def _write_reg(reg_addr, value):
    """Write one byte to a PMIC register address."""
    opcode_h, opcode_l = compute_opcodes(reg_addr)
    data = bytes([CMD_WRITE, opcode_h, opcode_l, value & 0xFF])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    result["reg_addr"] = reg_addr
    result["opcode_h"] = opcode_h
    result["opcode_l"] = opcode_l
    result["value_written"] = value
    return result


def _read_reg(reg_addr):
    """Read one byte from a PMIC register address."""
    opcode_h, opcode_l = compute_opcodes(reg_addr)
    data = bytes([CMD_READ, opcode_h, opcode_l, 0x00])
    result = uart.send_packet(uart.SOF_READ, PERIPHERAL_ID, data)
    result["reg_addr"] = reg_addr
    result["opcode_h"] = opcode_h
    result["opcode_l"] = opcode_l

    rx = result.get("rx", b"")
    if result["status"] == "ok" and len(rx) >= 2:
        raw_val = rx[1]
        result["value_read"] = raw_val
        result["voltage_mv"] = voltage_from_vset(raw_val)
    else:
        result["value_read"] = None
        result["voltage_mv"] = None
    return result


def unlock_pmic():
    """
    Send hardcoded unlock sequence: AA 04 04 AA 07 D3 DD
    This is a special write command to enable PMIC configuration.
    RX: 5A 5A
    """
    data = bytes([CMD_WRITE, 0x07, 0xD3, 0xDD])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    result["operation"] = "unlock"
    return result


def pmic_write(reg_addr, value):
    """Write value to PMIC register at reg_addr (10-bit address)."""
    return _write_reg(reg_addr, value)


def pmic_read(reg_addr):
    """Read one byte from PMIC register at reg_addr (10-bit address)."""
    return _read_reg(reg_addr)


def _read_matches(result, expected):
    return result.get("status") == "ok" and result.get("value_read") == expected


def _regulator_maps(is_ldo):
    return (LDO_REGS, LDO_ENABLE_REGS) if is_ldo else (BUCK_REGS, BUCK_ENABLE_REGS)


def _enable_value(is_ldo, enabled):
    if is_ldo:
        return LDO_ENABLE_VALUE if enabled else LDO_DISABLE_VALUE
    return BUCK_ENABLE_VALUE if enabled else BUCK_DISABLE_VALUE


def _set_regulator_enabled(is_ldo, rail_num, enabled):
    _, enable_regs = _regulator_maps(is_ldo)
    rail_type = "ldo" if is_ldo else "buck"
    if rail_num not in enable_regs:
        return {"status": "error", "error": f"Invalid {rail_type} number {rail_num}"}

    value = _enable_value(is_ldo, enabled)
    unlock = unlock_pmic()
    if unlock.get("status") != "ok":
        return {
            "status": "error",
            "operation": "enable" if enabled else "disable",
            "rail_type": rail_type,
            "rail_num": rail_num,
            "unlock_result": unlock,
            "error": "PMIC unlock failed",
            "tx": unlock.get("tx", b""),
            "rx": unlock.get("rx", b""),
        }

    enable_addr = enable_regs[rail_num]
    write = _write_reg(enable_addr, value)
    read = _read_reg(enable_addr)
    ok = write.get("status") == "ok" and _read_matches(read, value)
    final = read if read.get("rx") else write
    return {
        "status": "ok" if ok else "error",
        "operation": "enable" if enabled else "disable",
        "rail_type": rail_type,
        "rail_num": rail_num,
        "enable_reg": enable_addr,
        "enable_value": value,
        "unlock_result": unlock,
        "enable_result": write,
        "enable_verify_result": read,
        "error": "" if ok else "Enable register verify failed",
        "tx": final.get("tx", b""),
        "rx": final.get("rx", b""),
    }


def _configure_voltage_and_enable(is_ldo, rail_num, voltage_mv,
                                  max_attempts=MAX_CONFIG_ATTEMPTS):
    regs_map, enable_regs = _regulator_maps(is_ldo)
    rail_type = "ldo" if is_ldo else "buck"
    if rail_num not in regs_map:
        return {"status": "error", "error": f"Invalid {rail_type} number {rail_num}"}

    vset_code, actual_mv, warn = vset_from_voltage(voltage_mv, is_ldo=is_ldo)
    if warn:
        print(f"[PMIC] {rail_type.upper()} {rail_num}: {warn}")

    regs = regs_map[rail_num]
    enable_addr = enable_regs[rail_num]
    enable_value = _enable_value(is_ldo, True)
    attempts = []

    for attempt_num in range(1, max(1, int(max_attempts)) + 1):
        attempt = {"attempt": attempt_num}
        unlock = unlock_pmic()
        attempt["unlock_result"] = unlock
        if unlock.get("status") != "ok":
            attempts.append(attempt)
            continue

        r0 = _write_reg(regs["VSET0"], vset_code)
        r1 = _write_reg(regs["VSET1"], vset_code)
        rb0 = _read_reg(regs["VSET0"])
        rb1 = _read_reg(regs["VSET1"])
        attempt.update({
            "vset0_result": r0,
            "vset1_result": r1,
            "vset0_verify_result": rb0,
            "vset1_verify_result": rb1,
        })

        vset_ok = (
            r0.get("status") == "ok" and
            r1.get("status") == "ok" and
            _read_matches(rb0, vset_code) and
            _read_matches(rb1, vset_code)
        )
        attempt["vset_verified"] = vset_ok
        if not vset_ok:
            attempts.append(attempt)
            continue

        enable_write = _write_reg(enable_addr, enable_value)
        enable_read = _read_reg(enable_addr)
        enable_ok = (
            enable_write.get("status") == "ok" and
            _read_matches(enable_read, enable_value)
        )
        attempt.update({
            "enable_result": enable_write,
            "enable_verify_result": enable_read,
            "enable_verified": enable_ok,
        })
        attempts.append(attempt)

        final = enable_read if enable_read.get("rx") else enable_write
        return {
            "status": "ok" if enable_ok else "error",
            "operation": "configure_enable",
            "rail_type": rail_type,
            "rail_num": rail_num,
            "requested_mv": voltage_mv,
            "actual_mv": actual_mv,
            "vset_code": vset_code,
            "enable_reg": enable_addr,
            "enable_value": enable_value,
            "attempts": attempts,
            "attempt_count": attempt_num,
            "warning": warn,
            "error": "" if enable_ok else "Enable register verify failed",
            "tx": final.get("tx", b""),
            "rx": final.get("rx", b""),
        }

    final = attempts[-1].get("vset1_verify_result", attempts[-1].get("unlock_result", {})) if attempts else {}
    return {
        "status": "error",
        "operation": "configure_enable",
        "rail_type": rail_type,
        "rail_num": rail_num,
        "requested_mv": voltage_mv,
        "actual_mv": actual_mv,
        "vset_code": vset_code,
        "enable_reg": enable_addr,
        "enable_value": enable_value,
        "attempts": attempts,
        "attempt_count": len(attempts),
        "warning": warn,
        "error": "VSET readback did not match written value",
        "tx": final.get("tx", b""),
        "rx": final.get("rx", b""),
    }


def configure_buck_voltage_and_enable(buck_num, voltage_mv,
                                      max_attempts=MAX_CONFIG_ATTEMPTS):
    return _configure_voltage_and_enable(False, buck_num, voltage_mv,
                                         max_attempts=max_attempts)


def configure_ldo_voltage_and_enable(ldo_num, voltage_mv,
                                     max_attempts=MAX_CONFIG_ATTEMPTS):
    return _configure_voltage_and_enable(True, ldo_num, voltage_mv,
                                         max_attempts=max_attempts)


def disable_buck(buck_num):
    return _set_regulator_enabled(False, buck_num, False)


def disable_ldo(ldo_num):
    return _set_regulator_enabled(True, ldo_num, False)


def set_buck_voltage(buck_num, voltage_mv):
    """
    Set a Buck regulator voltage.
    buck_num  : 1–8
    voltage_mv: target voltage in mV (600–3800)
    Writes both VSET0 and VSET1 with the same VSET code.
    Returns dict with both write results and resolved voltage.
    """
    if buck_num not in BUCK_REGS:
        return {"status": "error", "error": f"Invalid buck number {buck_num}"}

    vset_code, actual_mv, warn = vset_from_voltage(voltage_mv, is_ldo=False)
    if warn:
        print(f"[PMIC] Buck {buck_num}: {warn}")

    regs = BUCK_REGS[buck_num]
    r0 = _write_reg(regs["VSET0"], vset_code)
    r1 = _write_reg(regs["VSET1"], vset_code)

    return {
        "status": "ok" if (r0["status"] == "ok" and r1["status"] == "ok")
                       else "error",
        "buck_num": buck_num,
        "requested_mv": voltage_mv,
        "actual_mv": actual_mv,
        "vset_code": vset_code,
        "vset0_result": r0,
        "vset1_result": r1,
        "warning": warn,
    }


def set_ldo_voltage(ldo_num, voltage_mv):
    """
    Set an LDO regulator voltage.
    ldo_num   : 1–4
    voltage_mv: target voltage in mV (600–1600)
    Writes both VSET0 and VSET1 with the same VSET code.
    """
    if ldo_num not in LDO_REGS:
        return {"status": "error", "error": f"Invalid LDO number {ldo_num}"}

    vset_code, actual_mv, warn = vset_from_voltage(voltage_mv, is_ldo=True)
    if warn:
        print(f"[PMIC] LDO {ldo_num}: {warn}")

    regs = LDO_REGS[ldo_num]
    r0 = _write_reg(regs["VSET0"], vset_code)
    r1 = _write_reg(regs["VSET1"], vset_code)

    return {
        "status": "ok" if (r0["status"] == "ok" and r1["status"] == "ok")
                       else "error",
        "ldo_num": ldo_num,
        "requested_mv": voltage_mv,
        "actual_mv": actual_mv,
        "vset_code": vset_code,
        "vset0_result": r0,
        "vset1_result": r1,
        "warning": warn,
    }


def pmic_generic_write(reg_addr, value):
    """Generic write — same as pmic_write, explicit name for clarity."""
    return _write_reg(reg_addr, value)


def pmic_generic_read(reg_addr):
    """Generic read — same as pmic_read, explicit name for clarity."""
    return _read_reg(reg_addr)
