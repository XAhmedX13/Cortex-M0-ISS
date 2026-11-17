#pragma once
#include <stdint.h>

enum op
{ // opcode for the operationS

    OP_INVALID,   // INVALID OPCODE
    OP_UNDEFINED, // REAL INSTRUCTION BUT NOT IMPLEMENTED

    // move instructions
    OP_MOV,
    OP_MVN,

    // Arthemitic instructions
    OP_ADD,
    OP_ADR,
    OP_ADC,
    OP_SUB,
    OP_SBC,
    OP_RSB, //(NEG)
    OP_MUL,

    // Logic and shifts
    OP_AND,
    OP_ORR,
    OP_EOR,
    OP_BIC,
    OP_TST,
    OP_LSL,
    OP_LSR,
    OP_ASR,
    OP_ROR,

    // Compare
    OP_CMP,
    OP_CMN,

    // Extend and reverse
    OP_SXTB,
    OP_SXTH,
    OP_UXTB,
    OP_UXTH,
    OP_REV,

    // Load and store
    OP_LDR,
    OP_LDRB,
    OP_LDRH,
    OP_LDRSB,
    OP_LDRSH,
    OP_STR,
    OP_STRB,
    OP_STRH,

    // Multiple
    OP_LDM,
    OP_STM,
    OP_PUSH,
    OP_POP,

    // Control
    OP_B, //(including conditional B)
    OP_BL,
    OP_BX,
    OP_BLX, //(register)

    // System
    OP_SVC,
    OP_NOP,
};

enum format
{

    FMT_INVALID, // INVALID FORMAT
    FMT_IMM8,    // 8 bit Immediate format

    FMT_LSL_IMM, // Logical shift left immediate
    FMT_LSL_REG, // logical shift left by register

    FMT_LSR_IMM, // Logical shift right immediate
    FMT_LSR_REG, // logical Shoft right by register

    FMT_ASR_IMM, // Arithmetic Shift Right immediate
    FMT_ASR_REG, // Arithmetic Shift Right register

    FMT_ADD_REG,       // Add register
    FMT_ADD_IMM3,      // Add immediate Of size 3
    FMT_ADD_IMM8,      // Add immediate Of size 8
    FMT_ADD_SP_PC_IMM, // Add scaled immediate to SP or aligned PC

    FMT_SUB_REG,  // Sub register
    FMT_SUB_IMM3, // sub immediate Of size 3
    FMT_SUB_IMM8, // sub immediate Of size 8

    FMT_CMP_IMM8, // compare 8 bit immediate

    FMT_MOV_REG,  // Mov register T1
    FMT_MOVS_REG, // Movs register T2

    FMT_REG2,        // Rd is also the first source register
    FMT_REG_SHIFT,   // Register-controlled shift or rotate
    FMT_COMPARE_REG, // Two source registers, flags only
    FMT_REG_UNARY,   // Destination and one source register

    FMT_BRANCH_REG,

    FMT_MEM_REG,
    FMT_MEM_IMM,
    FMT_MEM_SP,
    FMT_MEM_LITERAL,
    FMT_SP_IMM,
    FMT_MEM_MULTIPLE,
    FMT_PUSH_POP,
    FMT_NOP,
    FMT_BRANCH_COND,
    FMT_BRANCH_UNCOND,
    FMT_BRANCH_LINK,
    FMT_SVC,
    FMT_UDF
};

struct decodedInstruction
{

    enum op operation;
    enum format instructionFormat;

    int rd;   // destination register
    int rn;   // first source register or base register
    int rm;   // second source register or offset register
    int size; // instruction length (2 or 4 bytes)
    int condition;
    int sets_flags;

    uint32_t imm;      // 32 bit immediate
    uint32_t encoding; // 32 bit encoded instruction
    int32_t offset;    // signed 32 offset

    uint16_t regList; // a mask register for push, pop, LDM, and STM
};

struct decodedInstruction decode(uint16_t hw, uint16_t hw2, uint32_t pc);
