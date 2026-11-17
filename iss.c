/* iss.c -- CSCE 2303 Cortex-M0 simulator skeleton.
   Build from repository root: gcc -std=c11 -O2 -Wall -Wextra -o iss iss.c decoder.c disassembler.c      Run: ./iss prog.dump */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <ctype.h> // for hexadecimal conversion
#include <errno.h> // for detecting numeric conversion errors, for example overflowing command-line limit
#include <inttypes.h> // for PRIx32, PRId32, etc.
#include "decoder.h"
#include "disassembler.h"

#define ROM_BASE  0x00000000u
#define ROM_SIZE  (1u << 20)              /* 1 MB   */
#define RAM_BASE  0x20000000u
#define RAM_SIZE  (256u << 10)            /* 256 KB */
#define MAX_INSTR 100000000ull

uint8_t  rom[ROM_SIZE], ram[RAM_SIZE];
uint32_t r[16];                    /* r[13] = sp, r[14] = lr, r[15] = pc */
int      N, Z, C, V;               /* the APSR flags */
uint64_t instret;
static uint64_t max_instr = MAX_INSTR; // default to 100m
static FILE *trace_file; // Open trace output stream, default to NULL (not requested trace)
static int exit_requested, exit_status;
static int input_pending[2], input_count;
static uint32_t text_start;
static uint64_t text_end; // 64 bits to avoid overflow
static int has_text;

struct memory_write { uint32_t addr, value; int size; };

static struct memory_write writes[16];
static size_t write_count;
static int recording_writes;

static void load_error(const char *message)
{
    fprintf(stderr, "load error: %s\n", message);
    exit(253);
} // the input program could not be loaded; status 253
// the loader uses this function before execution 

/* Separate fetch diagnostics from data-access diagnostics. */
static uint32_t fetch_halfword(uint32_t addr);

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
    if (!p || !mem_ptr(addr + (uint32_t)size - 1)) fault("BUS"); // the old check validated only the starting address, now it verifies the first and last byte of the requested access
    uint32_t v = 0;
    for (int i = size - 1; i >= 0; i--)                  /* little-endian */
        v = (v << 8) | p[i];
    return v;
}

void write_mem(uint32_t addr, uint32_t v, int size)
{
    if (addr % size) fault("UNALIGNED");
    if (addr - RAM_BASE >= RAM_SIZE ||
        (uint32_t)size > RAM_SIZE - (addr - RAM_BASE)) fault("BUS"); // The subtraction avoids expressing the test as an unchecked addr + size
        // old check validated only the starting address, now it verifies that the requested size fits    /* only RAM is writable */
    if (recording_writes) {
        /* PUSH/STM can write at most sixteen registers per instruction. */
        if (write_count >= sizeof writes / sizeof writes[0]) abort();
        uint32_t mask = size == 4 ? UINT32_MAX : (1u << (size * 8)) - 1;
        writes[write_count++] = (struct memory_write){addr, v & mask, size};
    }
    for (int i = 0; i < size; i++)
        ram[addr - RAM_BASE + i] = (uint8_t)(v >> (8 * i));
}

/* readelf reserves 35 characters for up to sixteen bytes. Never parse ASCII. */
// old loader was short and permissive, this replacement validates the input more carefully while retaining the supplied readelf layout
void load_dump(const char *path)
{
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); exit(253); }
    memset(rom, 0, sizeof rom);
    memset(ram, 0, sizeof ram); // clearing memory (not necessary but to be safe)
    has_text = 0;
    text_end = 0; // reseting section metadata
    int in_text = 0;
    size_t count = 0;
    char line[1024]; // reading lines into a larger buffer
    while (fgets(line, sizeof line, f)) {
        if (!strchr(line, '\n') && !feof(f)) load_error("line too long");
        char *s = line;
        while (*s == ' ' || *s == '\t') s++;
        if (strncmp(s, "Hex dump of section ", 20) == 0) {
            in_text = strncmp(s, "Hex dump of section '.text':", 27) == 0; // updating the current section
            continue;
        }
        if (strncmp(s, "0x", 2) != 0) continue;
        char *end;
        errno = 0;
        unsigned long long address = strtoull(s, &end, 16);
        if (errno || end == s || address > UINT32_MAX || *end != ' ')
            load_error("invalid address"); // prevent an oversized address from being silently truncated into a valid-looking 32-bit address
        s = end + 1;
        size_t len = strcspn(s, "\r\n");
        if (len > 35) len = 35;
        int high = -1;
        size_t bytes = 0;
        for (size_t i = 0; i < len; i++) {
            unsigned char c = (unsigned char)s[i];
            if (c == ' ' || c == '\t') {
                if (high >= 0) load_error("incomplete byte");
                continue;
            }
            if (!isxdigit(c)) load_error("invalid hex data");
            int digit = c <= '9' ? c - '0' : tolower(c) - 'a' + 10;
            if (high < 0) { high = digit; continue; }
            if (address > UINT32_MAX) load_error("address overflow");
            uint8_t *p = mem_ptr((uint32_t)address); 
            if (!p) load_error("address outside ROM/RAM");
            *p = (uint8_t)((high << 4) | digit); // each pair of hexadecimal digits becomes one byte
            if (in_text) {
                if (!has_text || address < text_start) text_start = (uint32_t)address;
                if (address + 1 > text_end) text_end = address + 1;
                has_text = 1;
            }
            address++;
            high = -1;
            count++;
            bytes++;
        }
        if (high >= 0 || !bytes) load_error("incomplete data line");
    }
    if (ferror(f)) load_error("cannot read dump");
    fclose(f);
    if (!count) load_error("no data lines found");
}

