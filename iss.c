/* iss.c -- CSCE 2303 Cortex-M0 simulator skeleton.
   Build: gcc -O2 -Wall -o iss iss.c      Run: ./iss prog.dump */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include "decoder.h"

#define ROM_BASE  0x00000000u
#define ROM_SIZE  (1u << 20)              /* 1 MB   */
#define RAM_BASE  0x20000000u
#define RAM_SIZE  (256u << 10)            /* 256 KB */
#define MAX_INSTR 100000000ull

uint8_t  rom[ROM_SIZE], ram[RAM_SIZE];
uint32_t r[16];                    /* r[13] = sp, r[14] = lr, r[15] = pc */
int      N, Z, C, V;               /* the APSR flags */
uint64_t instret;

void fault(const char *kind)
{
    fprintf(stderr, "FAULT %s at pc=0x%08x\n", kind, r[15]);
    exit(255);
}

/* Pointer to the byte at addr, or NULL if addr is unmapped. */
uint8_t *mem_ptr(uint32_t addr)
{
    if (addr - ROM_BASE < ROM_SIZE) return &rom[addr - ROM_BASE];
    if (addr - RAM_BASE < RAM_SIZE) return &ram[addr - RAM_BASE];
    return NULL;
}

uint32_t read_mem(uint32_t addr, int size)       /* size = 1, 2 or 4 */
{
    if (addr % size) fault("UNALIGNED");
    uint8_t *p = mem_ptr(addr);
    if (!p) fault("BUS");
    uint32_t v = 0;
    for (int i = size - 1; i >= 0; i--)                  /* little-endian */
        v = (v << 8) | p[i];
    return v;
}

void write_mem(uint32_t addr, uint32_t v, int size)
{
    if (addr % size) fault("UNALIGNED");
    if (addr - RAM_BASE >= RAM_SIZE) fault("BUS");       /* only RAM is writable */
    for (int i = 0; i < size; i++)
        ram[addr - RAM_BASE + i] = (uint8_t)(v >> (8 * i));
}

/* Load a `readelf -x` dump. A data line looks like
     "  0x00000100 094811df 0a2000f0 03f812df 002000df .H... ......"
   The 35 characters after the address hold up to 16 bytes; the rest is ASCII. */
void load_dump(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(253); }
    char line[256];
    while (fgets(line, sizeof line, f)) {
        char *s = line;
        while (*s == ' ') s++;
        if (strncmp(s, "0x", 2) != 0) continue;          /* headers, blank lines */
        uint32_t addr = (uint32_t)strtoul(s, &s, 16);
        s++;                                             /* the space after the address */
        for (int i = 0; i + 1 < 35 && s[i] && s[i] != '\n'; ) {
            if (s[i] == ' ') { i++; continue; }
            unsigned byte;
            if (sscanf(s + i, "%2x", &byte) != 1) break;
            uint8_t *p = mem_ptr(addr++);
            if (!p) { fprintf(stderr, "load error\n"); exit(253); }
            *p = (uint8_t)byte;
            i += 2;
        }
    }
    fclose(f);
}

void reset(void)
{
    r[13] = read_mem(0, 4);                  /* initial sp   */
    uint32_t pc = read_mem(4, 4);            /* reset vector */
    r[15] = pc;                            /* diagnostic uses the reset vector */
    if (!(pc & 1)) fault("INVSTATE");
    r[15] = pc & ~1u;
    r[14] = 0xFFFFFFFFu;
}

void set_nz(uint32_t x) { N = x >> 31; Z = (x == 0); }

void svc(int n)
{
    switch (n) {
    case 0x00: exit(r[0] & 0xFF);                                    /* EXIT    */
    case 0x10: putchar(r[0] & 0xFF); break;                          /* PUTCHAR */
    case 0x11: for (uint32_t a = r[0]; read_mem(a, 1); a++)          /* PUTS    */
                   putchar(read_mem(a, 1));
               break;
    case 0x12: printf("%d", (int32_t)r[0]); break;                   /* PUTINT  */
    /* TODO: the other services in section 5 of the handout */
    default:   fault("UNDEFINED");
    }
}

