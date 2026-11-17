
#include <stdio.h>
#include <string.h>
#include "disassembler.h"

static const char *registerNames[] = {
    "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
    "r8", "r9", "r10", "r11", "r12", "sp", "lr", "pc"};

// Get the instruction name
static const char *getName(enum op operation)
{
    switch (operation)
    {
    case OP_MOV:
        return "mov";
    case OP_MVN:
        return "mvn";
    case OP_ADD:
        return "add";
    case OP_ADR:
        return "adr";
    case OP_ADC:
        return "adc";
    case OP_SUB:
        return "sub";
    case OP_SBC:
        return "sbc";
    case OP_RSB:
        return "rsb";
    case OP_MUL:
        return "mul";
    case OP_AND:
        return "and";
    case OP_ORR:
        return "orr";
    case OP_EOR:
        return "eor";
    case OP_BIC:
        return "bic";
    case OP_TST:
        return "tst";
    case OP_LSL:
        return "lsl";
    case OP_LSR:
        return "lsr";
    case OP_ASR:
        return "asr";
    case OP_ROR:
        return "ror";
    case OP_CMP:
        return "cmp";
    case OP_CMN:
        return "cmn";
    case OP_SXTB:
        return "sxtb";
    case OP_SXTH:
        return "sxth";
    case OP_UXTB:
        return "uxtb";
    case OP_UXTH:
        return "uxth";
    case OP_REV:
        return "rev";
    case OP_LDR:
        return "ldr";
    case OP_LDRB:
        return "ldrb";
    case OP_LDRH:
        return "ldrh";
    case OP_LDRSB:
        return "ldrsb";
    case OP_LDRSH:
        return "ldrsh";
    case OP_STR:
        return "str";
    case OP_STRB:
        return "strb";
    case OP_STRH:
        return "strh";
    case OP_LDM:
        return "ldmia";
    case OP_STM:
        return "stmia";
    case OP_PUSH:
        return "push";
    case OP_POP:
        return "pop";
    case OP_B:
        return "b";
    case OP_BL:
        return "bl";
    case OP_BX:
        return "bx";
    case OP_BLX:
        return "blx";
    case OP_SVC:
        return "svc";
    case OP_NOP:
        return "nop";
    case OP_UNDEFINED:
        return "undefined";
    default:
        return "invalid";
    }
}

// Convert register mask into a list like {r4, r5, lr}
static void getRegisters(uint16_t list, char *buffer)
{
    int first = 1;
    strcpy(buffer, "{");

    for (int i = 0; i < 16; i++)
    {
        if (list & (1u << i))
        {
            if (!first)
                strcat(buffer, ", ");

            strcat(buffer, registerNames[i]);
            first = 0;
        }
    }

    strcat(buffer, "}");
}