static uint32_t fetch_halfword(uint32_t addr)
{
    uint32_t saved_pc = r[15];
    r[15] = addr;
    uint32_t hw = read_mem(addr, 2);
    r[15] = saved_pc;
    return hw;
}
// temporarily sets r[15] to the fetch address. 
// if read_mem() faults, that is the address reported. 
// if the fetch succeeds, the original PC is restored.

// The driver rejects incomplete trailing instructions, then calls the existing team functions
static int disassemble_text(void)
{
    if (!has_text) load_error("no .text section found"); // checks that .text exists, then walks its extent
    for (uint64_t address = text_start; address < text_end;) {
        if ((address & 1) || address + 2 > text_end)
            load_error("incomplete .text halfword");
        uint32_t pc = (uint32_t)address;
        uint16_t hw = (uint16_t)read_mem(pc, 2), hw2 = 0;
        int wide = (hw >> 11) >= 0x1d; // at each address, it fetches the first halfword and determines whether the encoding indicates a wide instruction
        if (wide) {
            if (address + 4 > text_end) load_error("incomplete wide instruction");
            hw2 = (uint16_t)read_mem(pc + 2, 2);
        }
        struct decodedInstruction instruction = decode(hw, hw2, pc); 
        char assembly[256];
        disassemble(instruction, pc, assembly, sizeof assembly);
        if (wide) printf("%08" PRIx32 ": %04x%04x %s\n", pc, hw, hw2, assembly);
        else printf("%08" PRIx32 ": %04x %s\n", pc, hw, assembly);
        address += wide ? 4 : 2;
    }
    return 0;
}

void reset(void)
{
    memset(r, 0, sizeof r);
    N = Z = C = V = 0;
    instret = 0;
    exit_requested = exit_status = 0;
    input_count = 0;
    r[13] = read_mem(0, 4) & ~3u;                  /* initial sp   */
    // 3u has its bottom two bits set 
    // its complement has those bits clear, 
    // ANDing with it clears SP bits 0 and 1.
    uint32_t pc = read_mem(4, 4);            /* reset vector */
    r[15] = pc;                            /* diagnostic uses the reset vector */
    if (!(pc & 1)) fault("INVSTATE");
    r[15] = pc & ~1u;
    r[14] = 0xFFFFFFFFu;
}
// reset() explicitly resets registers, flags, the retirement counter, exit state, and pending-input state, 
// including when called after state has already changed, as several values depends on them

void set_nz(uint32_t x) { N = x >> 31; Z = (x == 0); }

/* Two bytes of lookahead let GETINT leave a sign with no digits unread. */
static int input_byte(void)
{
    return input_count ? input_pending[--input_count] : getchar();
}

static void unread_byte(int c)
{
    if (c != EOF) input_pending[input_count++] = c;
}

// GETCHAR and GETINT share these helpers so input read ahead by GETINT remains visible to the next service

static uint32_t input_integer(void)
{
    int c;
    do { c = input_byte(); } while (c == ' ' || (c >= 9 && c <= 13));
    int sign = 0;
    if (c == '+' || c == '-') { sign = c; c = input_byte(); }
    if (c < '0' || c > '9') {
        unread_byte(c);
        if (sign) unread_byte(sign);
        return 0;
    }
    uint32_t value = 0;
    do {
        value = value * 10u + (unsigned)(c - '0');
        c = input_byte();
    } while (c >= '0' && c <= '9');
    unread_byte(c);
    return sign == '-' ? 0u - value : value;
}

