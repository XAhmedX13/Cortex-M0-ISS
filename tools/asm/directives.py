"""Directive handling shared by the layout pass."""

try:
    from .errors import AsmError
    from .expr import EvalContext, Expression
    from .lexer import parse_string
except ImportError:
    from errors import AsmError
    from expr import EvalContext, Expression
    from lexer import parse_string


IGNORED_DIRECTIVES = {
    ".syntax", ".cpu", ".arch", ".thumb", ".fpu", ".type", ".size",
    ".file", ".eabi_attribute",
}
SECTION_NAMES = {".text": ".text", ".data": ".data", ".bss": ".bss"}
DATA_SIZES = {".word": 4, ".long": 4, ".4byte": 4,
              ".hword": 2, ".short": 2, ".2byte": 2, ".byte": 1}


def handle_directive(program, statement) -> None:
    """Dispatch a directive to the function that implements it."""
    name = statement.mnemonic.lower()
    if name in IGNORED_DIRECTIVES:
        return
    if name == ".end":
        program.stop = True
        return
    handler = DIRECTIVE_HANDLERS.get(name)
    if handler is None:
        raise AsmError("unsupported directive: " + name, statement.file,
                       statement.line, statement.source)
    handler(program, statement)


def do_section(program, statement) -> None:
    """Switch to a named section, honouring the ``%nobits`` section type."""
    if not statement.operands:
        _wrong_count(statement)
    name = _unquote_name(statement.operands[0], statement)
    is_nobits = name == ".bss"
    for operand in statement.operands[1:]:
        if "nobits" in operand.lower():
            is_nobits = True
    program.set_section(name, is_nobits)


def do_simple_section(program, statement) -> None:
    """Switch to the section named by ``.text``, ``.data`` or ``.bss``."""
    if statement.operands:
        _wrong_count(statement)
    name = SECTION_NAMES[statement.mnemonic.lower()]
    program.set_section(name, name == ".bss")


def do_data(program, statement) -> None:
    """Emit one or more integer values with a fixed width."""
    if not statement.operands:
        _wrong_count(statement)
    size = DATA_SIZES[statement.mnemonic.lower()]
    if size == 4 and program.current_section.size % 4:
        program.diagnostics.warning("unaligned .word at section offset " +
                                    str(program.current_section.size), statement)
    specs = [(size, text) for text in statement.operands]
    program.emit_data(statement, specs)


def do_string(program, statement) -> None:
    """Emit one or more strings, optionally followed by a NUL byte."""
    if not statement.operands:
        _wrong_count(statement)
    add_nul = statement.mnemonic.lower() in (".asciz", ".string")
    data = bytearray()
    for operand in statement.operands:
        data.extend(parse_string(operand, statement))
        if add_nul:
            data.append(0)
    program.emit_literal_bytes(statement, bytes(data))


def do_space(program, statement) -> None:
    """Reserve a number of bytes with an optional fill value."""
    if len(statement.operands) not in (1, 2):
        _wrong_count(statement)
    count = _constant_value(program, statement, statement.operands[0])
    if count < 0:
        raise AsmError("space count must not be negative", statement.file,
                       statement.line, statement.source)
    fill = statement.operands[1] if len(statement.operands) == 2 else "0"
    Expression(fill, statement)
    program.emit_space(statement, count, fill)


def do_align(program, statement) -> None:
    """Align the current section using ARM, byte or power-of-two semantics."""
    if len(statement.operands) != 1:
        _wrong_count(statement)
    argument = _constant_value(program, statement, statement.operands[0])
    if argument < 0:
        raise AsmError("alignment must not be negative", statement.file,
                       statement.line, statement.source)
    name = statement.mnemonic.lower()
    if name == ".balign":
        if argument == 0 or argument & (argument - 1):
            raise AsmError("balign argument must be a power of two", statement.file,
                           statement.line, statement.source)
        alignment = argument
    else:
        alignment = 1 << argument
    program.align(statement, alignment)


def do_equ(program, statement) -> None:
    """Define an absolute symbol from a possibly forward expression."""
    if len(statement.operands) != 2:
        _wrong_count(statement)
    name = statement.operands[0]
    if not name or not (name[0].isalpha() or name[0] in "_.$"):
        raise AsmError("invalid symbol name: " + name, statement.file,
                       statement.line, statement.source)
    program.define_equ(name, statement.operands[1], statement)


def do_global(program, statement) -> None:
    """Mark a symbol as global."""
    if len(statement.operands) != 1:
        _wrong_count(statement)
    program.mark_global(statement.operands[0])


def do_thumb_func(program, statement) -> None:
    """Mark the next defined label as a Thumb function symbol."""
    if statement.operands:
        _wrong_count(statement)
    program.set_pending_thumb_func()


def do_ltorg(program, statement) -> None:
    """Flush the current section's pending literal pool."""
    if statement.operands:
        _wrong_count(statement)
    program.flush_pool(statement)


DIRECTIVE_HANDLERS = {
    ".text": do_simple_section,
    ".data": do_simple_section,
    ".bss": do_simple_section,
    ".section": do_section,
    ".word": do_data,
    ".long": do_data,
    ".4byte": do_data,
    ".hword": do_data,
    ".short": do_data,
    ".2byte": do_data,
    ".byte": do_data,
    ".ascii": do_string,
    ".asciz": do_string,
    ".string": do_string,
    ".space": do_space,
    ".skip": do_space,
    ".zero": do_space,
    ".align": do_align,
    ".balign": do_align,
    ".p2align": do_align,
    ".equ": do_equ,
    ".set": do_equ,
    ".global": do_global,
    ".globl": do_global,
    ".thumb_func": do_thumb_func,
    ".ltorg": do_ltorg,
    ".pool": do_ltorg,
}


def _unquote_name(text: str, statement) -> str:
    """Return a section name, accepting double-quoted names."""
    name = text.strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        return bytes(parse_string(name, statement)).decode("utf-8")
    return name


def _constant_value(program, statement, text: str) -> int:
    """Evaluate an expression whose value is needed during layout."""
    expression = Expression(text, statement)
    context = EvalContext(statement, None, "data")
    return expression.evaluate(program.symbols, context)


def _wrong_count(statement) -> None:
    """Raise the standard wrong-operand-count error."""
    raise AsmError("wrong operand count", statement.file, statement.line,
                   statement.source)