uint32_t calculate_addr(struct decodedInstruction instruction) {
    uint32_t n = r[instruction.rn];
    switch (instruction.instructionFormat)
    {
        case FMT_MEM_REG:
            return n + r[instruction.rm];
        case FMT_MEM_IMM:
            return n + instruction.imm;
        case FMT_MEM_LITERAL:
            return ((r[15] + 4) & ~3u) + instruction.imm;
        case FMT_MEM_SP:
            return n + instruction.imm;
        default:
            return 0;
    }
}

int cond_passed(int cond) {
    switch (cond) {
    case 0x0: return Z == 1;                    /* EQ */
    case 0x1: return Z == 0;                    /* NE */
    case 0x2: return C == 1;                    /* CS/HS */
    case 0x3: return C == 0;                    /* CC/LO */
    case 0x4: return N == 1;                    /* MI */
    case 0x5: return N == 0;                    /* PL */
    case 0x6: return V == 1;                    /* VS */
    case 0x7: return V == 0;                    /* VC */
    case 0x8: return C == 1 && Z == 0;          /* HI */
    case 0x9: return !(C == 1 && Z == 0);       /* LS */
    case 0xA: return N == V;                    /* GE */
    case 0xB: return N != V;                    /* LT */
    case 0xC: return Z == 0 && N == V;          /* GT */
    case 0xD: return !(Z == 0 && N == V);       /* LE */
    }
    return 1;
}

/* Execute one instruction. r[15] holds the address of the current
   instruction; an instruction that reads pc must see r[15] + 4. */