// Convert decoded instruction into assembly text
void disassemble(struct decodedInstruction instruction,
                 uint32_t pc,
                 char *buffer,
                 size_t bufferSize)
{
    if (buffer == NULL || bufferSize == 0)
        return;

    if (instruction.operation == OP_UNDEFINED ||
        instruction.operation == OP_INVALID)
    {
        snprintf(buffer, bufferSize, "%s",
                 getName(instruction.operation));
        return;
    }

    const char *name = getName(instruction.operation);
    const char *s = instruction.sets_flags ? "s" : "";
    char registers[96];

    // Check register numbers
    if (instruction.rd < 0 || instruction.rd > 15 ||
        instruction.rn < 0 || instruction.rn > 15 ||
        instruction.rm < 0 || instruction.rm > 15)
    {
        snprintf(buffer, bufferSize, "invalid");
        return;
    }

    const char *rd = registerNames[instruction.rd];
    const char *rn = registerNames[instruction.rn];
    const char *rm = registerNames[instruction.rm];

    switch (instruction.instructionFormat)
    {
    case FMT_IMM8: // MOVS immediate
        snprintf(buffer, bufferSize, "movs %s, #%u",
                 rd, (unsigned)instruction.imm);
        break;

    case FMT_LSL_IMM:
    case FMT_LSR_IMM:
    case FMT_ASR_IMM:
        snprintf(buffer, bufferSize, "%s%s %s, %s, #%u",
                 name, s, rd, rm, (unsigned)instruction.imm);
        break;

    case FMT_ADD_REG:
    case FMT_SUB_REG:
        snprintf(buffer, bufferSize, "%s%s %s, %s, %s",
                 name, s, rd, rn, rm);
        break;

    case FMT_ADD_IMM3:
    case FMT_SUB_IMM3:
        snprintf(buffer, bufferSize, "%s%s %s, %s, #%u",
                 name, s, rd, rn, (unsigned)instruction.imm);
        break;

    case FMT_ADD_IMM8:
    case FMT_SUB_IMM8:
        snprintf(buffer, bufferSize, "%s%s %s, #%u",
                 name, s, rd, (unsigned)instruction.imm);
        break;

    case FMT_CMP_IMM8:
        snprintf(buffer, bufferSize, "cmp %s, #%u",
                 rn, (unsigned)instruction.imm);
        break;

    case FMT_MOV_REG:
        // MOV r8, r8 is also a NOP alias
        if (instruction.encoding == 0x46C0)
            snprintf(buffer, bufferSize, "nop");
        else
            snprintf(buffer, bufferSize, "%s %s, %s",
                     name, rd, rm);
        break;

    case FMT_MOVS_REG:
        snprintf(buffer, bufferSize, "movs %s, %s", rd, rm);
        break;

    case FMT_REG2:
        if (instruction.operation == OP_MUL)
            snprintf(buffer, bufferSize, "muls %s, %s", rd, rn);
        else
            snprintf(buffer, bufferSize, "%s%s %s, %s",
                     name, s, rd, rm);
        break;

    case FMT_REG_SHIFT:
    case FMT_LSL_REG:
    case FMT_LSR_REG:
    case FMT_ASR_REG:
        snprintf(buffer, bufferSize, "%s%s %s, %s",
                 name, s, rd, rm);
        break;

    case FMT_COMPARE_REG:
        snprintf(buffer, bufferSize, "%s %s, %s",
                 name, rn, rm);
        break;

    case FMT_REG_UNARY:
        if (instruction.operation == OP_RSB)
            snprintf(buffer, bufferSize, "negs %s, %s",
                     rd, rn);
        else
            snprintf(buffer, bufferSize, "%s%s %s, %s",
                     name, s, rd, rm);
        break;

    case FMT_BRANCH_REG:
        snprintf(buffer, bufferSize, "%s %s", name, rm);
        break;

    case FMT_MEM_REG:
        snprintf(buffer, bufferSize, "%s %s, [%s, %s]",
                 name, rd, rn, rm);
        break;

    case FMT_MEM_IMM:
        snprintf(buffer, bufferSize, "%s %s, [%s, #%u]",
                 name, rd, rn, (unsigned)instruction.imm);
        break;

    case FMT_MEM_SP:
        snprintf(buffer, bufferSize, "%s %s, [sp, #%u]",
                 name, rd, (unsigned)instruction.imm);
        break;

    case FMT_MEM_LITERAL:
        snprintf(buffer, bufferSize, "ldr %s, [pc, #%u]",
                 rd, (unsigned)instruction.imm);
        break;

    case FMT_ADD_SP_PC_IMM:
        if (instruction.operation == OP_ADR)
            snprintf(buffer, bufferSize, "add %s, pc, #%u",
                     rd, (unsigned)instruction.imm);
        else
            snprintf(buffer, bufferSize, "add %s, sp, #%u",
                     rd, (unsigned)instruction.imm);
        break;

    case FMT_SP_IMM:
        snprintf(buffer, bufferSize, "%s sp, #%u",
                 name, (unsigned)instruction.imm);
        break;

    case FMT_PUSH_POP:
        getRegisters(instruction.regList, registers);
        snprintf(buffer, bufferSize, "%s %s",
                 name, registers);
        break;

    case FMT_MEM_MULTIPLE:
        getRegisters(instruction.regList, registers);

        if (instruction.operation == OP_LDM &&
            (instruction.regList & (1u << instruction.rn)))
        {
            snprintf(buffer, bufferSize, "%s %s, %s",
                     name, rn, registers);
        }
        else
        {
            snprintf(buffer, bufferSize, "%s %s!, %s",
                     name, rn, registers);
        }
        break;

    case FMT_BRANCH_COND:
    {
        static const char *conditions[] = {
            "eq", "ne", "cs", "cc",
            "mi", "pl", "vs", "vc",
            "hi", "ls", "ge", "lt",
            "gt", "le"};

        if (instruction.condition < 0 ||
            instruction.condition > 13)
        {
            snprintf(buffer, bufferSize, "invalid");
            break;
        }

        uint32_t target = pc + 4u + (uint32_t)instruction.offset;

        snprintf(buffer, bufferSize, "b%s %x",
                 conditions[instruction.condition],
                 (unsigned)target);
        break;
    }

    case FMT_BRANCH_UNCOND:
    case FMT_BRANCH_LINK:
    {
        uint32_t target = pc + 4u + (uint32_t)instruction.offset;

        snprintf(buffer, bufferSize, "%s %x",
                 name, (unsigned)target);
        break;
    }

    case FMT_SVC:
        snprintf(buffer, bufferSize, "svc %u",
                 (unsigned)instruction.imm);
        break;

    case FMT_NOP:
        snprintf(buffer, bufferSize, "nop");
        break;

    case FMT_UDF:
        snprintf(buffer, bufferSize, "undefined");
        break;

    default:
        snprintf(buffer, bufferSize, "invalid");
        break;
    }
}
