
#include "decoder.h"

struct decodedInstruction decode(uint16_t hw, uint16_t hw2, uint32_t pc)
{
    (void)pc; // PC is used later when calculating branch targets

    struct decodedInstruction instruction = {
        .operation = OP_INVALID,
        .encoding = hw,
        .size = 2}; // initializing a new struct

    // 32-BIT THUMB INSTRUCTIONS

    if ((hw >> 11) >= 0x1D) // 32-bit Thumb instruction
    {
        instruction.size = 4;

        if ((hw & 0xF800) == 0xF000 &&
            (hw2 & 0xD000) == 0xD000) // BL immediate
        {
            instruction.operation = OP_BL;
            instruction.instructionFormat = FMT_BRANCH_LINK;
            instruction.encoding = ((uint32_t)hw << 16) | hw2;

            int s = (hw >> 10) & 0x1;   // Sign bit from bit 10
            int j1 = (hw2 >> 13) & 0x1; // J1 from bit 13
            int j2 = (hw2 >> 11) & 0x1; // J2 from bit 11

            int i1 = (j1 ^ s) ^ 1; // I1 = NOT(J1 XOR S)
            int i2 = (j2 ^ s) ^ 1; // I2 = NOT(J2 XOR S)

            int32_t imm10 = hw & 0x3FF;  // Immediate from bits 9-0
            int32_t imm11 = hw2 & 0x7FF; // Immediate from bits 10-0

            int32_t offset = (s << 24) |
                             (i1 << 23) |
                             (i2 << 22) |
                             (imm10 << 12) |
                             (imm11 << 1);

            if (s) // Negative branch offset
            {
                offset -= 0x02000000; // Sign extend the 25-bit offset
            }

            instruction.offset = offset;
        }
        else // Other 32-bit Thumb instructions are not supported
        {
            instruction.operation = OP_UNDEFINED;
            instruction.instructionFormat = FMT_INVALID;
            instruction.encoding = ((uint32_t)hw << 16) | hw2;
        }
    }

    // GROUP 1: SHIFT / ADD / SUB / MOV / CMP

