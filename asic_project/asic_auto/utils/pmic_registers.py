# pmic_registers.py
# MCP16701 register addresses for all Buck and LDO VSET registers

# Each regulator has VSET0 (mode 0) and VSET1 (mode 1)
# Write both with the same value using pmic_write()

BUCK_REGS = {
    1: {"VSET0": 0x21F, "VSET1": 0x220},
    2: {"VSET0": 0x227, "VSET1": 0x228},
    3: {"VSET0": 0x22F, "VSET1": 0x230},
    4: {"VSET0": 0x237, "VSET1": 0x238},
    5: {"VSET0": 0x23F, "VSET1": 0x240},
    6: {"VSET0": 0x247, "VSET1": 0x248},
    7: {"VSET0": 0x24F, "VSET1": 0x250},
    8: {"VSET0": 0x257, "VSET1": 0x258},
}

LDO_REGS = {
    1: {"VSET0": 0x25E, "VSET1": 0x25F},
    2: {"VSET0": 0x265, "VSET1": 0x266},
    3: {"VSET0": 0x26C, "VSET1": 0x26D},
    4: {"VSET0": 0x273, "VSET1": 0x274},
}


def compute_opcodes(reg_addr):
    """
    Compute OPCODE_H and OPCODE_L from a 10-bit register address.

    OPCODE_H: bits[7:2] = N5:N0 = number of data bytes (always 1)
              bits[1:0] = A9:A8 (top 2 bits of address)
    OPCODE_L: bits[7:0] = A7:A0 (lower 8 bits of address)

    Example: reg_addr=0x22F (BUCK3 VSET0)
      a9a8    = (0x22F >> 8) & 0x03 = 0x02
      a7a0    = 0x22F & 0xFF        = 0x2F
      opcode_h= (1 << 2) | 0x02    = 0x06
      opcode_l= 0x2F
    """
    n_bytes = 1
    a9a8 = (reg_addr >> 8) & 0x03
    a7a0 = reg_addr & 0xFF
    opcode_h = (n_bytes << 2) | a9a8
    opcode_l = a7a0
    return opcode_h, opcode_l