void svc(int n)
{
    switch (n) {
    case 0x00:
        // the service requests termination and returns, 
        // step() completes retirement and tracing, then main() observes the request
        exit_requested = 1;
        exit_status = r[0] & 0xff;
        break;
    case 0x10: putchar(r[0] & 0xff); break; // retains its original low-byte behavior
    case 0x11:
        for (uint32_t a = r[0];; a++) {
            uint32_t byte = read_mem(a, 1);
            if (!byte) break;
            putchar((int)byte);
        }
        break;
    case 0x12: printf("%" PRId32, (int32_t)r[0]); break;
    case 0x13: printf("0x%08" PRIX32, r[0]); break; // PUTHEX: prints a lowercase 0x prefix followed by eight uppercase hex digits
    case 0x14: { // GETCHAR
        int c = input_byte();
        r[0] = c == EOF ? UINT32_MAX : (uint32_t)c;
        break;
    } 
    case 0x15: r[0] = input_integer(); break; // GETINT
    /* CP3 services are added here without changing retirement in step(). */
    default: fault("UNDEFINED"); 
    }
}

// for sorting addresses
static int compare_writes(const void *a, const void *b)
{
    const struct memory_write *x = a, *y = b;
    return (x->addr > y->addr) - (x->addr < y->addr);
}

// for writing an instruction trace
static void trace_instruction(uint32_t pc, uint32_t hw, uint32_t hw2,
                              int wide, const uint32_t before[15])
{
    if (!trace_file) return;
    static const char *names[] = {
        "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
        "r8", "r9", "r10", "r11", "r12", "sp", "lr"
    };
    fprintf(trace_file, "%08" PRIx32 " %04" PRIx32, pc, hw);
    if (wide) fprintf(trace_file, "%04" PRIx32, hw2);
    for (int i = 0; i < 15; i++)
        if (r[i] != before[i])
            fprintf(trace_file, " %s=%08" PRIx32, names[i], r[i]);
    qsort(writes, write_count, sizeof writes[0], compare_writes);
    for (size_t i = 0; i < write_count; i++)
        fprintf(trace_file, " [%08" PRIx32 "]=%0*" PRIx32,
                writes[i].addr, writes[i].size * 2, writes[i].value);
    fprintf(trace_file, " NZCV=%d%d%d%d\n", N, Z, C, V);
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
    uint32_t before[15];
    memcpy(before, r, sizeof before);
    write_count = 0;
    recording_writes = 1;

    uint32_t hw = fetch_halfword(pc);
    uint32_t hw2 = 0;
    int wide = (hw >> 11) >= 0x1d;
    if (wide) hw2 = fetch_halfword(pc + 2);
    uint32_t next = pc + (wide ? 4u : 2u);

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
            if (instruction.instructionFormat == FMT_MOV_REG ||
                instruction.instructionFormat == FMT_MOVS_REG) {
                res = r[instruction.rm];
            } else {
                res = instruction.imm;
            }
            r[instruction.rd] = res;
            break;
        case OP_MVN:
            res = ~r[instruction.rm];
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
                n = r[instruction.rm];
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
            r[instruction.rd] = res;
            if (instruction.sets_flags) {
                C = carry;
            }
            break;
        case OP_LSR:
            n = r[instruction.rn];
            m = r[instruction.rm] & 0xFF;
            carry = C;
            if (instruction.instructionFormat == FMT_LSR_IMM) {
                n = r[instruction.rm];
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
                n = r[instruction.rm];
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
            recording_writes = 0; /* Service writes are not instruction writes. */
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
    recording_writes = 0;
    trace_instruction(pc, hw, hw2, wide, before);
}

static int usage(const char *program)
{
    fprintf(stderr, "usage: %s [--disasm] [--max-instr N] [--trace FILE] PROGRAM\n", program);
    return 2;
} // CLI errors return status 2

int main(int argc, char **argv)
{
    const char *program = NULL, *trace_path = NULL;
    int disasm = 0;
    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--disasm")) disasm = 1;
        else if (!strcmp(argv[i], "--trace")) {
            if (++i == argc) return usage(argv[0]);
            trace_path = argv[i];
        } else if (!strcmp(argv[i], "--max-instr")) {
            if (++i == argc || !argv[i][0]) return usage(argv[0]);
            for (const char *p = argv[i]; *p; p++)
                if (*p < '0' || *p > '9') return usage(argv[0]);
            errno = 0;
            char *end; // zero is accepted; it prevents any instruction from executing
            max_instr = strtoull(argv[i], &end, 10);
            if (errno || *end) return usage(argv[0]);
        } else if (argv[i][0] == '-' || program) return usage(argv[0]); 
        else program = argv[i];
    }
    if (!program) return usage(argv[0]);
    // the parser rejects missing option values, unknown options, multiple program paths, and a missing program path

    load_dump(program);
    if (disasm) return disassemble_text();
    if (trace_path) {
        trace_file = fopen(trace_path, "w");
        if (!trace_file) { perror(trace_path); return 2; }
    }
    reset();
    while (!exit_requested) {
        if (instret >= max_instr) {
            fprintf(stderr, "LIMIT at pc=0x%08" PRIx32 "\n", r[15]);
            return 254;
        }
        step();
    }
    if (trace_file && fclose(trace_file)) { perror(trace_path); return 2; }
    return exit_status;
}
