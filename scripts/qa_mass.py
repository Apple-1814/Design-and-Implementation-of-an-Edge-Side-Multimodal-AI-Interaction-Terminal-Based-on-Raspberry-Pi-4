#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mass QA test: ~200 board/code questions plus deep and cross-module cases.

Run on the Pi:
    python3 scripts/qa_mass.py --group fast
    python3 scripts/qa_mass.py --group deep
    python3 scripts/qa_mass.py --group all

Fast cases use fast_only so a question that should be answered by the board
card fails immediately instead of waiting for the 0.5B model.
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from qa_stress import chat, check

# Each group has several paraphrases of one fact; must is all-of.
GROUPS = [
    {"id": "led_data", "cat": "LED", "must": ["PC8", "PC15"], "not": ["PA9"], "q": [
        "LED 的数据口是哪几个引脚？", "8 个 LED 接在哪些 GPIO？", "LED1 到 LED8 对应哪些引脚？",
        "CT117E-M4 的 LED 用 PC 口还是 PB 口？", "LED 的 PC8–PC15 是怎么接的？", "板子上 8 个灯的数据引脚是什么？",
    ]},
    {"id": "led_latch", "cat": "LED", "must": ["PD2"], "q": [
        "LED 锁存引脚是哪个？", "PD2 在 LED 电路里做什么？", "为什么写完 PC8–PC15 还要操作 PD2？",
        "LED 的 74HC573 锁存端接哪里？", "LED 不更新和 PD2 有什么关系？", "LED 锁存脉冲是哪个引脚？",
    ]},
    {"id": "led_polarity", "cat": "LED", "must": ["低电平"], "q": [
        "LED 是高电平点亮还是低电平点亮？", "PC8 输出 0 时 LED 亮还是灭？", "LED_Disp 为什么先写高电平？",
        "LED 的默认熄灭电平是什么？", "LED 低电平有效吗？", "LED 极性怎么判断？",
    ]},
    {"id": "key1", "cat": "按键", "must": ["PB0"], "q": [
        "KEY1 接哪个引脚？", "PB0 是哪个按键？", "按键 1 的 GPIO 是什么？",
        "KEY1 按下读到什么电平？", "KEY1 的 Key_Scan 返回值是多少？", "PB0 按键怎么配置？",
    ]},
    {"id": "key4", "cat": "按键", "must": ["PA0"], "q": [
        "KEY4 接哪个引脚？", "PA0 是哪个按键？", "KEY4 的扫描返回值？",
        "按键 4 的 GPIO？", "PA0 按键按下是什么电平？", "KEY4 怎么初始化？",
    ]},
    {"id": "usart_tx", "cat": "USART", "must": ["PA9"], "q": [
        "USART1 的 TX 是哪个引脚？", "串口发送脚接哪里？", "PA9 是什么功能？",
        "USART1_TX 对应哪个 GPIO？", "板载 DAPLink 的串口 TX 接 MCU 哪个脚？", "串口 TX 要配成什么模式？",
    ]},
    {"id": "usart_rx", "cat": "USART", "must": ["PA10"], "q": [
        "USART1 的 RX 是哪个引脚？", "PA10 是什么功能？", "串口接收脚接哪里？",
        "USART1_RX 对应哪个 GPIO？", "DAPLink 的 RXD 接 MCU 哪个脚？", "PA10 怎么配置？",
    ]},
    {"id": "usart_mode", "cat": "USART", "must": ["AF_PP"], "q": [
        "USART1 的 GPIO 应该配成推挽还是开漏？", "为什么串口收不到数据？", "AF_PP 和 AF_OD 对串口有什么影响？",
        "USART1 初始化 GPIO 模式是什么？", "串口 TX 用 GPIO_MODE_AF_PP 吗？", "官方例程串口开漏有什么问题？",
    ]},
    {"id": "i2c_scl", "cat": "I2C", "must": ["PB6"], "q": [
        "I2C1 的 SCL 是哪个引脚？", "AT24C02 的时钟线接哪里？", "PB6 是什么功能？",
        "I2C 时钟引脚怎么配置？", "EEPROM 的 SCL 对应哪个 GPIO？", "PB6 要开漏还是推挽？",
    ]},
    {"id": "i2c_sda", "cat": "I2C", "must": ["PB7"], "q": [
        "I2C1 的 SDA 是哪个引脚？", "AT24C02 的数据线接哪里？", "PB7 是什么功能？",
        "I2C 数据引脚怎么配置？", "EEPROM 的 SDA 对应哪个 GPIO？", "PB7 要上拉吗？",
    ]},
    {"id": "eeprom_addr", "cat": "I2C", "must": ["0x50"], "q": [
        "AT24C02 的 I2C 地址是多少？", "24C02 的写地址是什么？", "EEPROM 的 7 位地址是多少？",
        "AT24C02 读地址是多少？", "I2C 上 24C02 地址 0x50 对吗？", "AT24C02 地址怎么算？",
    ]},
    {"id": "adc1", "cat": "ADC", "must": ["PB12"], "q": [
        "ADC1 接哪个引脚？", "PB12 是什么 ADC 通道？", "电位器 R38 接到哪里？",
        "ADC1_IN11 对应哪个 GPIO？", "ADC1 的模拟输入脚是什么？", "PB12 怎么配置成 ADC？",
    ]},
    {"id": "adc2", "cat": "ADC", "must": ["PB15"], "q": [
        "ADC2 接哪个引脚？", "PB15 是什么 ADC 通道？", "电位器 R37 接到哪里？",
        "ADC2_IN15 对应哪个 GPIO？", "第二路 ADC 的引脚是什么？", "PB15 怎么配置成 ADC？",
    ]},
    {"id": "adc_res", "cat": "ADC", "must": ["12"], "q": [
        "ADC 是几位分辨率？", "ADC 返回值范围是多少？", "ADC 满量程对应多少伏？",
        "PB12 采样值 4095 对应几伏？", "ADC 的参考电压是多少？", "ADC 转换结果怎么换算电压？",
    ]},
    {"id": "pwm1", "cat": "PWM", "must": ["PA2"], "q": [
        "PWM1 是哪个引脚？", "PA2 对应哪个定时器通道？", "TIM15_CH1 接哪个 GPIO？",
        "第一路 PWM 输出在哪里？", "PWM1 怎么配置？", "PA2 输出什么波形？",
    ]},
    {"id": "pwm2", "cat": "PWM", "must": ["PA3"], "q": [
        "PWM2 是哪个引脚？", "PA3 对应哪个定时器通道？", "TIM15_CH2 接哪个 GPIO？",
        "第二路 PWM 输出在哪里？", "PWM2 怎么配置？", "PA3 和 PA2 是同一个定时器吗？",
    ]},
    {"id": "pwm_timer", "cat": "PWM", "must": ["TIM15"], "q": [
        "PWM 用的哪个定时器？", "PWM 频率是多少？", "TIM15 的 Prescaler 和 Period 是多少？",
        "PWM 怎么输出 1kHz？", "PWM 占空比 50% 对应比较值多少？", "PWM 频率怎么计算？",
    ]},
    {"id": "lcd", "cat": "LCD", "must": ["LCD"], "q": [
        "LCD 是多少寸？", "LCD 怎么清屏？", "LCD_DisplayStringLine 怎么用？",
        "LCD 显示中文要注意什么？", "LCD 初始化顺序是什么？", "LCD 花屏怎么排查？",
    ]},
    {"id": "mcu", "cat": "板卡", "must": ["STM32G431RBT6"], "q": [
        "板子的主控芯片是什么？", "STM32G431RBT6 的封装是什么？", "CT117E-M4 的 MCU 型号？",
        "芯片有多少 Flash 和 RAM？", "板子主频是多少？", "MCU 是 Cortex-M4 吗？",
    ]},
    {"id": "resources", "cat": "板卡", "must": ["LED"], "q": [
        "板子上有几个 LED？", "板子上有几个按键？", "板子有几路 ADC？",
        "板子有几路 PWM？", "板子有 EEPROM 吗？", "板子有 CMSIS-DAP 吗？",
    ]},
    {"id": "debugger", "cat": "板卡", "must": ["CMSIS-DAP"], "q": [
        "板载调试器是什么？", "Keil 用什么调试器？", "CMSIS-DAP 怎么下载？",
        "SWD 需要接哪些线？", "板子能用 ST-Link 吗？", "CMSIS-DAP 是板载的吗？",
    ]},
    {"id": "exam", "cat": "真题", "must": ["LED"], "q": [
        "省赛一般考什么？", "国赛一般考什么？", "蓝桥杯嵌入式客观题考什么？",
        "备赛先学什么？", "省赛常见模块组合？", "真题怎么刷？",
    ]},
    {"id": "code_led", "cat": "代码", "must": ["LED_Disp"], "q": [
        "LED_Disp 函数怎么用？", "LED 初始化的代码在哪？", "LED 低电平点亮的代码怎么写？",
        "LED 锁存代码是什么？", "LED 全亮命令是什么？", "LED 全灭命令是什么？",
    ]},
    {"id": "code_usart", "cat": "代码", "must": ["USART1_Init"], "q": [
        "USART1_Init 怎么写？", "串口中断接收代码怎么写？", "HAL_UART_RxCpltCallback 怎么用？",
        "串口发送字符串用什么函数？", "为什么不要用 sizeof 发送字符串？", "串口环形缓冲怎么写？",
    ]},
    {"id": "code_i2c", "cat": "代码", "must": ["24c02"], "q": [
        "iic_24c02_write 怎么写？", "iic_24c02_read 怎么写？", "I2CStart 和 I2CStop 是什么？",
        "24C02 页写怎么处理？", "软件 I2C 的 SDA 怎么切换输入输出？", "AT24C02 写周期延时多少？",
    ]},
    {"id": "code_adcpwm", "cat": "代码", "must": ["PWM"], "q": [
        "getADC1 怎么读？", "ADC 轮询转换怎么初始化？", "PWM_SetDuty 怎么设置占空比？",
        "PWM_SetDuty2 怎么用？", "TIM15 PWM 启动函数是什么？", "ADC2 初始化代码怎么写？",
    ]},
    {"id": "trouble", "cat": "排错", "must": ["排查"], "q": [
        "LED 不亮怎么排查？", "按键乱跳怎么办？", "串口收不到数据怎么办？",
        "ADC 数值不变怎么办？", "PWM 没有波形怎么办？", "LCD 花屏怎么办？",
    ]},
    {"id": "rtc", "cat": "RTC", "must": ["RTC"], "q": [
        "RTC 怎么配置？", "RTC 时钟源是什么？", "RTC 怎么显示日期？",
        "RTC 怎么设置时间？", "RTC 中断怎么用？", "RTC 日历怎么读？",
    ]},
    {"id": "protocol", "cat": "命令", "must": ["LED"], "q": [
        "LED 单灯命令是什么？", "LCD 显示命令是什么？", "ADC 查询命令是什么？",
        "PWM 设置命令是什么？", "PING 命令返回什么？", "LEDALL 命令怎么用？",
    ]},
    {"id": "board_more", "cat": "板卡", "must": ["AT24C02"], "q": [
        "板载 EEPROM 型号是什么？", "LCD 是多少寸？", "调试器是什么？",
        "开发环境是什么？", "板子供电是多少伏？", "扩展接口有哪些？",
    ]},
    {"id": "code_more", "cat": "代码", "must": ["RTC"], "q": [
        "RTC 初始化代码怎么写？", "LCD_Init 怎么用？", "Key_Scan 怎么用？",
        "ADC2 初始化代码怎么写？", "USART1 波特率是多少？", "PWM 的 Prescaler 和 Period 是多少？",
    ]},
]