void step(void)
{
    uint32_t pc = r[15];
    uint32_t hw = read_mem(pc, 2);
    uint32_t hw2 = read_mem(pc + 2, 2);
    uint32_t next = pc + 2;

    struct decodedInstruction instruction = decode(hw, hw2, pc);
    uint32_t n, m, res = 0, addr, v;
    switch (instruction.operation) {
        case OP_INVALID:
            fault("INVALID");
            break;
        case OP_UNDEFINED:
            fault("UNDEFINED");
            break;

        // Move instructions
        case OP_MOV:
            if (instruction.instructionFormat == FMT_MOV_REG) {
                res = r[instruction.rn];
            } else {
                res = instruction.imm;
            }
            r[instruction.rd] = res;
            break;
        case OP_MVN:
            res = ~r[instruction.rn];
            r[instruction.rd] = res;
            break;

        // Arthemitic instructions
        case OP_ADD:
            n = r[instruction.rn];
            m = r[instruction.rm];
            if (instruction.instructionFormat != FMT_ADD_REG &&
                instruction.instructionFormat != FMT_REG2) {
                m = instruction.imm;
            }
            if (instruction.rn == 15) {
                n = (r[15] + 4) & ~3u;      /* pc-relative: Align(pc + 4) */
            }
            res = n + m;
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = (res < n);
                V = !(n>>31 ^ m>>31) && (res>>31 ^ n>>31);
            }
            break;
        case OP_ADR:
            uint32_t aligned_pc = (pc + 4) & ~3u;
            r[instruction.rd] = aligned_pc + instruction.imm;
            break;
        case OP_ADC:
            n = r[instruction.rn];
            m = r[instruction.rm];
            uint64_t sum = (uint64_t)n + m + C;
            res = (uint32_t)sum;
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = (sum >> 32) & 1;
                V = !(n>>31 ^ m>>31) && (res>>31 ^ n>>31);
            }
            break;
        case OP_SUB:
            n = r[instruction.rn];
            m = r[instruction.rm];
            if (instruction.instructionFormat != FMT_SUB_REG) {
                m = instruction.imm;
            }
            res = n - m;
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = (n >= m);
                V = (n>>31 ^ m>>31) && (n>>31 ^ res>>31); 
            }
            break;
        case OP_SBC:
            n = r[instruction.rn];
            m = r[instruction.rm];
            uint64_t sub = (uint64_t)n - m - !C;
            res = (uint32_t)sub;
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = ((uint64_t)n >= ((uint64_t)m + !C));
                V = (n>>31 ^ m>>31) && (n>>31 ^ res>>31);
            }
            break;
        case OP_RSB:
            n = r[instruction.rn];
            res = 0 - n;
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = (n == 0);
                V = n>>31 && res>>31;
            }
            break;
        case OP_MUL:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n * m;
            r[instruction.rd] = res;
            break;

        // Logic and shifts
        case OP_AND:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n & m;
            r[instruction.rd] = res;
            break;
        case OP_ORR:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n | m;
            r[instruction.rd] = res;
            break;
        case OP_EOR:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n ^ m;
            r[instruction.rd] = res;
            break;
        case OP_BIC:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n & ~m;
            r[instruction.rd] = res;
            break;
        case OP_TST:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n & m;
            break;
        case OP_LSL:
            n = r[instruction.rn];
            m = r[instruction.rm] & 0xFF;
            int carry = C;
            if (instruction.instructionFormat == FMT_LSL_IMM) {
                m = instruction.imm;
            }
            if (m == 0) {
                res = n;
            }
            else if (m < 32) {
                res = n << m;
                carry = (n >> (32-m)) & 1;
            }
            else if (m == 32) {
                res = 0; 
                carry = n & 1;
            }
            else {
                res = 0;
                carry = 0;
            }
            if (instruction.sets_flags) {
                C = carry;
            }
            break;
        case OP_LSR:
            n = r[instruction.rn];
            m = r[instruction.rm] & 0xFF;
            carry = C;
            if (instruction.instructionFormat == FMT_LSR_IMM) {
                m = instruction.imm;
                if (m == 0) {
                    m = 32;
                }
            }

            if (m == 0) {
                res = n;
            }
            else if (m < 32) {
                res = n >> m;
                carry = (n >> (m-1)) & 1;
            }
            else if (m == 32) {
                res = 0;
                carry = n >> 31;
            }
            else {
                res = 0;
                carry = 0;
            }

            r[instruction.rd] = res;

            if (instruction.sets_flags) {
                C = carry;
            }
            break;
        case OP_ASR:
            n = r[instruction.rn];
            m = r[instruction.rm] & 0xFF;
            if (instruction.instructionFormat == FMT_ASR_IMM) {
                m = instruction.imm;
                if (m == 0) {
                    m = 32;
                }
            }
            int sign = n >> 31;
            carry = C;
            if (m == 0) {
                res = n;
            }
            else if (m < 32) {
                res = n >> m;
                if (sign) {
                    res |= (UINT32_MAX << (32 - m));
                }
                carry = (n >> (m-1)) & 1;
            }
            else {
                res = sign ? UINT32_MAX : 0;
                carry = sign;
            }
            r[instruction.rd] = res;

            if (instruction.sets_flags) {
                C = carry;
            }
            break;
        case OP_ROR:
            n = r[instruction.rn];
            m = r[instruction.rm] & 0xFF;
            carry = C;
            if (m == 0) {
                res = n;
            }
            else {
                m %= 32;
                if (m == 0) {
                    res = n;
                    carry = n >> 31;
                }
                else {
                    res = (n >> m) | (n << (32 - m));
                    carry = (res >> 31);
                }
            }
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = carry;
            }
            break;

        // Compare
        case OP_CMP:
            n = r[instruction.rn];
            m = r[instruction.rm];
            if (instruction.instructionFormat == FMT_CMP_IMM8) {
                m = instruction.imm;
            }
            res = n - m;
            C = (n >= m);
            V = (n>>31 ^ m>>31) && (n>>31 ^ res>>31);
            break;
        case OP_CMN:
            n = r[instruction.rn];
            m = r[instruction.rm];
            res = n + m;
            C = (res < n);
            V = !(n>>31 ^ m>>31) && (res>>31 ^ n>>31);
            break;
        
        // Extend and reverse
        case OP_SXTB:
            n = r[instruction.rn] & 0xFF;
            sign = n >> 7;
            r[instruction.rd] = sign ? (n | (UINT32_MAX << 8)) : n;
            break;
        case OP_SXTH:
            n = r[instruction.rn] & 0xFFFF;
            sign = n >> 15;
            r[instruction.rd] = sign ? (n | (UINT32_MAX << 16)) : n;
            break;
        case OP_UXTB:
            r[instruction.rd] = r[instruction.rn] & 0xFF;
            break;
        case OP_UXTH:
            r[instruction.rd] = r[instruction.rn] & 0xFFFF;
            break;
        case OP_REV:
            n = r[instruction.rn];
            r[instruction.rd] = ((n >> 24) & 0xFF) | ((n >> 8) & 0xFF00) | ((n << 8) & 0xFF0000) | ((n << 24) & 0xFF000000);
            break;

        // Load and store
        case OP_LDR:
            addr = calculate_addr(instruction);
            r[instruction.rd] = read_mem(addr, 4);
            break;
        case OP_LDRB:
            addr = calculate_addr(instruction);
            r[instruction.rd] = read_mem(addr, 1);
            break;
        case OP_LDRH:
            addr = calculate_addr(instruction);
            r[instruction.rd] = read_mem(addr, 2);
            break;
        case OP_LDRSB:
            addr = calculate_addr(instruction);
            res = read_mem(addr, 1);
            sign = res >> 7;
            r[instruction.rd] = sign ? res | (UINT32_MAX << 8) : res;
            break;
        case OP_LDRSH:
            addr = calculate_addr(instruction);
            res = read_mem(addr, 2);
            sign = res >> 15;
            r[instruction.rd] = sign ? res | (UINT32_MAX << 16) : res;
            break;
        case OP_STR:
            v = r[instruction.rd];
            addr = calculate_addr(instruction);
            write_mem(addr, v, 4);
            break;
        case OP_STRB:
            v = r[instruction.rd];
            addr = calculate_addr(instruction);
            write_mem(addr, v, 1);
            break;
        case OP_STRH:
            v = r[instruction.rd];
            addr = calculate_addr(instruction);
            write_mem(addr, v, 2);
            break;

        // Multiple
        case OP_LDM:
            addr = r[instruction.rn];
            for (int i = 0; i < 16; ++i) {
                if (instruction.regList & (1u << i)) {
                    r[i] = read_mem(addr, 4);
                    addr += 4;
                }
            }
            if (!(instruction.regList & (1u << instruction.rn))) {
                r[instruction.rn] = addr;
            }
            break;
        case OP_STM:
            addr = r[instruction.rn];
            for (int i = 0; i < 16; ++i) {
                if (instruction.regList & (1u << i)) {
                    write_mem(addr, r[i], 4);
                    addr += 4;
                }
            }
            r[instruction.rn] = addr;
            break;
        case OP_PUSH:
            for (int i = 15; i >= 0; --i) {  /* lowest register at lowest address */
                if (instruction.regList & (1u << i)) {
                    r[13] -= 4;
                    write_mem(r[13], r[i], 4);
                }
            }
            break;
        case OP_POP:
            for (int i = 0; i < 8; ++i) {
                if (instruction.regList & (1u << i)) {
                    r[i] = read_mem(r[13], 4);
                    r[13] += 4;
                }
            }

            if (instruction.regList & (1u << 15)) {
                uint32_t val = read_mem(r[13], 4);
                r[13] += 4;
                if (!(val & 1))
                    fault("INVSTATE");      /* Thumb-only: bit 0 must be set */
                next = val & ~1u;
            }
            break;

        // Control
        case OP_B:
            if (instruction.instructionFormat == FMT_BRANCH_COND && !cond_passed(instruction.condition))
                break;
            next = pc + 4 + instruction.offset;
            break; 
        case OP_BL:
            r[14] = (pc + 4) | 1;
            next  = pc + 4 + instruction.offset;
            break;
        case OP_BX:
        case OP_BLX:
        {
            uint32_t target = r[instruction.rm];
            if (!(target & 1))
                fault("INVSTATE");            /* Thumb-only: bit 0 must be set */
            if (instruction.operation == OP_BLX)
                r[14] = (pc + 2) | 1;         /* BLX reg is a 2-byte instruction */
            next = target & ~1u;              /* strip the state bit */
            break;
        }
        
        // System
        case OP_SVC:
            svc(instruction.imm);
            break;
        case OP_NOP:
            break;
    }
    if (instruction.sets_flags) {
        N = (res >> 31);
        Z = (res == 0);
    }

    r[15] = next;
    instret++;
    /* TODO: write a trace line here when --trace is given (section 6) */
}

int main(int argc, char **argv)
{
    /* TODO: parse the options in section 6 */
    if (argc != 2) { fprintf(stderr, "usage: %s PROGRAM\n", argv[0]); return 2; }
    load_dump(argv[1]);
    reset();
    for (;;) {
        if (instret >= MAX_INSTR) {
            fprintf(stderr, "LIMIT at pc=0x%08x\n", r[15]);
            exit(254);
        }
        step();
    }
}
