#pragma once

#include <stddef.h>
#include <stdint.h>
#include "decoder.h"

void disassemble(struct decodedInstruction instruction,
                 uint32_t pc,
                 char *buffer,
                 size_t bufferSize);