PER_Q = {
    "mcu": [["STM32G431RBT6"], ["LQFP64"], ["STM32G431RBT6"], ["128KB"], ["80MHz"], ["Cortex-M4"]],
    "resources": [["8"], ["4"], ["ADC1", "ADC2"], ["PWM1", "PWM2"], ["AT24C02"], ["CMSIS-DAP"]],
    "protocol": [["LED"], ["LCD"], ["ADC"], ["PWM"], ["PONG"], ["LEDALL"]],
    "board_more": [["AT24C02"], ["2.4"], ["CMSIS-DAP"], ["Keil"], ["5V"], ["J1"]],
    "code_more": [["RTC"], ["LCD_Init"], ["Key_Scan"], ["ADC2"], ["9600"], ["Prescaler"]],
    "code_adcpwm": [["getADC1"], ["ADC1_Init"], ["PWM_SetDuty"], ["PWM_SetDuty2"], ["PWM_Output"], ["ADC2_Init"]],
    "trouble": [["PC8"], ["消抖"], ["PA9"], ["PB12"], ["PA2"], ["LCD_Clear"]],
    "code_usart": [["USART1_Init"], ["USART1_Init"], ["USART1_Init"], ["USART1_Init"], ["sizeof"], ["USART1_Init"]],
}

DEEP = [
    {"id": "code_definition", "messages": [{"role": "user", "content": "代码是什么？"}], "must": ["代码"]},
    {"id": "weather", "messages": [{"role": "user", "content": "天气怎么样？"}], "must": ["无法获取"], "not": ["℃", "北京", "2022"]},
    {"id": "embedded", "messages": [{"role": "user", "content": "什么是嵌入式系统？"}], "must": ["嵌入式"]},
    {"id": "nvic", "messages": [{"role": "user", "content": "NVIC 中断优先级怎么配置？"}], "must": ["NVIC"]},
    {"id": "capture", "messages": [{"role": "user", "content": "定时器输入捕获怎么测频率？"}], "must": ["捕获"]},
    {"id": "rtc_config", "messages": [{"role": "user", "content": "RTC 实时时钟怎么配置？"}], "must": ["RTC"]},
    {"id": "lcd_chinese", "messages": [{"role": "user", "content": "LCD 怎么显示中文？"}], "must": ["字库"]},
    {"id": "i2c_page", "messages": [{"role": "user", "content": "AT24C02 页写为什么要拆分？"}], "must": ["页"]},
    {"id": "usart_irq", "messages": [{"role": "user", "content": "串口中断接收怎么写？"}], "must": ["中断"]},
    {"id": "adc_filter", "messages": [{"role": "user", "content": "ADC 采样怎么滤波？"}], "must": ["滤波"]},
    {"id": "pwm_calc", "messages": [{"role": "user", "content": "PWM 频率和占空比怎么计算？"}], "must": ["频率"]},
    {"id": "key_state", "messages": [{"role": "user", "content": "按键状态机怎么写？"}], "must": ["按键"]},
    {"id": "exam_strategy", "messages": [{"role": "user", "content": "省赛怎么准备？"}], "must": ["省赛"]},
    {"id": "keil_fail", "messages": [{"role": "user", "content": "Keil 下载失败怎么排查？"}], "must": ["CMSIS-DAP"]},
    {"id": "crash", "messages": [{"role": "user", "content": "程序跑飞了怎么办？"}], "must": ["中断"]},
    {"id": "cross_led_usart", "messages": [{"role": "user", "content": "LED 和 USART1 分别用哪些引脚？"}], "must": ["PC8", "PA9"]},
    {"id": "cross_adc_pwm", "messages": [{"role": "user", "content": "ADC1 和 PWM1 分别是什么引脚？"}], "must": ["PB12", "PA2"]},
    {"id": "cross_lcd_rtc", "messages": [{"role": "user", "content": "LCD 和 RTC 怎么配置？"}], "must": ["LCD", "RTC"]},
    {"id": "counts", "messages": [{"role": "user", "content": "板子有几路 ADC 和 PWM？"}], "must": ["ADC", "PWM"]},
    {"id": "concept_interrupt", "messages": [{"role": "user", "content": "什么是中断？"}], "must": ["中断", "ISR"]},
    {"id": "concept_pwm", "messages": [{"role": "user", "content": "PWM 是什么？"}], "must": ["占空比"]},
    {"id": "concept_i2c", "messages": [{"role": "user", "content": "I2C 是什么？"}], "must": ["SCL", "SDA"]},
    {"id": "faq_sky", "messages": [{"role": "user", "content": "为什么天是蓝的？"}], "must": ["瑞利散射"]},
    {"id": "faq_code", "messages": [{"role": "user", "content": "代码是什么？"}], "must": ["指令"]},
    {"id": "board_usart1", "messages": [{"role": "user", "content": "什么是 USART1？"}], "must": ["PA9", "PA10"]},
]


