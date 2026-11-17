"""Instruction selection and encoding for the supported Cortex-M0 subset."""

from typing import List

try:
    from .errors import AsmError
    from .expr import EvalContext, Expression
    from .lexer import split_operands
except ImportError:
    from errors import AsmError
    from expr import EvalContext, Expression
    from lexer import split_operands


REGISTER_ALIASES = {
    "sp": 13, "lr": 14, "pc": 15, "ip": 12, "fp": 11, "sl": 10, "sb": 9,
}
CONDITIONS = {
    "eq": 0, "ne": 1, "cs": 2, "hs": 2, "cc": 3, "lo": 3,
    "mi": 4, "pl": 5, "vs": 6, "vc": 7, "hi": 8, "ls": 9,
    "ge": 10, "lt": 11, "gt": 12, "le": 13,
}
MISSING_SUFFIX = {
    "and": "ands", "orr": "orrs", "eor": "eors", "bic": "bics",
    "adc": "adcs", "sbc": "sbcs", "mul": "muls", "mvn": "mvns",
    "lsl": "lsls", "lsr": "lsrs", "asr": "asrs", "ror": "rors",
    "neg": "rsbs",
}
COURSE_SUBSET_ERRORS = {
    "bkpt", "cpsid", "cpsie", "mrs", "msr", "dmb", "dsb", "isb",
    "wfi", "wfe", "sev", "yield", "udf", "rev16", "revsh",
}
NOT_IMPLEMENTED = {
    "ands", "orrs", "eors", "bics", "adcs", "sbcs", "mvns", "rsbs",
    "lsrs", "asrs", "rors", "tst", "cmn", "sxth", "sxtb", "uxth",
    "uxtb", "rev",
}
DATA_LIMITS = {
    1: (-128, 255),
    2: (-32768, 65535),
    4: (-2147483648, 4294967295),
}
REGISTER_LOAD_STORE = {
    "str": 0x5000, "strh": 0x5200, "strb": 0x5400,
    "ldrsb": 0x5600, "ldr": 0x5800, "ldrh": 0x5A00,
    "ldrb": 0x5C00, "ldrsh": 0x5E00,
}
IMMEDIATE_LOAD_STORE = {
    "str": (0x6000, 4, 124),
    "ldr": (0x6800, 4, 124),
    "strb": (0x7000, 1, 31),
    "ldrb": (0x7800, 1, 31),
    "strh": (0x8000, 2, 62),
    "ldrh": (0x8800, 2, 62),
}


def base_mnemonic(mnemonic: str) -> str:
    """Remove an ignored ``.n`` or ``.w`` width suffix."""
    name = mnemonic.lower()
    for suffix in (".n", ".w"):
        if name.endswith(suffix):
            return name[:-len(suffix)]
    return name


def encode_program(program, diagnostics) -> None:
    """Evaluate and encode every layout item, collecting all errors."""
    for section in program.section_order:
        for item in section.items:
            try:
                item.encoded = _encode_item(program, item)
            except AsmError as error:
                diagnostics.add_error(error)
                item.encoded = bytes(item.size)


def parse_register(text: str, item) -> int:
    """Parse ``r0`` to ``r15`` or a named register alias."""
    name = text.strip().lower()
    if name in REGISTER_ALIASES:
        return REGISTER_ALIASES[name]
    if len(name) > 1 and name[0] == "r" and name[1:].isdigit():
        number = int(name[1:])
        if 0 <= number <= 15:
            return number
    raise AsmError("unknown register: " + text.strip(), item.statement.file,
                   item.statement.line, item.statement.source)


def require_low(register: int, item) -> None:
    """Reject a high register where the 16-bit encoding has only three bits."""
    if register > 7:
        raise AsmError("high register r" + str(register) +
                       " where a low register (r0-r7) is required",
                       item.statement.file, item.statement.line,
                       item.statement.source)


