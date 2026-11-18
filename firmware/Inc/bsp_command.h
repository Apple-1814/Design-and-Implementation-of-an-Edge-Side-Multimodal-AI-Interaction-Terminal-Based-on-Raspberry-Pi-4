#ifndef BSP_COMMAND_H
#define BSP_COMMAND_H

#include "main.h"

void CMD_Init(void);
void CMD_FeedByte(uint8_t byte);
void CMD_Proc(void);

#endif /* BSP_COMMAND_H */
