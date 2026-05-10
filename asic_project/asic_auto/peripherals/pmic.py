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
    Send hardcoded unlock sequence: AA 04 04 AA 07 D1 DD
    This is a special write command to enable PMIC configuration.
    RX: 5A 5A
    """
    data = bytes([CMD_WRITE, 0x07, 0xD1, 0xDD])
    result = uart.send_packet(uart.SOF_WRITE, PERIPHERAL_ID, data)
    result["operation"] = "unlock"
    return result


def pmic_write(reg_addr, value):
    """Write value to PMIC register at reg_addr (10-bit address)."""
    return _write_reg(reg_addr, value)


def pmic_read(reg_addr):
    """Read one byte from PMIC register at reg_addr (10-bit address)."""
    return _read_reg(reg_addr)


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