def run_fast():
    results = []
    for group in GROUPS:
        for idx, q in enumerate(group["q"], 1):
            case_id = f"{group['id']}_{idx}"
            try:
                r = chat([{"role": "user", "content": q}], timeout=15, max_tokens=32, fast_only=True)
                per = PER_Q.get(group["id"])
                must = per[idx - 1] if per else group.get("must", ())
                failures = check(
                    r,
                    must=must,
                    must_not=group.get("not", ()),
                    mode="knowledge",
                )
                results.append({
                    "id": case_id, "cat": group["cat"], "q": q,
                    "ok": not failures, "failures": failures,
                    "content": r["content"], "mode": r["mode"], "latency": r["latency"],
                })
            except Exception as exc:
                results.append({
                    "id": case_id, "cat": group["cat"], "q": q,
                    "ok": False, "failures": [f"exception: {exc}"],
                    "content": "", "mode": None, "latency": 0,
                })
    return results


def run_deep():
    results = []
    for case in DEEP:
        try:
            r = chat(case["messages"], timeout=120, max_tokens=160)
            failures = check(r, must=case.get("must", ()), must_not=case.get("not", ()))
            results.append({
                "id": case["id"], "cat": "deep", "q": case["messages"][-1]["content"],
                "ok": not failures, "failures": failures,
                "content": r["content"], "mode": r["mode"], "latency": r["latency"],
            })
        except Exception as exc:
            results.append({
                "id": case["id"], "cat": "deep", "q": case["messages"][-1]["content"],
                "ok": False, "failures": [f"exception: {exc}"],
                "content": "", "mode": None, "latency": 0,
            })
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", choices=["fast", "deep", "all"], default="all")
    ap.add_argument("--out", default=str(Path.home() / "ai-terminal" / "logs"))
    args = ap.parse_args()

    results = []
    if args.group in ("fast", "all"):
        results.extend(run_fast())
    if args.group in ("deep", "all"):
        results.extend(run_deep())

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = out_dir / f"qa_mass_{args.group}_{stamp}.json"
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    by_cat = defaultdict(lambda: [0, 0])
    for r in results:
        by_cat[r["cat"]][1] += 1
        if r["ok"]:
            by_cat[r["cat"]][0] += 1
    for r in results:
        if not r["ok"]:
            print(f"FAIL {r['id']:<20} {r['q']}")
            print("     " + " | ".join(r["failures"]))
            print("     " + (r["content"] or "").replace("\n", " ")[:160])
    for cat, (ok, total) in sorted(by_cat.items()):
        print(f"{cat:<8} {ok}/{total}")
    passed = sum(1 for r in results if r["ok"])
    print(f"\nRESULT: {passed}/{len(results)} PASS; log={out}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
