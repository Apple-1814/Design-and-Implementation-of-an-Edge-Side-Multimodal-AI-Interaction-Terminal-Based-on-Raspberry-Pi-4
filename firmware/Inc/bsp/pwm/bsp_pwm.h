#ifndef BSP_PWM_H
#define BSP_PWM_H

#include "main.h"

extern TIM_HandleTypeDef htim15;

void PWM_Output_TIM15_Init(void);
void PWM_SetDuty(uint8_t duty);
void PWM_SetDuty2(uint8_t duty);

#endif /* BSP_PWM_H */