def check_range(value: int, low: int, high: int, what: str, item) -> int:
    """Check an integer range and include the value and limits in errors."""
    if value < low or value > high:
        raise AsmError(what + " out of range: " + str(value) +
                       " (expected " + str(low) + ".." + str(high) + ")",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    return value


def _encode_item(program, item) -> bytes:
    """Encode one layout item according to its kind."""
    if item.kind == "instr":
        return _encode_instruction(program, item)
    if item.kind == "pool_word":
        value = _evaluate(program, item, item.expression.text, "data")
        return (value & 0xFFFFFFFF).to_bytes(4, "little")
    if item.kind == "padding":
        return bytes(item.size)
    return _encode_data_item(program, item)


def _encode_data_item(program, item) -> bytes:
    """Evaluate and pack one or more explicit data directive values."""
    if item.literal_bytes:
        return item.literal_bytes
    if item.fill_spec is not None:
        fill = _evaluate(program, item, item.fill_spec, "data")
        check_range(fill, -128, 255, "fill value", item)
        return bytes([fill & 0xFF]) * item.size
    result = bytearray()
    for size, text in item.data_specs:
        value = _evaluate(program, item, text, "data")
        low, high = DATA_LIMITS[size]
        check_range(value, low, high, "data value", item)
        result.extend((value & ((1 << (size * 8)) - 1)).to_bytes(size, "little"))
    return bytes(result)


def _encode_instruction(program, item) -> bytes:
    """Dispatch a mnemonic to its encoder and pack the resulting bits."""
    name = base_mnemonic(item.mnemonic)
    if name in COURSE_SUBSET_ERRORS:
        raise AsmError("instruction not in the course subset: " + name,
                       item.statement.file, item.statement.line,
                       item.statement.source)
    if name in MISSING_SUFFIX:
        raise AsmError("use '" + MISSING_SUFFIX[name] +
                       "' (ARMv6-M data-processing instructions set flags)",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    if name == "bl":
        return _encode_bl(program, item)
    value = _encode_halfword_instruction(program, item, name)
    return (value & 0xFFFF).to_bytes(2, "little")


def _encode_halfword_instruction(program, item, name: str) -> int:
    """Encode all single-halfword instruction groups."""
    if name in ("movs", "mov"):
        return _encode_mov(program, item, name == "movs")
    if name in ("adds", "subs"):
        return _encode_flag_add_sub(program, item, name == "adds")
    if name in ("add", "sub"):
        return _encode_nons_add_sub(program, item, name == "add")
    if name == "cmp":
        return _encode_cmp(program, item)
    if name == "svc":
        return _encode_svc(program, item)
    if name == "nop":
        return _encode_no_operand(program, item, 0xBF00)
    if name in ("bx", "blx"):
        return _encode_bx_blx(program, item, name == "blx")
    if name in ("push", "pop"):
        return _encode_push_pop(program, item, name == "push")
    if name == "b":
        return _encode_branch(program, item)
    if name.startswith("b") and name[1:] in CONDITIONS:
        return _encode_branch(program, item, CONDITIONS[name[1:]])
    if name == "adr":
        return _encode_adr(program, item)
    if name == "lsls":
        return _encode_lsls_immediate(program, item)
    if name == "muls":
        return _encode_muls(program, item)
    if name in ("ldr", "str"):
        return _encode_word_load_store(program, item, name)
    if name in IMMEDIATE_LOAD_STORE or name in ("ldrsb", "ldrsh"):
        return _encode_sized_load_store(program, item, name)
    if name in ("ldm", "ldmia", "stmia", "stm"):
        _check_multiple_writeback(program, item, name)
    if name in NOT_IMPLEMENTED:
        raise AsmError("instruction not implemented in M1-M4: " + name,
                       item.statement.file, item.statement.line,
                       item.statement.source)
    raise AsmError("unknown mnemonic: " + item.mnemonic, item.statement.file,
                   item.statement.line, item.statement.source)


def _evaluate(program, item, text: str, use: str, location=None) -> int:
    """Evaluate one expression with the item's address as the location counter."""
    if location is None:
        location = item.address()
    context = EvalContext(item.statement, location, use)
    return Expression(text, item.statement).evaluate(program.symbols, context)


def _is_immediate(text: str) -> bool:
    """Return True when an operand begins with the immediate marker ``#``."""
    return text.strip().startswith("#")


def _parse_immediate(program, item, text: str, allow_bare: bool = False) -> int:
    """Evaluate an immediate operand, requiring ``#`` unless it is optional."""
    stripped = text.strip()
    if stripped.startswith("#"):
        stripped = stripped[1:]
    elif not allow_bare:
        raise AsmError("immediate operand must start with '#'",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    return _evaluate(program, item, stripped, "data")


def _require_count(item, count: int) -> None:
    """Report the standard wrong-operand-count error."""
    if len(item.operands) != count:
        raise AsmError("wrong operand count: expected " + str(count) +
                       ", got " + str(len(item.operands)),
                       item.statement.file, item.statement.line,
                       item.statement.source)


def _encode_mov(program, item, flag_setting: bool) -> int:
    """Encode ``movs`` register/immediate forms and ``mov`` register form."""
    _require_count(item, 2)
    rd = parse_register(item.operands[0], item)
    if _is_immediate(item.operands[1]):
        if not flag_setting:
            raise AsmError("use 'movs' (ARMv6-M data-processing instructions set flags)",
                           item.statement.file, item.statement.line,
                           item.statement.source)
        require_low(rd, item)
        imm = _parse_immediate(program, item, item.operands[1])
        check_range(imm, 0, 255, "movs immediate", item)
        # 00100 Rd imm8: Rd occupies bits 10:8 and imm8 occupies bits 7:0.
        return 0x2000 | ((rd & 7) << 8) | (imm & 0xFF)
    rm = parse_register(item.operands[1], item)
    if flag_setting:
        require_low(rd, item)
        require_low(rm, item)
        # movs Rd, Rm is the alias of lsls Rd, Rm, #0 (shift field is zero).
        return 0x0000 | ((rm & 7) << 3) | (rd & 7)
    # 01000110 D Rm4 Rd3: bit 7 extends Rd to four bits.
    d_bit = (rd >> 3) & 1
    return 0x4600 | (d_bit << 7) | ((rm & 0xF) << 3) | (rd & 7)


def _encode_flag_add_sub(program, item, is_add: bool) -> int:
    """Encode the low-register ``adds`` and ``subs`` forms."""
    operands = item.operands
    base_register = 0x1800 if is_add else 0x1A00
    if len(operands) == 2:
        rd = parse_register(operands[0], item)
        require_low(rd, item)
        if _is_immediate(operands[1]):
            imm = _parse_immediate(program, item, operands[1])
            check_range(imm, 0, 255, "add/sub immediate", item)
            # 00110/00111 Rdn imm8: Rdn is bits 10:8 and imm8 is bits 7:0.
            base_imm8 = 0x3000 if is_add else 0x3800
            return base_imm8 | ((rd & 7) << 8) | (imm & 0xFF)
        rm = parse_register(operands[1], item)
        require_low(rm, item)
        # 0001100/0001101 Rm Rn Rd with Rn equal to Rd.
        return base_register | ((rm & 7) << 6) | ((rd & 7) << 3) | (rd & 7)
    if len(operands) == 3:
        return _encode_flag_add_sub_three(program, item, is_add, base_register)
    raise AsmError("wrong operand count: expected 2 or 3, got " +
                   str(len(operands)), item.statement.file, item.statement.line,
                   item.statement.source)


def _encode_flag_add_sub_three(program, item, is_add: bool, base_register: int) -> int:
    """Encode a three-operand low-register ``adds`` or ``subs``."""
    rd = parse_register(item.operands[0], item)
    rn = parse_register(item.operands[1], item)
    require_low(rd, item)
    require_low(rn, item)
    if _is_immediate(item.operands[2]):
        imm = _parse_immediate(program, item, item.operands[2])
        if rd == rn:
            check_range(imm, 0, 255, "add/sub immediate", item)
            base_imm8 = 0x3000 if is_add else 0x3800
            # 00110/00111 Rdn imm8 is preferred when Rd and Rn are equal.
            return base_imm8 | ((rd & 7) << 8) | (imm & 0xFF)
        check_range(imm, 0, 7, "add/sub imm3", item)
        base_imm3 = 0x1C00 if is_add else 0x1E00
        # 0001110/0001111 imm3 Rn Rd: imm3 occupies bits 8:6.
        return base_imm3 | ((imm & 7) << 6) | ((rn & 7) << 3) | (rd & 7)
    rm = parse_register(item.operands[2], item)
    require_low(rm, item)
    # 0001100/0001101 Rm Rn Rd: all three registers are low registers.
    return base_register | ((rm & 7) << 6) | ((rn & 7) << 3) | (rd & 7)


def _encode_nons_add_sub(program, item, is_add: bool) -> int:
    """Encode ``add`` and ``sub`` forms that do not set flags."""
    operands = item.operands
    name = "add" if is_add else "sub"
    if len(operands) == 2:
        if _is_immediate(operands[1]):
            first = parse_register(operands[0], item)
            if first == 13:
                return _encode_sp_adjust(program, item, is_add)
            raise AsmError("use '" + name + "s' (ARMv6-M data-processing instructions set flags)",
                           item.statement.file, item.statement.line,
                           item.statement.source)
        if is_add:
            return _encode_add_register(program, item)
        raise AsmError("use 'subs' (ARMv6-M data-processing instructions set flags)",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    if len(operands) == 3:
        return _encode_nons_three(program, item, is_add)
    raise AsmError("wrong operand count: expected 2 or 3, got " +
                   str(len(operands)), item.statement.file, item.statement.line,
                   item.statement.source)


def _encode_nons_three(program, item, is_add: bool) -> int:
    """Encode a three-operand ``add`` or ``sub``."""
    rd = parse_register(item.operands[0], item)
    rn = parse_register(item.operands[1], item)
    if _is_immediate(item.operands[2]):
        if rd == 13 and rn == 13:
            return _encode_sp_adjust(program, item, is_add)
        if not is_add:
            raise AsmError("use 'subs' (ARMv6-M data-processing instructions set flags)",
                           item.statement.file, item.statement.line,
                           item.statement.source)
        if rn == 13:
            return _encode_add_sp_immediate(program, item)
        if rn == 15:
            return _encode_add_pc_immediate(program, item)
        raise AsmError("use 'adds' (ARMv6-M data-processing instructions set flags)",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    if is_add:
        return _encode_add_register(program, item)
    raise AsmError("use 'subs' (ARMv6-M data-processing instructions set flags)",
                   item.statement.file, item.statement.line,
                   item.statement.source)


def _encode_add_register(program, item) -> int:
    """Encode the high-register ``ADD (register)`` T2 form."""
    if len(item.operands) == 2:
        rd = parse_register(item.operands[0], item)
        rn = rd
        source = parse_register(item.operands[1], item)
    else:
        rd = parse_register(item.operands[0], item)
        rn = parse_register(item.operands[1], item)
        source = parse_register(item.operands[2], item)
    if rd == rn:
        encoded_rm = source
    elif rd == source and rn == 13:
        encoded_rm = rn
    elif rd == source and rn == rd:
        encoded_rm = rn
    else:
        raise AsmError("add register form requires Rd == Rn, or Rd == Rm with Rn == sp",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    # 01000100 DN Rm4 Rdn3: DN extends the destination to four bits.
    d_bit = (rd >> 3) & 1
    return 0x4400 | (d_bit << 7) | ((encoded_rm & 0xF) << 3) | (rd & 7)


def _encode_sp_adjust(program, item, is_add: bool) -> int:
    """Encode ``add sp, #imm`` and ``sub sp, #imm`` in steps of four."""
    _require_count(item, 2 if len(item.operands) == 2 else 3)
    text = item.operands[1] if len(item.operands) == 2 else item.operands[2]
    imm = _parse_immediate(program, item, text)
    if imm % 4:
        raise AsmError("stack adjustment must be a multiple of 4: " + str(imm),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    check_range(imm, 0, 508, "stack adjustment", item)
    base = 0xB000 if is_add else 0xB080
    # 10110000/10110001 imm7: imm7 stores imm/4 in bits 6:0.
    return base | ((imm // 4) & 0x7F)


def _encode_add_sp_immediate(program, item) -> int:
    """Encode ``add Rd, sp, #imm``."""
    rd = parse_register(item.operands[0], item)
    require_low(rd, item)
    imm = _parse_immediate(program, item, item.operands[2])
    if imm % 4:
        raise AsmError("sp-relative offset must be a multiple of 4: " + str(imm),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    check_range(imm, 0, 1020, "sp-relative offset", item)
    # 10101000 Rd imm8: imm8 stores the byte offset divided by four.
    return 0xA800 | ((rd & 7) << 8) | ((imm // 4) & 0xFF)


def _encode_add_pc_immediate(program, item) -> int:
    """Encode ``add Rd, pc, #imm`` using the aligned PC base."""
    rd = parse_register(item.operands[0], item)
    require_low(rd, item)
    imm = _parse_immediate(program, item, item.operands[2])
    if imm % 4:
        raise AsmError("pc-relative offset must be a multiple of 4: " + str(imm),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    check_range(imm, 0, 1020, "pc-relative offset", item)
    # 10100000 Rd imm8: the target is Align(PC,4) + imm8*4.
    return 0xA000 | ((rd & 7) << 8) | ((imm // 4) & 0xFF)


def _encode_adr(program, item) -> int:
    """Encode ``adr Rd, label`` as a forward pc-relative address."""
    _require_count(item, 2)
    rd = parse_register(item.operands[0], item)
    require_low(rd, item)
    target = _evaluate(program, item, item.operands[1], "code") & ~1
    base = (item.address() + 4) & ~3
    offset = target - base
    if offset % 4:
        raise AsmError("adr target must be 4-byte aligned: " + str(target),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    check_range(offset, 0, 1020, "adr offset", item)
    # 10100000 Rd imm8: imm8 is the aligned byte offset divided by four.
    return 0xA000 | ((rd & 7) << 8) | ((offset // 4) & 0xFF)


def _encode_lsls_immediate(program, item) -> int:
    """Encode the immediate-shift ``lsls`` form."""
    if len(item.operands) == 2:
        rd = parse_register(item.operands[0], item)
        rm = rd
        immediate_text = item.operands[1]
    elif len(item.operands) == 3:
        rd = parse_register(item.operands[0], item)
        rm = parse_register(item.operands[1], item)
        immediate_text = item.operands[2]
    else:
        raise AsmError("wrong operand count: expected 2 or 3, got " +
                       str(len(item.operands)), item.statement.file,
                       item.statement.line, item.statement.source)
    require_low(rd, item)
    require_low(rm, item)
    imm = _parse_immediate(program, item, immediate_text)
    check_range(imm, 0, 31, "shift amount", item)
    # 00000 imm5 Rm Rd: imm5 is bits 10:6.
    return 0x0000 | ((imm & 31) << 6) | ((rm & 7) << 3) | (rd & 7)


def _encode_muls(program, item) -> int:
    """Encode ``muls``, requiring the destination to equal a source."""
    if len(item.operands) == 2:
        rd = parse_register(item.operands[0], item)
        source = parse_register(item.operands[1], item)
    elif len(item.operands) == 3:
        rd = parse_register(item.operands[0], item)
        rn = parse_register(item.operands[1], item)
        rm = parse_register(item.operands[2], item)
        if rd == rn:
            source = rm
        elif rd == rm:
            source = rn
        else:
            raise AsmError("muls destination must equal one of its sources",
                           item.statement.file, item.statement.line,
                           item.statement.source)
    else:
        raise AsmError("wrong operand count: expected 2 or 3, got " +
                       str(len(item.operands)), item.statement.file,
                       item.statement.line, item.statement.source)
    require_low(rd, item)
    require_low(source, item)
    # 0100001101 Rn Rdm: Rn is bits 5:3 and the accumulator/destination is bits 2:0.
    return 0x4340 | ((source & 7) << 3) | (rd & 7)


def _encode_cmp(program, item) -> int:
    """Encode immediate, low-register and high-register ``cmp`` forms."""
    _require_count(item, 2)
    rn = parse_register(item.operands[0], item)
    if _is_immediate(item.operands[1]):
        require_low(rn, item)
        imm = _parse_immediate(program, item, item.operands[1])
        check_range(imm, 0, 255, "cmp immediate", item)
        # 00101 Rn imm8: Rn is bits 10:8.
        return 0x2800 | ((rn & 7) << 8) | (imm & 0xFF)
    rm = parse_register(item.operands[1], item)
    if rn <= 7 and rm <= 7:
        # 0100001010 Rm Rn: operation code 10 is bits 9:6.
        return 0x4280 | ((rm & 7) << 3) | (rn & 7)
    # 01000101 N Rm4 Rn3: bit 7 extends Rn to four bits.
    n_bit = (rn >> 3) & 1
    return 0x4500 | (n_bit << 7) | ((rm & 0xF) << 3) | (rn & 7)


def _encode_svc(program, item) -> int:
    """Encode ``svc``, whose immediate may omit the leading ``#``."""
    _require_count(item, 1)
    imm = _parse_immediate(program, item, item.operands[0], allow_bare=True)
    check_range(imm, 0, 255, "svc immediate", item)
    # 11011111 imm8: the service number is bits 7:0.
    return 0xDF00 | (imm & 0xFF)


def _encode_no_operand(program, item, base: int) -> int:
    """Encode an instruction with no operands."""
    _require_count(item, 0)
    return base


def _encode_bx_blx(program, item, is_blx: bool) -> int:
    """Encode ``bx Rm`` and ``blx Rm``."""
    _require_count(item, 1)
    rm = parse_register(item.operands[0], item)
    base = 0x4780 if is_blx else 0x4700
    # 01000111 0/1 Rm4 000: the four-bit register is in bits 6:3.
    return base | ((rm & 0xF) << 3)


def _encode_branch(program, item, condition=None) -> int:
    """Encode conditional and unconditional branches with range checks."""
    _require_count(item, 1)
    target = _evaluate(program, item, item.operands[0], "code") & ~1
    offset = target - (item.address() + 4)
    if offset % 2:
        raise AsmError("odd branch offset: " + str(offset),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    if condition is None:
        check_range(offset, -2048, 2046, "branch offset", item)
        return 0xE000 | ((offset >> 1) & 0x7FF)
    check_range(offset, -256, 254, "conditional branch offset", item)
    # 1101 cond imm8: the condition is bits 11:8 and imm8 is bits 7:0.
    return 0xD000 | ((condition & 0xF) << 8) | ((offset >> 1) & 0xFF)


def _encode_bl(program, item) -> bytes:
    """Encode the 32-bit ``bl`` with its split J1/J2 immediate bits."""
    _require_count(item, 1)
    target = _evaluate(program, item, item.operands[0], "code") & ~1
    offset = target - (item.address() + 4)
    if offset % 2:
        raise AsmError("odd branch offset: " + str(offset),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    check_range(offset, -16777216, 16777214, "bl offset", item)
    off25 = offset & 0x1FFFFFF
    s_bit = (off25 >> 24) & 1
    i1 = (off25 >> 23) & 1
    i2 = (off25 >> 22) & 1
    imm10 = (off25 >> 12) & 0x3FF
    imm11 = (off25 >> 1) & 0x7FF
    j1 = 1 ^ (i1 ^ s_bit)
    j2 = 1 ^ (i2 ^ s_bit)
    # 11110 S imm10 / 1101 J1 1 J2 imm11: J1 and J2 invert I1 and I2.
    first = 0xF000 | (s_bit << 10) | imm10
    second = 0xD000 | (j1 << 13) | (j2 << 11) | imm11
    return first.to_bytes(2, "little") + second.to_bytes(2, "little")


def _parse_register_list(text: str, item, is_push: bool):
    """Parse a push or pop register list into its bitmask and pc/lr flag."""
    stripped = text.strip()
    if not stripped.startswith("{") or not stripped.endswith("}"):
        raise AsmError("register list must be enclosed in braces",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    entries = split_operands(stripped[1:-1], item.statement)
    if not entries or any(not entry for entry in entries):
        raise AsmError("register list must not be empty", item.statement.file,
                       item.statement.line, item.statement.source)
    mask = 0
    special = 0
    for entry in entries:
        for register in _expand_register_entry(entry, item):
            if register <= 7:
                mask |= 1 << register
            elif is_push and register == 14:
                special = 1
            elif not is_push and register == 15:
                special = 1
            else:
                raise AsmError("register r" + str(register) +
                               " is not allowed in this register list",
                               item.statement.file, item.statement.line,
                               item.statement.source)
    return mask, special


def _expand_register_entry(entry: str, item) -> List[int]:
    """Expand one register-list item, including ranges such as ``r4-r7``."""
    pieces = entry.split("-")
    if len(pieces) == 1:
        return [parse_register(pieces[0], item)]
    if len(pieces) != 2:
        raise AsmError("bad register range: " + entry, item.statement.file,
                       item.statement.line, item.statement.source)
    first = parse_register(pieces[0], item)
    last = parse_register(pieces[1], item)
    if first > last:
        raise AsmError("bad register range: " + entry, item.statement.file,
                       item.statement.line, item.statement.source)
    return list(range(first, last + 1))


def _encode_push_pop(program, item, is_push: bool) -> int:
    """Encode ``push`` and ``pop`` with their register-list bitmaps."""
    _require_count(item, 1)
    mask, special = _parse_register_list(item.operands[0], item, is_push)
    base = 0xB400 if is_push else 0xBC00
    # 1011010 M list8 / 1011110 P list8: M means lr and P means pc.
    return base | (special << 8) | (mask & 0xFF)


def _parse_memory_operand(program, text: str, item):
    """Parse ``[Rn]``, ``[Rn, #imm]`` or ``[Rn, Rm]`` into a triple."""
    stripped = text.strip()
    if "!" in stripped:
        raise AsmError("writeback is not supported on single loads and stores",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    if not stripped.startswith("[") or not stripped.endswith("]"):
        raise AsmError("expected a bracketed memory operand",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    parts = split_operands(stripped[1:-1], item.statement)
    if len(parts) not in (1, 2):
        raise AsmError("wrong operand count in memory operand",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    base = parse_register(parts[0], item)
    if len(parts) == 1:
        return base, "zero", 0
    offset = parts[1].strip()
    if _is_immediate(offset):
        return base, "imm", _parse_immediate(program, item, offset)
    if offset.startswith("-"):
        raise AsmError("negative offsets are not supported",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    return base, "reg", parse_register(offset, item)


def _check_offset(value: int, step: int, maximum: int, what: str, item) -> int:
    """Check a non-negative offset and return the encoded field value."""
    if value % step:
        raise AsmError(what + " must be a multiple of " + str(step) + ": " + str(value),
                       item.statement.file, item.statement.line,
                       item.statement.source)
    check_range(value, 0, maximum, what, item)
    return (value // step) & 0xFF


def _check_pc_offset(value: int, item) -> int:
    """Check a 10-bit pc-relative word offset."""
    return _check_offset(value, 4, 1020, "pc-relative offset", item)


def _encode_word_load_store(program, item, name: str) -> int:
    """Encode the word ``ldr`` and ``str`` forms."""
    _require_count(item, 2)
    rt = parse_register(item.operands[0], item)
    require_low(rt, item)
    second = item.operands[1].strip()
    if name == "ldr" and second.startswith("="):
        return _encode_pool_load(program, item, rt)
    if name == "ldr" and not second.startswith("["):
        return _encode_label_load(program, item, rt)
    base, kind, offset = _parse_memory_operand(program, second, item)
    if name == "ldr" and base == 15:
        if kind != "imm":
            raise AsmError("pc-relative ldr requires an immediate offset",
                           item.statement.file, item.statement.line,
                           item.statement.source)
        # 01001 Rt imm8: imm8 is Align(PC,4)-relative word offset.
        return 0x4800 | ((rt & 7) << 8) | _check_pc_offset(offset, item)
    if base == 13:
        word = _check_offset(offset, 4, 1020, "sp-relative offset", item)
        base_opcode = 0x9800 if name == "ldr" else 0x9000
        # 1001 0/1 Rt imm8: Rt is bits 10:8 and imm8 is imm/4.
        return base_opcode | ((rt & 7) << 8) | word
    require_low(base, item)
    if kind == "reg":
        base_opcode = 0x5800 if name == "ldr" else 0x5000
        # 0101 1000/0000 Rm Rn Rt: bits 8:6 hold the offset register.
        return base_opcode | ((offset & 7) << 6) | ((base & 7) << 3) | (rt & 7)
    word = _check_offset(offset, 4, 124, "word offset", item)
    base_opcode = 0x6800 if name == "ldr" else 0x6000
    # 0110 1000/0000 imm5 Rn Rt: imm5 is the byte offset divided by four.
    return base_opcode | ((word & 0x1F) << 6) | ((base & 7) << 3) | (rt & 7)


def _encode_pool_load(program, item, rt: int) -> int:
    """Encode ``ldr Rt, =expr`` using its assigned literal pool word."""
    if item.pool_entry is None:
        raise AsmError("literal pool entry is missing", item.statement.file,
                       item.statement.line, item.statement.source)
    instruction_address = item.address()
    pool_base = (instruction_address + 4) & ~3
    offset = item.pool_entry.address() - pool_base
    if offset % 4 or offset < 0 or offset > 1020:
        raise AsmError("literal pool out of range: add .ltorg after this function " +
                       "(offset " + str(offset) + ", limit 0..1020)",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    # 01001 Rt imm8: imm8 addresses the aligned literal word.
    return 0x4800 | ((rt & 7) << 8) | ((offset // 4) & 0xFF)


def _encode_label_load(program, item, rt: int) -> int:
    """Encode ``ldr Rt, label`` as a forward pc-relative load."""
    target = _evaluate(program, item, item.operands[1], "code") & ~1
    base = (item.address() + 4) & ~3
    offset = target - base
    if offset % 4 or offset < 0 or offset > 1020:
        raise AsmError("literal target out of range: add .ltorg near this function " +
                       "(offset " + str(offset) + ", limit 0..1020)",
                       item.statement.file, item.statement.line,
                       item.statement.source)
    # 01001 Rt imm8: the target must be a forward, aligned word address.
    return 0x4800 | ((rt & 7) << 8) | ((offset // 4) & 0xFF)


def _encode_sized_load_store(program, item, name: str) -> int:
    """Encode byte, halfword and sign-extending load/store forms."""
    _require_count(item, 2)
    rt = parse_register(item.operands[0], item)
    require_low(rt, item)
    base, kind, offset = _parse_memory_operand(program, item.operands[1], item)
    require_low(base, item)
    if kind == "reg" or name in ("ldrsb", "ldrsh"):
        if kind == "imm":
            raise AsmError("only register offset exists for " + name,
                           item.statement.file, item.statement.line,
                           item.statement.source)
        rm = offset if kind == "reg" else 0
        require_low(rm, item)
        base_opcode = REGISTER_LOAD_STORE[name]
        # 0101 op Rm Rn Rt: bits 8:6 select the offset register.
        return base_opcode | ((rm & 7) << 6) | ((base & 7) << 3) | (rt & 7)
    base_opcode, step, maximum = IMMEDIATE_LOAD_STORE[name]
    field = _check_offset(offset, step, maximum, name + " offset", item)
    # 011x/100x imm5 Rn Rt: imm5 is the byte offset divided by ``step``.
    return base_opcode | ((field & 0x1F) << 6) | ((base & 7) << 3) | (rt & 7)


def _check_multiple_writeback(program, item, name: str) -> None:
    """Validate the write-back rules before reporting M5 as unimplemented."""
    _require_count(item, 2)
    base_text = item.operands[0].strip()
    writeback = base_text.endswith("!")
    rn = parse_register(base_text[:-1] if writeback else base_text, item)
    mask, _ = _parse_register_list(item.operands[1], item, False)
    if name.startswith("st") and not writeback:
        raise AsmError("stm requires write-back (use Rn!)", item.statement.file,
                       item.statement.line, item.statement.source)
    if name.startswith("ld"):
        if (rn in _register_mask(mask)) == writeback:
            raise AsmError("ldm write-back rule violation for r" + str(rn),
                           item.statement.file, item.statement.line,
                           item.statement.source)
    raise AsmError("instruction not implemented in M1-M4: " + name,
                   item.statement.file, item.statement.line, item.statement.source)


def _register_mask(mask: int) -> List[int]:
    """Turn a low-register bitmask into register numbers."""
    return [number for number in range(8) if mask & (1 << number)]
