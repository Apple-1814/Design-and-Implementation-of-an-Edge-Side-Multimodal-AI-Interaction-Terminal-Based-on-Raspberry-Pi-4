/* Pre-written code walkthroughs for the CT117E-M4 control panel.
 *
 * Each guide is intentionally deterministic: the page should explain the
 * exact clock / pin / peripheral / main sequence without asking the local
 * model.  The code is assembled from the verified firmware in firmware/.
 */
(function () {
  const HEADER = `#include "main.h"

static void Error_Handler(void);
`;

  const SYSTEM_CLOCK = `
/* ===== 1. 时钟：HSE 24MHz -> PLL -> 80MHz ===== */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);

  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV3;   /* 24MHz / 3  = 8MHz  */
  RCC_OscInitStruct.PLL.PLLN = 20;              /* 8MHz  * 20 = 160MHz */
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;   /* 160MHz / 2 = 80MHz */
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK) { Error_Handler(); }

  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK | RCC_CLOCKTYPE_SYSCLK |
                                RCC_CLOCKTYPE_PCLK1 | RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;
  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK) {
    Error_Handler();
  }
}
`;

  const ERROR_HANDLER = `
void Error_Handler(void)
{
  __disable_irq();
  while (1) { }
}
`;

  const hex2 = (value) => "0x" + (Number(value) & 0xff).toString(16).toUpperCase().padStart(2, "0");
  const bitString = (value) => (Number(value) & 0xff).toString(2).padStart(8, "0");
  const commentSafe = (value) => String(value).replace(/\*\//g, "* /").replace(/\r?\n/g, " ");

  function ledAction(ctx = {}) {
    if (ctx.action === "all") {
      const mask = Number(ctx.mask || 0) & 0xff;
      const label = mask === 0xff ? "全亮" : mask === 0 ? "全灭" : `位图 ${hex2(mask)}`;
      return `  LED_Disp(${hex2(mask)});   /* 本次：${label} */`;
    }
    if (ctx.action === "led") {
      const id = Math.min(8, Math.max(1, Number(ctx.id) || 1));
      const bit = 1 << (id - 1);
      const before = Number(ctx.beforeMask || 0) & 0xff;
      const on = Boolean(ctx.on);
      const after = on ? (before | bit) : (before & ~bit);
      const expr = on ? `|= (1u << ${id - 1});` : `&= ~(1u << ${id - 1});`;
      return `  {
    uint8_t mask = ${hex2(before)};   /* 前：${bitString(before)} */
    mask ${expr}   /* LD${id} ${on ? "亮" : "灭"} */
    LED_Disp(${hex2(after)});   /* 后：${bitString(after)} */
  }`;
    }
    return "  LED_Disp(0x01);   /* 示例：LD1 亮 */";
  }

  function lcdAction(ctx = {}) {
    if (ctx.action === "lcd_clear") {
      return "  LCD_Clear(White);   /* 本次：清屏，不显示新字符串 */";
    }
    const text = commentSafe(ctx.text || "Hello");
    return `  LCD_Clear(White);
  LCD_DisplayStringLine(Line0, (uint8_t *)${JSON.stringify(String(ctx.text || "Hello"))});   /* 文本：${text} */`;
  }

  function adcAction(ctx = {}) {
    if (ctx.action === "adc") {
      const ch = Number(ctx.ch) === 2 ? 2 : 1;
      const raw = ctx.raw == null ? "--" : String(ctx.raw);
      const voltage = ctx.voltage == null ? "--" : Number(ctx.voltage).toFixed(3);
      return ch === 2
        ? `  adc2 = getADC2();   /* ADC2/PB15：${raw} -> ${voltage}V */`
        : `  adc1 = getADC1();   /* ADC1/PB12：${raw} -> ${voltage}V */`;
    }
    return "  adc1 = getADC1();   /* 示例：ADC1 / PB12 */\n  adc2 = getADC2();   /* 示例：ADC2 / PB15 */";
  }

  function pwmAction(ctx = {}) {
    if (ctx.action === "pwm") {
      const d1 = Math.max(0, Math.min(100, Number(ctx.duty1 ?? 0)));
      const d2 = Math.max(0, Math.min(100, Number(ctx.duty2 ?? 0)));
      return `  PWM_SetDuty(${d1});    /* PWM1 / PA2 = ${d1}% */
  PWM_SetDuty2(${d2});   /* PWM2 / PA3 = ${d2}% */`;
    }
    return "  PWM_SetDuty(50);    /* 示例：PWM1 / PA2 = 50% */\n  PWM_SetDuty2(30);   /* 示例：PWM2 / PA3 = 30% */";
  }

  const assemble = (moduleCode, token, action) =>
    HEADER + SYSTEM_CLOCK + moduleCode.replace(token, action) + ERROR_HANDLER;

  const LED_CODE = `
/* ===== 2. GPIO：PC8-PC15 数据，PD2 锁存 ===== */
static void LED_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOD_CLK_ENABLE();

  /* PC8-PC15：推挽输出，默认高电平（全灭） */
  GPIO_InitStruct.Pin = GPIO_PIN_8 | GPIO_PIN_9 | GPIO_PIN_10 | GPIO_PIN_11 |
                        GPIO_PIN_12 | GPIO_PIN_13 | GPIO_PIN_14 | GPIO_PIN_15;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
  HAL_GPIO_WritePin(GPIOC, 0xFF00, GPIO_PIN_SET);

  /* PD2：74HC573 的 LE，推挽输出，默认低 */
  GPIO_InitStruct.Pin = GPIO_PIN_2;
  HAL_GPIO_Init(GPIOD, &GPIO_InitStruct);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_2, GPIO_PIN_RESET);
}

/* 高电平透明、下降沿锁存 */
static void LED_Latch(void)
{
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_2, GPIO_PIN_SET);
  HAL_GPIO_WritePin(GPIOD, GPIO_PIN_2, GPIO_PIN_RESET);
}

/* ucled 的 bit0->PC8(LD1)，bit7->PC15(LD8)；低电平点亮 */
void LED_Disp(uint8_t ucled)
{
  HAL_GPIO_WritePin(GPIOC, 0xFF00, GPIO_PIN_SET);
  LED_Latch();

  HAL_GPIO_WritePin(GPIOC, (uint16_t)ucled << 8, GPIO_PIN_RESET);
  LED_Latch();
}

/* ===== 3. main：初始化顺序与主循环 ===== */
int main(void)
{
  HAL_Init();
  SystemClock_Config();
  LED_Init();

  /* ===== 本次控制操作 ===== */
@@LED_ACTION@@
  while (1)
  {
    /* USART1 收到 LED 命令后调用 LED_Disp(new_mask) */
  }
}
`;

  const LCD_CODE = `
/* ===== 2. GPIO：PB5/PB8/PB9 控制线，PA8，PC0-PC15 数据 ===== */
void LCD_BusOut(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  GPIO_InitStruct.Pin = GPIO_PIN_All;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_VERY_HIGH;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOC, &GPIO_InitStruct);
}

void LCD_CtrlLinesConfig(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOC_CLK_ENABLE();
  __HAL_RCC_GPIOA_CLK_ENABLE();
  __HAL_RCC_GPIOB_CLK_ENABLE();

  /* PB5 / PB8 / PB9 控制线 */
  GPIO_InitStruct.Pin = GPIO_PIN_5 | GPIO_PIN_8 | GPIO_PIN_9;
  GPIO_InitStruct.Mode = GPIO_MODE_OUTPUT_PP;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_LOW;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);

  /* PA8 控制线 */
  GPIO_InitStruct.Pin = GPIO_PIN_8;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);

  LCD_BusOut();

  /* 空闲电平 */
  GPIOA->BSRR |= 0x0100;
  GPIOB->BSRR |= 0x0220;
}

/* ===== 3. main：LCD_Init 内部会调用 LCD_CtrlLinesConfig ===== */
int main(void)
{
  HAL_Init();
  SystemClock_Config();

  LCD_Init();                       /* 官方 bsp_lcd.c：控制线 + 控制器寄存器 */
  /* ===== 本次控制操作 ===== */
@@LCD_ACTION@@

  while (1)
  {
    /* USART1 收到 LCD 命令后调用 LCD_DisplayStringLine() */
  }
}
`;

  const ADC_CODE = `
/* ===== 2. 时钟与 GPIO：PB12=ADC1_IN11，PB15=ADC2_IN15 ===== */
static void ADC_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};
  RCC_PeriphCLKInitTypeDef PeriphClkInit = {0};

  __HAL_RCC_GPIOB_CLK_ENABLE();
  __HAL_RCC_ADC12_CLK_ENABLE();

  PeriphClkInit.PeriphClockSelection = RCC_PERIPHCLK_ADC12;
  PeriphClkInit.Adc12ClockSelection = RCC_ADC12CLKSOURCE_SYSCLK;
  if (HAL_RCCEx_PeriphCLKConfig(&PeriphClkInit) != HAL_OK) { Error_Handler(); }

  GPIO_InitStruct.Pin = GPIO_PIN_12 | GPIO_PIN_15;
  GPIO_InitStruct.Mode = GPIO_MODE_ANALOG;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  HAL_GPIO_Init(GPIOB, &GPIO_InitStruct);
}

/* ===== 3. ADC1 / ADC2：12 位、单次、软件触发 ===== */
ADC_HandleTypeDef hadc1;
ADC_HandleTypeDef hadc2;

static void ADC1_Init(void)
{
  ADC_ChannelConfTypeDef sConfig = {0};

  hadc1.Instance = ADC1;
  hadc1.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV2;
  hadc1.Init.Resolution = ADC_RESOLUTION_12B;
  hadc1.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc1.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc1.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc1.Init.ContinuousConvMode = DISABLE;
  hadc1.Init.NbrOfConversion = 1;
  hadc1.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc1.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc1.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&hadc1) != HAL_OK) { Error_Handler(); }

  sConfig.Channel = ADC_CHANNEL_11;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_640CYCLES_5;
  sConfig.SingleDiff = ADC_SINGLE_ENDED;
  sConfig.OffsetNumber = ADC_OFFSET_NONE;
  sConfig.Offset = 0;
  if (HAL_ADC_ConfigChannel(&hadc1, &sConfig) != HAL_OK) { Error_Handler(); }
}

static void ADC2_Init(void)
{
  ADC_ChannelConfTypeDef sConfig = {0};

  hadc2.Instance = ADC2;
  hadc2.Init.ClockPrescaler = ADC_CLOCK_ASYNC_DIV2;
  hadc2.Init.Resolution = ADC_RESOLUTION_12B;
  hadc2.Init.DataAlign = ADC_DATAALIGN_RIGHT;
  hadc2.Init.ScanConvMode = ADC_SCAN_DISABLE;
  hadc2.Init.EOCSelection = ADC_EOC_SINGLE_CONV;
  hadc2.Init.ContinuousConvMode = DISABLE;
  hadc2.Init.NbrOfConversion = 1;
  hadc2.Init.ExternalTrigConv = ADC_SOFTWARE_START;
  hadc2.Init.Overrun = ADC_OVR_DATA_PRESERVED;
  hadc2.Init.OversamplingMode = DISABLE;
  if (HAL_ADC_Init(&hadc2) != HAL_OK) { Error_Handler(); }

  sConfig.Channel = ADC_CHANNEL_15;
  sConfig.Rank = ADC_REGULAR_RANK_1;
  sConfig.SamplingTime = ADC_SAMPLETIME_640CYCLES_5;
  sConfig.SingleDiff = ADC_SINGLE_ENDED;
  sConfig.OffsetNumber = ADC_OFFSET_NONE;
  sConfig.Offset = 0;
  if (HAL_ADC_ConfigChannel(&hadc2, &sConfig) != HAL_OK) { Error_Handler(); }
}

static uint16_t getADC1(void)
{
  uint16_t adc = 0;
  HAL_ADC_Start(&hadc1);
  if (HAL_ADC_PollForConversion(&hadc1, 10u) == HAL_OK) {
    adc = (uint16_t)HAL_ADC_GetValue(&hadc1);
  }
  HAL_ADC_Stop(&hadc1);
  return adc;
}

static uint16_t getADC2(void)
{
  uint16_t adc = 0;
  HAL_ADC_Start(&hadc2);
  if (HAL_ADC_PollForConversion(&hadc2, 10u) == HAL_OK) {
    adc = (uint16_t)HAL_ADC_GetValue(&hadc2);
  }
  HAL_ADC_Stop(&hadc2);
  return adc;
}

/* ===== 4. main ===== */
int main(void)
{
  uint16_t adc1;
  uint16_t adc2;

  HAL_Init();
  SystemClock_Config();
  ADC_GPIO_Init();
  ADC1_Init();
  ADC2_Init();

  /* ===== 本次采样 ===== */
@@ADC_ACTION@@

  while (1)
  {
    /* USART1 收到 ADC? / ADC2? 后重新采样并回传 */
  }
}
`;

  const PWM_CODE = `
/* ===== 2. GPIO：PA2=TIM15_CH1，PA3=TIM15_CH2 ===== */
static void PWM_GPIO_Init(void)
{
  GPIO_InitTypeDef GPIO_InitStruct = {0};

  __HAL_RCC_GPIOA_CLK_ENABLE();

  GPIO_InitStruct.Pin = GPIO_PIN_2 | GPIO_PIN_3;
  GPIO_InitStruct.Mode = GPIO_MODE_AF_PP;
  GPIO_InitStruct.Pull = GPIO_NOPULL;
  GPIO_InitStruct.Speed = GPIO_SPEED_FREQ_HIGH;
  GPIO_InitStruct.Alternate = GPIO_AF9_TIM15;
  HAL_GPIO_Init(GPIOA, &GPIO_InitStruct);
}

/* ===== 3. TIM15：PSC=79, ARR=999 -> 1kHz ===== */
TIM_HandleTypeDef htim15;

static void PWM_Output_TIM15_Init(void)
{
  TIM_ClockConfigTypeDef sClockSourceConfig = {0};
  TIM_MasterConfigTypeDef sMasterConfig = {0};
  TIM_OC_InitTypeDef sConfigOC = {0};

  __HAL_RCC_TIM15_CLK_ENABLE();

  htim15.Instance = TIM15;
  htim15.Init.Prescaler = 79;              /* 80MHz / 80 = 1MHz */
  htim15.Init.CounterMode = TIM_COUNTERMODE_UP;
  htim15.Init.Period = 999;                /* 1MHz / 1000 = 1kHz */
  htim15.Init.ClockDivision = TIM_CLOCKDIVISION_DIV1;
  htim15.Init.RepetitionCounter = 0;
  htim15.Init.AutoReloadPreload = TIM_AUTORELOAD_PRELOAD_ENABLE;
  if (HAL_TIM_Base_Init(&htim15) != HAL_OK) { Error_Handler(); }

  sClockSourceConfig.ClockSource = TIM_CLOCKSOURCE_INTERNAL;
  if (HAL_TIM_ConfigClockSource(&htim15, &sClockSourceConfig) != HAL_OK) {
    Error_Handler();
  }
  if (HAL_TIM_PWM_Init(&htim15) != HAL_OK) { Error_Handler(); }

  sMasterConfig.MasterOutputTrigger = TIM_TRGO_RESET;
  sMasterConfig.MasterSlaveMode = TIM_MASTERSLAVEMODE_DISABLE;
  if (HAL_TIMEx_MasterConfigSynchronization(&htim15, &sMasterConfig) != HAL_OK) {
    Error_Handler();
  }

  sConfigOC.OCMode = TIM_OCMODE_PWM1;
  sConfigOC.Pulse = 0;
  sConfigOC.OCPolarity = TIM_OCPOLARITY_HIGH;
  sConfigOC.OCNPolarity = TIM_OCNPOLARITY_HIGH;
  sConfigOC.OCFastMode = TIM_OCFAST_DISABLE;
  sConfigOC.OCIdleState = TIM_OCIDLESTATE_RESET;
  sConfigOC.OCNIdleState = TIM_OCNIDLESTATE_RESET;
  if (HAL_TIM_PWM_ConfigChannel(&htim15, &sConfigOC, TIM_CHANNEL_1) != HAL_OK) {
    Error_Handler();
  }
  if (HAL_TIM_PWM_ConfigChannel(&htim15, &sConfigOC, TIM_CHANNEL_2) != HAL_OK) {
    Error_Handler();
  }

  PWM_GPIO_Init();

  if (HAL_TIM_PWM_Start(&htim15, TIM_CHANNEL_1) != HAL_OK) { Error_Handler(); }
  if (HAL_TIM_PWM_Start(&htim15, TIM_CHANNEL_2) != HAL_OK) { Error_Handler(); }
}

/* duty: 0-100 -> CCR = duty * 10 (ARR=999) */
void PWM_SetDuty(uint8_t duty)
{
  if (duty > 100u) { duty = 100u; }
  __HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_1, (uint32_t)duty * 10u);
}

void PWM_SetDuty2(uint8_t duty)
{
  if (duty > 100u) { duty = 100u; }
  __HAL_TIM_SET_COMPARE(&htim15, TIM_CHANNEL_2, (uint32_t)duty * 10u);
}

/* ===== 4. main ===== */
int main(void)
{
  HAL_Init();
  SystemClock_Config();
  PWM_Output_TIM15_Init();

  /* ===== 本次占空比 ===== */
@@PWM_ACTION@@

  while (1)
  {
    /* USART1 收到 PWM 命令后调用 PWM_SetDuty()/PWM_SetDuty2() */
  }
}
`;

  window.CODE_GUIDES = {
    led: {
      kicker: "GPIO 输出 + 74HC573 锁存",
      title: "LED 控制：从时钟到 main",
      summary: "PC8–PC15 输出 8 位位图，PD2 产生锁存脉冲；低电平点亮。",
      steps: [
        ["① 开时钟", "使能 GPIOC（PC8–PC15）和 GPIOD（PD2）时钟；时钟没开时写 GPIO 寄存器无效。"],
        ["② 配引脚", "PC8–PC15 配为推挽输出，默认输出高电平（全灭）；PD2 配为推挽输出，默认低电平。"],
        ["③ 写位图", "ucled 的 bit0 对应 PC8（LD1），bit7 对应 PC15（LD8）；需要点亮的位写 0。"],
        ["④ 锁存", "PD2 先拉高再拉低，74HC573 的 LE 高电平透明、下降沿锁存；不翻转 PD2，LED 不会更新。"],
        ["⑤ main 顺序", "HAL_Init → SystemClock_Config（80MHz）→ LED_Init → LED_Disp；命令模式下由 USART1 收到命令后调用 LED_Disp。"],
      ],
      files: ["firmware/Src/bsp/led/bsp_led.c", "firmware/Src/main.c"],
      build: (ctx = {}) => assemble(LED_CODE, "@@LED_ACTION@@", ledAction(ctx)),
      action: (ctx = {}) => ledAction(ctx),
    },
    lcd: {
      kicker: "GPIO 并口 + 官方 LCD 驱动",
      title: "LCD 显示：从时钟到 main",
      summary: "PC0–PC15 并口数据，PB5/PB8/PB9 与 PA8 控制线；先 LCD_Init，再清屏和显示。",
      steps: [
        ["① 开时钟", "使能 GPIOC（数据总线）、GPIOA（PA8）、GPIOB（控制线）时钟。"],
        ["② 配控制线", "PB5/PB8/PB9 与 PA8 配为推挽输出；空闲时保持高电平。"],
        ["③ 配数据线", "PC0–PC15 配为推挽输出，速度设为 Very High；读 LCD ID 时才临时切输入。"],
        ["④ 初始化控制器", "调用官方 LCD_Init()，内部执行 LCD_CtrlLinesConfig() 并写 REG_932X/8230 寄存器。"],
        ["⑤ 清屏与显示", "先 LCD_Clear(White) 清屏，再 LCD_DisplayStringLine(Line0, 文本)；不要在定时器中断里刷屏。"],
        ["⑥ main 顺序", "HAL_Init → SystemClock_Config（80MHz）→ LCD_Init → LCD_Clear → 显示。"],
      ],
      files: ["firmware/Src/bsp/lcd/bsp_lcd.c", "firmware/Inc/bsp/lcd/bsp_lcd.h"],
      build: (ctx = {}) => assemble(LCD_CODE, "@@LCD_ACTION@@", lcdAction(ctx)),
      action: (ctx = {}) => lcdAction(ctx),
    },
    adc: {
      kicker: "ADC1/ADC2 + 电位器",
      title: "ADC 采样：从时钟到 main",
      summary: "PB12=ADC1_IN11（R38），PB15=ADC2_IN15（R37）；12 位、单次、软件触发。",
      steps: [
        ["① 开时钟", "使能 GPIOB、ADC12 时钟，并把 ADC12 时钟源选为 SYSCLK。"],
        ["② 配引脚", "PB12、PB15 配为模拟模式（GPIO_MODE_ANALOG），不能配成普通输入/输出。"],
        ["③ 配 ADC", "ADC1/ADC2 均为 12 位、右对齐、单次转换、软件触发，采样时间 640.5 个周期。"],
        ["④ 读采样", "HAL_ADC_Start → HAL_ADC_PollForConversion(10ms) → HAL_ADC_GetValue → HAL_ADC_Stop。"],
        ["⑤ 换算", "码值 0–4095 对应 0–3.3V；电压 = raw * 3.3 / 4095。需要稳定显示时做 8/16 次平均或中值滤波。"],
        ["⑥ main 顺序", "HAL_Init → SystemClock_Config → ADC_GPIO_Init → ADC1_Init/ADC2_Init → 采样。"],
      ],
      files: ["firmware/Src/bsp/adc/bsp_adc.c", "firmware/Src/main.c"],
      build: (ctx = {}) => assemble(ADC_CODE, "@@ADC_ACTION@@", adcAction(ctx)),
      action: (ctx = {}) => adcAction(ctx),
    },
    pwm: {
      kicker: "TIM15 双通道 PWM",
      title: "PWM 输出：从时钟到 main",
      summary: "PA2=TIM15_CH1，PA3=TIM15_CH2；PSC=79、ARR=999，固定 1kHz。",
      steps: [
        ["① 开时钟", "使能 GPIOA 和 TIM15 时钟；PA2/PA3 必须复用为 AF9。"],
        ["② 配引脚", "PA2/PA3 配为 GPIO_MODE_AF_PP，Alternate=GPIO_AF9_TIM15，不能当普通 GPIO 用。"],
        ["③ 配时基", "TIM15 时钟 80MHz，PSC=79 → 1MHz 计数；ARR=999 → 1kHz。"],
        ["④ 配通道", "两个通道都用 PWM1 模式、高电平有效，初始 Pulse=0，然后 HAL_TIM_PWM_Start() 启动。"],
        ["⑤ 调占空比", "CCR = duty × 10（duty 0–100 对应 0–1000）；改频率要同时改 PSC 和 ARR。"],
        ["⑥ main 顺序", "HAL_Init → SystemClock_Config → PWM_Output_TIM15_Init → PWM_SetDuty/SetDuty2。"],
      ],
      files: ["firmware/Src/bsp/pwm/bsp_pwm.c", "firmware/Src/main.c"],
      build: (ctx = {}) => assemble(PWM_CODE, "@@PWM_ACTION@@", pwmAction(ctx)),
      action: (ctx = {}) => pwmAction(ctx),
    },
  };
})();