    else if ((hw & 0xC000) == 0x0000)
    {

        // Special case of LSL: MOVS register T2

        if ((hw & 0xFFC0) == 0x0000)
        { // MOVS register T2

            instruction.operation = OP_MOV;
            instruction.instructionFormat = FMT_MOVS_REG;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3

            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x0000)
        { // LSL Immediate

            instruction.operation = OP_LSL;
            instruction.instructionFormat = FMT_LSL_IMM;
            instruction.rd = hw & 7;            // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7;   // Extract Rm from bits 5-3
            instruction.imm = (hw >> 6) & 0x1F; // Extract immediate form bits 10-6
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x0800)
        { // LSR Immediate

            instruction.operation = OP_LSR;
            instruction.instructionFormat = FMT_LSR_IMM;
            instruction.rd = hw & 7;            // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7;   // Extract Rm from bits 5-3
            instruction.imm = (hw >> 6) & 0x1F; // Extract immediate form bits 10-6

            if (instruction.imm == 0)
            { // value zero means shift 32 bits
                instruction.imm = 32;
            }

            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x1000)
        { // ASR Immediate

            instruction.operation = OP_ASR;
            instruction.instructionFormat = FMT_ASR_IMM;
            instruction.rd = hw & 7;            // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7;   // Extract Rm from bits 5-3
            instruction.imm = (hw >> 6) & 0x1F; // Extract immediate form bits 10-6

            if (instruction.imm == 0)
            { // value zero means shift 32 bits
                instruction.imm = 32;
            }

            instruction.sets_flags = 1;
        }

        else if ((hw & 0xFE00) == 0x1800)
        { // ADD register T1

            instruction.operation = OP_ADD;
            instruction.instructionFormat = FMT_ADD_REG;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = (hw >> 3) & 0x7; // Extract Rn from bits 5-3
            instruction.rm = (hw >> 6) & 0x7; // Extract Rm from bits 8-6
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xFE00) == 0x1A00)
        { // SUB Register T1

            instruction.operation = OP_SUB;
            instruction.instructionFormat = FMT_SUB_REG;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = (hw >> 3) & 0x7; // Extract Rn from bits 5-3
            instruction.rm = (hw >> 6) & 0x7; // Extract Rm from bits 8-6
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xFE00) == 0x1C00)
        { // ADD Immediate 3 bit

            instruction.operation = OP_ADD;
            instruction.instructionFormat = FMT_ADD_IMM3;
            instruction.rd = hw & 7;           // lower 3 bits
            instruction.rn = (hw >> 3) & 0x7;  // Extract Rn from bits 5-3
            instruction.imm = (hw >> 6) & 0x7; // Extract Imm from bits 8-6
            instruction.sets_flags = 1;
        }
        else if ((hw & 0xFE00) == 0x1E00)
        { // SUB Immediate 3 bit

            instruction.operation = OP_SUB;
            instruction.instructionFormat = FMT_SUB_IMM3;
            instruction.rd = hw & 7;           // lower 3 bits
            instruction.rn = (hw >> 3) & 0x7;  // Extract Rn from bits 5-3
            instruction.imm = (hw >> 6) & 0x7; // Extract Imm from bits 8-6
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x2000)
        { // MOVS

            instruction.operation = OP_MOV;
            instruction.instructionFormat = FMT_IMM8;
            instruction.rd = (hw >> 8) & 7; // shifting 8 bits to extract destination register
            instruction.imm = hw & 0x00FF;  // extracting the immediate
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x2800)
        { // Compare Immediate 8 bit

            instruction.operation = OP_CMP;
            instruction.instructionFormat = FMT_CMP_IMM8;

            instruction.rn = (hw >> 8) & 0x7; // Extract Rn from bits 10-8
            instruction.imm = hw & 0xFF;      // Extract Imm from bits 7-0
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x3000)
        { // ADD Immediate 8 bit

            instruction.operation = OP_ADD;
            instruction.instructionFormat = FMT_ADD_IMM8;
            instruction.rd = (hw >> 8) & 0x7; // Extract Rd from bits 10-8
            instruction.rn = (hw >> 8) & 0x7; // Extract Rn from bits 10-8
            instruction.imm = hw & 0xFF;      // Extract Imm from bits 7-0
            instruction.sets_flags = 1;
        }

        else if ((hw & 0xF800) == 0x3800)
        { // SUB Immediate 8 bit

            instruction.operation = OP_SUB;
            instruction.instructionFormat = FMT_SUB_IMM8;
            instruction.rd = (hw >> 8) & 0x7; // Extract Rd from bits 10-8
            instruction.rn = (hw >> 8) & 0x7; // Extract Rn from bits 10-8
            instruction.imm = hw & 0xFF;      // Extract Imm from bits 7-0
            instruction.sets_flags = 1;
        }
    }

    // GROUP 2: DATA PROCESSING

    else if ((hw & 0xFC00) == 0x4000)
    {

        int opcode = (hw >> 6) & 0xF;
        switch (opcode)
        {

        case 0x0: // AND Rdn = Rdn & Rm
            instruction.operation = OP_AND;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x1: // EOR: Rdn = Rdn ^ Rm
            instruction.operation = OP_EOR;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x2: // LSL register: shift Rdn left by Rm
            instruction.operation = OP_LSL;
            instruction.instructionFormat = FMT_REG_SHIFT;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x3: // LSR register: shift Rdn right by Rm
            instruction.operation = OP_LSR;
            instruction.instructionFormat = FMT_REG_SHIFT;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x4: // ASR register: arithmetic shift Rdn by Rm
            instruction.operation = OP_ASR;
            instruction.instructionFormat = FMT_REG_SHIFT;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x5: // ADC: Rdn = Rdn + Rm + carry
            instruction.operation = OP_ADC;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x6: // SBC: Rdn = Rdn - Rm - (1-carry)
            instruction.operation = OP_SBC;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x7: // ROR register rotate Rdn by Rm
            instruction.operation = OP_ROR;
            instruction.instructionFormat = FMT_REG_SHIFT;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x8: // TST: Rdn & Rm
            instruction.operation = OP_TST;
            instruction.instructionFormat = FMT_COMPARE_REG;
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0x9: // RSB: rd = 0 - Rm
            instruction.operation = OP_RSB;
            instruction.instructionFormat = FMT_REG_UNARY;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = (hw >> 3) & 0x7; // bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0xA: // CMP: Rdn - Rm
            instruction.operation = OP_CMP;
            instruction.instructionFormat = FMT_COMPARE_REG;
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0xB: // CMN: Rdn + Rm
            instruction.operation = OP_CMN;
            instruction.instructionFormat = FMT_COMPARE_REG;
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0xC: // ORR: Rdn = Rdn | Rm
            instruction.operation = OP_ORR;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0xD: // MUL: Rdm = Rdm * Rm
            instruction.operation = OP_MUL;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = (hw >> 3) & 0x7; // lower 3 bits
            instruction.rm = hw & 7;          // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0xE: // BIC: Rdn = Rdn & ~Rm
            instruction.operation = OP_BIC;
            instruction.instructionFormat = FMT_REG2;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rn = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;

        case 0xF: // MVN: Rdn = ~Rm
            instruction.operation = OP_MVN;
            instruction.instructionFormat = FMT_REG_UNARY;
            instruction.rd = hw & 7;          // lower 3 bits
            instruction.rm = (hw >> 3) & 0x7; // Extract Rm from bits 5-3
            instruction.sets_flags = 1;
            break;
        }
    }

    // GROUP 3: SPECIAL DATA / BX / BLX

    else if ((hw & 0xFC00) == 0x4400)
    { // opcode 0100 01
        int opcode = (hw >> 8) & 0x3;

        switch (opcode)
        {

        case 0x0: // ADD register T2: High registers
            instruction.operation = OP_ADD;
            instruction.instructionFormat = FMT_REG2;
            int lowerThreeBits = hw & 7;                // extracting the lower 3 bits
            int d = (hw >> 7) & 1;                      // extracting bit number 7
            instruction.rd = (d << 3) | lowerThreeBits; // rd is the concatenation of both
            instruction.rn = (d << 3) | lowerThreeBits; // rn is the concatenation of both
            instruction.rm = (hw >> 3) & 0xF;           // Extract Rm from bits 6-3
            instruction.sets_flags = 0;
            break;

        case 0x1: // CMP register T2 : High registers
            instruction.operation = OP_CMP;
            instruction.instructionFormat = FMT_COMPARE_REG;
            int lowerthreebits = hw & 7;                      // extracting the lower 3 bits
            int bitnum7 = (hw >> 7) & 1;                      // extracting bit number 7
            instruction.rn = (bitnum7 << 3) | lowerthreebits; // rd is the concatenation of both
            instruction.rm = (hw >> 3) & 0xF;                 // Extract Rm from bits 6-3
            instruction.sets_flags = 1;
            break;

        case 0x2:                                          // MOV register T1
            instruction.operation = OP_MOV;                // operation is move
            instruction.instructionFormat = FMT_MOV_REG;   // uses format move register
            int lowerthreeBits = hw & 7;                   // extracting the lower 3 bits
            int bit7 = (hw >> 7) & 1;                      // extracting bit number 7
            instruction.rd = (bit7 << 3) | lowerthreeBits; // rd is the concatenation of both
            instruction.rm = (hw >> 3) & 0xF;              // Extract Rm from bits 6-3
            instruction.sets_flags = 0;                    // move register T1 dont update the flags
            break;

        case 0x3: // BX / BLX register
            if ((hw & 0x7) == 0)
            { // bits 2-0 have to be zero

                if (((hw >> 7) & 0x1) == 0)
                { // Bit 7 = 0 means BX

                    instruction.operation = OP_BX;
                    instruction.instructionFormat = FMT_BRANCH_REG;
                    instruction.rm = (hw >> 3) & 0xF; // Extract Rm from bits 6-3
                    instruction.sets_flags = 0;
                }

                else if (((hw >> 7) & 0x1) == 1)
                { // Bit 7 = 1 means BLX

                    instruction.operation = OP_BLX;
                    instruction.instructionFormat = FMT_BRANCH_REG;
                    instruction.rm = (hw >> 3) & 0xF; // Extract Rm from bits 6-3
                    instruction.sets_flags = 0;
                }
            }

            break;
        }
    }

    // GROUP 4: LOAD / STORE

    else if (
        (hw & 0xF800) == 0x4800 || // opocode 01001
        (hw & 0xF000) == 0x5000 || // opcode 0101
        (hw & 0xE000) == 0x6000 || // opcode 0110 or 0111
        (hw & 0xF000) == 0x8000 || // opcode 1000
        (hw & 0xF000) == 0x9000    // opcode 1001
    )
    {

        if ((hw & 0xF800) == 0x4800) // LDR literal
        {

            instruction.operation = OP_LDR;
            instruction.instructionFormat = FMT_MEM_LITERAL;
            instruction.rd = (hw >> 8) & 0x7;   // rt from bits 10-8
            instruction.rn = 15;                // pc relative base
            instruction.imm = (hw & 0xFF) << 2; // i*4
        }

        else if ((hw & 0xF000) == 0x5000)
        {

            int opcode = (hw >> 9) & 0x7; // extract opcode from bits 11-9
            instruction.instructionFormat = FMT_MEM_REG;
            instruction.rd = hw & 0x7;        // rt from bits 2-0
            instruction.rn = (hw >> 3) & 0x7; // Base register from bits 5-3
            instruction.rm = (hw >> 6) & 0x7; // Offset register from bits 8-6
            switch (opcode)
            {

            case 0x0: // STR register
                instruction.operation = OP_STR;
                break;

            case 0x1: // STRH register
                instruction.operation = OP_STRH;
                break;

            case 0x2: // STRB register
                instruction.operation = OP_STRB;
                break;

            case 0x3: // LDRSB register
                instruction.operation = OP_LDRSB;
                break;

            case 0x4: // LDR register
                instruction.operation = OP_LDR;
                break;

            case 0x5: // LDRH register
                instruction.operation = OP_LDRH;
                break;

            case 0x6: // LDRB register
                instruction.operation = OP_LDRB;
                break;

            case 0x7: // LDRSH register
                instruction.operation = OP_LDRSH;
                break;
            }
        }

        else if ((hw & 0xF000) == 0x6000) // LDR and STR immediate
        {

            instruction.operation = (hw & 0x0800) ? OP_LDR : OP_STR; // if bit 11 is 1 then it is LDR
            instruction.instructionFormat = FMT_MEM_IMM;
            instruction.rd = hw & 0x7;                 // Rt: bits 2-0
            instruction.rn = (hw >> 3) & 0x7;          // Rn: bits 5-3
            instruction.imm = ((hw >> 6) & 0x1F) << 2; // imm5 from bits 10-6
        }

        else if ((hw & 0xF000) == 0x7000) // LDRB and STRB
        {

            instruction.operation = (hw & 0x0800) ? OP_LDRB : OP_STRB; // if bit 11 is 1 then it is lDRB
            instruction.instructionFormat = FMT_MEM_IMM;
            instruction.rd = hw & 0x7;          // rt: bits 2-0
            instruction.rn = (hw >> 3) & 0x7;   // rn: bits 5-3
            instruction.imm = (hw >> 6) & 0x1F; // imm5 from bits 10-6
        }

        else if ((hw & 0xF000) == 0x8000) // LDRH AND STRH
        {

            instruction.operation = (hw & 0x0800) ? OP_LDRH : OP_STRH; // if bit 11 is 1 then it is lDRH
            instruction.instructionFormat = FMT_MEM_IMM;
            instruction.rd = hw & 0x7;                 // Rt: bits 2-0
            instruction.rn = (hw >> 3) & 0x7;          // Rn: bits 5-3
            instruction.imm = ((hw >> 6) & 0x1F) << 1; // imm5 from bits 10-6
        }

        else if ((hw & 0xF000) == 0x9000) // SP Relative word
        {

            instruction.operation = (hw & 0x0800) ? OP_LDR : OP_STR; // if bit 11 is 1 then it is lDR
            instruction.instructionFormat = FMT_MEM_SP;
            instruction.rd = (hw >> 8) & 0x7;   // Rt: bits 10-8
            instruction.rn = 13;                // SP
            instruction.imm = (hw & 0xFF) << 2; // imm8 = i*4
        }
    }

    // GROUP 5: ADR / ADD SP-RELATIVE

    else if ((hw & 0xF000) == 0xA000) // ADR / ADD SP-RELATIVE
    {
        instruction.operation = (hw & 0x0800) ? OP_ADD : OP_ADR; // if bit 11 is 1 then it is ADD SP-RELATIVE
        instruction.instructionFormat = FMT_ADD_SP_PC_IMM;
        instruction.rd = (hw >> 8) & 0x7;
        instruction.rn = (hw & 0x0800) ? 13 : 15; // if bit 11 is 1 then it is SP else it is PC
        instruction.imm = (hw & 0xFF) << 2;
    }

    // GROUP 6: MISCELLANEOUS

    else if ((hw & 0xF000) == 0xB000) // Miscellaneous instructions
    {
        if ((hw & 0xFF00) == 0xB000) // ADD/SUB SP immediate
        {
            instruction.operation = (hw & 0x0080) ? OP_SUB : OP_ADD;
            instruction.instructionFormat = FMT_SP_IMM;
            instruction.rd = 13;                // Destination is SP
            instruction.rn = 13;                // First source is SP
            instruction.imm = (hw & 0x7F) << 2; // imm7 multiplied by 4
        }

        else if ((hw & 0xFF00) == 0xB200) // SXTH, SXTB, UXTH, UXTB
        {
            int opcode = (hw >> 6) & 0x3; // Opcode from bits 7-6

            instruction.instructionFormat = FMT_REG_UNARY;
            instruction.rd = hw & 0x7;        // Rd from bits 2-0
            instruction.rm = (hw >> 3) & 0x7; // Rm from bits 5-3

            switch (opcode)
            {
            case 0x0: // SXTH
                instruction.operation = OP_SXTH;
                break;

            case 0x1: // SXTB
                instruction.operation = OP_SXTB;
                break;

            case 0x2: // UXTH
                instruction.operation = OP_UXTH;
                break;

            case 0x3: // UXTB
                instruction.operation = OP_UXTB;
                break;
            }
        }

        else if ((hw & 0xFE00) == 0xB400) // PUSH
        {
            instruction.operation = OP_PUSH;
            instruction.instructionFormat = FMT_PUSH_POP;
            instruction.rn = 13;             // Stack pointer
            instruction.regList = hw & 0xFF; // Register list from bits 7-0

            if (hw & 0x0100) // Bit 8 includes LR
            {
                instruction.regList |= (1 << 14); // Add R14 to register list
            }
        }

        else if ((hw & 0xFE00) == 0xBC00) // POP
        {
            instruction.operation = OP_POP;
            instruction.instructionFormat = FMT_PUSH_POP;
            instruction.rn = 13;             // Stack pointer
            instruction.regList = hw & 0xFF; // Register list from bits 7-0

            if (hw & 0x0100) // Bit 8 includes PC
            {
                instruction.regList |= (1 << 15); // Add R15 to register list
            }
        }

        else if ((hw & 0xFF00) == 0xBA00) // REV, REV16, REVSH
        {
            int opcode = (hw >> 6) & 0x3; // Opcode from bits 7-6

            instruction.instructionFormat = FMT_REG_UNARY;
            instruction.rd = hw & 0x7;        // Rd from bits 2-0
            instruction.rm = (hw >> 3) & 0x7; // Rm from bits 5-3

            switch (opcode)
            {
            case 0x0: // REV
                instruction.operation = OP_REV;
                break;

            case 0x1: // REV16
                instruction.operation = OP_UNDEFINED;
                instruction.instructionFormat = FMT_INVALID;
                break;

            case 0x2: // Undefined encoding
                instruction.operation = OP_UNDEFINED;
                instruction.instructionFormat = FMT_INVALID;
                break;

            case 0x3: // REVSH
                instruction.operation = OP_UNDEFINED;
                instruction.instructionFormat = FMT_INVALID;
                break;
            }
        }

        else if (hw == 0xBF00) // NOP
        {
            instruction.operation = OP_NOP;
            instruction.instructionFormat = FMT_NOP;
        }
    }

    // GROUP 7: MULTIPLE LOAD / STORE

    else if ((hw & 0xF000) == 0xC000) // Load and store multiple
    {
        instruction.operation = (hw & 0x0800) ? OP_LDM : OP_STM; // if bit 11 is 1 then it is LDM
        instruction.instructionFormat = FMT_MEM_MULTIPLE;
        instruction.rn = (hw >> 8) & 0x7;
        instruction.regList = hw & 0xFF;
    }

    // GROUP 8: CONDITIONAL BRANCH / SVC

    else if ((hw & 0xF000) == 0xD000) // conditional B, SVC, and undefined
    {
        unsigned int cond = (hw >> 8) & 0xF;

        if (cond == 0xF) // SVC
        {
            instruction.operation = OP_SVC;
            instruction.instructionFormat = FMT_SVC;
            instruction.imm = hw & 0xFF;
        }
        else if (cond == 0xE) // UNDEFINED
        {
            instruction.operation = OP_UNDEFINED;
            instruction.instructionFormat = FMT_UDF;
            instruction.imm = hw & 0xFF;
        }
        else // BRANCH
        {
            instruction.operation = OP_B;
            instruction.instructionFormat = FMT_BRANCH_COND;
            instruction.condition = cond;

            int8_t imm8 = (hw & 0xFF);
            instruction.offset = imm8 * 2;
        }
    }

    // GROUP 9: UNCONDITIONAL BRANCH

    else if ((hw & 0xF800) == 0xE000) // B unconditional
    {
        instruction.operation = OP_B;
        instruction.instructionFormat = FMT_BRANCH_UNCOND;

        int32_t imm11 = hw & 0x7FF; // Immediate from bits 10-0

        if (imm11 & 0x400) // Bit 10 means the offset is negative
        {
            imm11 -= 0x800; // Sign extend the 11-bit immediate
        }

        instruction.offset = imm11 * 2; // Branch offset in bytes
    }

    // Any remaining encoding is not supported by this simulator.
    if (instruction.operation == OP_INVALID)
    {
        instruction.operation = OP_UNDEFINED;
        instruction.instructionFormat = FMT_INVALID;
    }

    return instruction;
}
