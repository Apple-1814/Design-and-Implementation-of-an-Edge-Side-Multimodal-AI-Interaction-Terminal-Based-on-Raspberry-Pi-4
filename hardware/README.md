# hardware —— 硬件方案、BOM 与接线

本课设不做 PCB 打样，使用现成树莓派 4B + 蓝桥杯 CT117E-M4（STM32G431RBT6）。

## 目录（待补）

```text
hardware/
  bom.csv            BOM：型号、数量、供电/接口
  wiring.md          接线表：Pi/STM32/外设引脚
  schematic/         系统框图、电源树、接线图
  simulation/        Proteus/立创EDA 仿真截图与说明
```

## 报告对应

| 报告章节 | 材料 |
|---|---|
| 主要电子元件及个数 | `bom.csv` |
| 电路图以及仿真结果 | `schematic/`、`simulation/` |
| 作品演示 | 接线照片、工作状态照片 |

## 关键约束

- STM32 GPIO 3.3V，禁止 5V 直连。
- UART：Pi TX→PA10、Pi RX←PA9、GND 共地。
- 风扇/继电器独立供电并共地。
- 仿真只覆盖 MCU 子系统/关键电路；Pi/LLM 不可仿真需在报告说明。

## 状态

M1 使用板载 LED/LCD 验证，尚未整理 BOM/接线图；M7 前补齐。
