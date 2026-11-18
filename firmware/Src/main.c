#include "main.h"
#include "led\bsp_led.h"
#include "key\bsp_key.h"
#include "lcd\bsp_lcd.h"
#include "usart\bsp_usart.h"
#include "bsp_command.h"
#include "adc/bsp_adc.h"
#include "pwm/bsp_pwm.h"
#include <stdio.h>

union float_bytes {
    float value;
    uint8_t bytes[sizeof(float)];
};



//变量创建区
__IO uint32_t uwTick_Key_Set_Point = 0;//控制Key_Proc的执行
__IO uint32_t uwTick_Lcd_Set_Point = 0;//控制Key_Proc的执行
__IO uint32_t uwTick_Usart_Set_Point = 0;//控制Key_Proc的执行
unsigned char i=0;


//按键扫描专用
unsigned char ucKey_Val,ucKey_Down,ucKey_Up,ucKey_Old;

//LCD显示专用变量
unsigned char Lcd_Disp_String[22];

//串口专用变量
int counter = 0;
uint8_t str[40];
unsigned char rx_buffer;


//子函数声明区
void SystemClock_Config(void);
void Key_Proc(void);
void LCD_Proc(void);
void USART_Proc(void);


//主函数
int main(void)
{
	
	
//内核时钟初始化
  HAL_Init();
  SystemClock_Config();

//外设函数初始化
  LED_Init();
  KEY_Init();
	
  LCD_Init();
  LCD_Clear(White);
  LCD_SetBackColor(White);
  LCD_SetTextColor(Blue);
  LED_Disp(0x01);
  ADC1_Init();
  LED_Disp(0x03);
  PWM_Output_TIM15_Init();
  LED_Disp(0x07);

  USART1_Init();
  HAL_UART_Receive_IT(&huart1, &rx_buffer, 1);
  CMD_Init();
  LED_Disp(0x0F);


  while (1)
  {

	  
	  CMD_Proc();
	  

  }
}

void Key_Proc(void)
{
	
	if((uwTick - uwTick_Key_Set_Point)<100)  return;//减速函数
	uwTick_Key_Set_Point = uwTick;
	
	//分几种情况  ^异或符号
	//情况1：100ms两次扫描，按键得到的结果从0（都没按下）到B4按下，产生下降沿
	//ucKey_Val = 0000 0100
	// ucKey_Down = 0000 0100 &（0000 0000 ^ 0000 0100）=0000 0100(4)
	//ucKey_Up = 1111 1011 &（0000 0000 ^ 0000 0100）= 0000 0000
	//ucKey_Old = 0000 0100(4)
	
	//情况2：B4产生下降沿后，按键一直按着
	//ucKey_Val = 0000 0100
	// ucKey_Down = 0000 0100 &（0000 0100 ^ 0000 0100）=0000 0000(0)
	//ucKey_Up = 1111 1011 &（0000 0100 ^ 0000 0100）= 0000 0000
	//ucKey_Old = 0000 0100(4)
	
	//情况3：B4产生下降沿后，按键一直按着随后弹起
	//ucKey_Val = 0000 0000
	// ucKey_Down = 0000 0000 &（0000 0100 ^ 0000 0000）=0000 0000(0)
	//ucKey_Up = 1111 1111 &（0000 0100 ^ 0000 0000）= 0000 0100（4）
	//ucKey_Old = 0000 0000(0)
	
	//情况4：一直不按
	//ucKey_Val = 0000 0000
	// ucKey_Down = 0000 0000 &（0000 0000 ^ 0000 0000）=0000 0000(0)
	//ucKey_Up = 1111 1111 &（0000 0000 ^ 0000 0000）= 0000 0000（0）
	//ucKey_Old = 0000 0000(0)
	
	ucKey_Val = Key_Scan();
	ucKey_Down = ucKey_Val & (ucKey_Old ^ ucKey_Val);// 0000 0100 &（0000 0000 ^ 0000 0100）=0000 0100(4)
	ucKey_Up = ~ucKey_Val & (ucKey_Old ^ ucKey_Val);
	ucKey_Old = ucKey_Val;
	
	if(ucKey_Down == 4)
	{
		LED_Disp(0x88);
//		HAL_Delay(500);
		
//		
	}
	if(ucKey_Down == 3)
	{
		LED_Disp(0x00);
	}	

}

void LCD_Proc(void)
{
  if((uwTick - uwTick_Lcd_Set_Point)<100)  return;//减速函数
  uwTick_Lcd_Set_Point = uwTick;
  i++;

  sprintf((char *)Lcd_Disp_String,"     i num: %03d     ",(unsigned int)i);
  LCD_DisplayStringLine(Line2, Lcd_Disp_String);


}

void USART_Proc(void)
{
	if((uwTick - uwTick_Usart_Set_Point)<500)  return;//减速函数
	uwTick_Usart_Set_Point = uwTick;
  
	sprintf((char *)str, "%04d:Hello,world.\r\n", counter);
//	HAL_UART_Transmit(&huart1,fb.bytes, sizeof(float), 50);
	HAL_UART_Transmit(&huart1,str, sizeof(str), 50);
//	HAL_Delay(500);
//	LED_Disp(0x11);	
//	HAL_Delay(300);
//	LED_Disp(0x00);
		
	if(++counter == 10000)
		counter = 0;

}

void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
	if (huart->Instance == USART1)
	{
		CMD_FeedByte(rx_buffer);
		HAL_UART_Receive_IT(&huart1, &rx_buffer, 1);
	}
}



/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  HAL_PWREx_ControlVoltageScaling(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = RCC_PLLM_DIV3;
  RCC_OscInitStruct.PLL.PLLN = 20;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = RCC_PLLQ_DIV2;
  RCC_OscInitStruct.PLL.PLLR = RCC_PLLR_DIV2;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV1;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV1;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_2) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  /* User can add his own implementation to report the HAL error return state */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* User can add his own implementation to report the file name and line number,
     ex: printf("Wrong parameters value: file %s on line %d\r\n", file, line) */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
