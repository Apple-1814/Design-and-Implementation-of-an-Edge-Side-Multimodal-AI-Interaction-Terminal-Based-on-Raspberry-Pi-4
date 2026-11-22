# 蓝桥杯知识库与 AI 助教说明

> 对应里程碑 M8。知识库源为外部教程资料，**索引与原始资料均不提交到 Git**。

## 1. 目标

把 `D:\BaiduNetdiskDownload\蓝桥杯嵌入式教程完整版（去加密）` 中的可读内容提取为可检索片段，让树莓派上的 AI 助教能够：

- 回答 CT117E-M4 / STM32G431RBT6 的板卡、引脚、外设、代码问题；
- 给出本机验证过的配置与官方/历年源码；
- 回答省赛/国赛考点与备赛路线；
- 展示资料来源，避免“凭空回答”。

## 2. 数据来源与处理

| 类型 | 处理方式 | 是否入索引 |
|---|---|---|
| 章节 PPT（37 份，旧版 `.ppt`） | 解析 OLE `PowerPoint Document` 的 TextChars/TextBytes 原子 | 是 |
| PDF（3 份） | PyMuPDF 按页提取；文本过少的页面跳过 | 是 |
| DOCX（3 份真题汇编） | python-docx 提取段落/表格；图片型仅保留目录 | 是（目录） |
| XLSX（3 份考点统计） | openpyxl 读取全部工作表 | 是 |
| 源码 RAR/ZIP/7z（51 个） | 7-Zip 仅解出 `.c/.h/.ioc`，过滤 HAL/CMSIS/构建产物 | 是 |
| 本机固件 | `firmware/Src|Inc` 的 BSP 源码 | 是 |
| 板卡事实卡 | `docs/board_facts.md` | 是 |
| MP4 视频（29 个） | 未转写 | 否 |
| 图片型真题/OneNote | 未 OCR；只保留标题/目录 | 部分 |

当前索引：**1610 个片段 / 464 个来源 / 约 2.62MB 文本**。

## 3. 构建

```bash
# PC；依赖：7-Zip、PyMuPDF、python-docx、openpyxl、olefile
python scripts/build_knowledge.py
```

产物：

- `knowledge/chunks.jsonl`：每行一个片段，字段 `id/title/source/kind/category/text/meta`；
- `knowledge/manifest.json`：构建时间、片段数、字符数、分类统计、sha256。

可选参数：

```bash
python scripts/build_knowledge.py --no-archives   # 只构建文档
python scripts/build_knowledge.py --ocr-docx      # 需要 RapidOCR，当前未启用
python scripts/build_knowledge.py --keep-work     # 保留解压目录，调试用
```

## 4. 树莓派部署

```bash
ssh apple@<Pi-IP> 'mkdir -p ~/ai-terminal/knowledge'
scp knowledge/chunks.jsonl knowledge/manifest.json apple@<Pi-IP>:~/ai-terminal/knowledge/
scp pi/app/knowledge.py apple@<Pi-IP>:~/ai-terminal/pi/app/
ssh apple@<Pi-IP> 'kill -9 $(pgrep -f "uvicorn app.main" | head -1)'
```

服务启动时加载索引（1610 片段在 Pi 上约 1 秒内完成）。

## 5. 检索与问答策略

```text
用户问题
  → 硬件命令规则路由（PING/LED/LCD/ADC/PWM）
  → 身份/问候（“你是谁/你能做什么/你好/谢谢”）→ 固定介绍
  → BM25 检索
       ├─ 板卡事实卡 / 本机固件 / 官方 BSP / 课件摘录 → 直答（约 0.04s）
       ├─ 开放技术问题 → Qwen2.5-0.5B RAG（压缩上下文，20–60s）
       └─ 普通/未知问题 → Qwen2.5-0.5B 无 RAG 回答（天气说明无实时数据；日期用系统时间）
```

- 分词：中文 bigram + ASCII 标识符（`PA9`、`USART1`、`HAL_ADC_Start`）+ 领域同义词；
- 加权：板卡事实卡 1.7×、本机固件 1.4×、官方测试工程 1.3×；旧平台（F103/STC15）0.72×；
- 直答边界：只有板卡小节与问题模块明确匹配，或代码包含目标 API 时才直答；否则走 RAG/通用回答；
- 身份/问候固定回答；日期/时间用树莓派系统时间；天气说明无实时数据，不编造；
- 来源：SSE 先发 `sources`，前端显示“知识库直答/RAG 生成”和可展开的资料卡片。
- 上下文：最近 4 条消息（每条 ≤600 字/总 ≤1500 字）、RAG 700 字/3 来源、输出 ≤160 tokens；llama-server `-c 2048`。

## 6. 接口

| 接口 | 说明 |
|---|---|
| `GET /api/knowledge/status` | 片段数、来源数、分类、manifest、加载错误 |
| `GET /api/knowledge/search?q=LED&top_k=4` | 返回 label/kind/score/snippet |
| `POST /api/knowledge/reload` | 重新加载索引（更新索引后无需重启） |
| `POST /api/chat` | 硬件路由 + 知识直答/RAG；SSE 含 `sources/mode` |

## 7. 验证样例

| 问题 | 结果 |
|---|---|
| LED 怎么点亮？ | 板卡事实卡 3.1 + 本机 `bsp_led.c`，0.04s |
| USART1 串口怎么配置？ | 板卡事实卡 3.5 + 本机 `bsp_usart.c`，0.04s |
| I2C 读写 AT24C02 怎么写？ | 板卡事实卡 3.6 + 官方 `bsp_iic.c`，0.04s |
| PWM 怎么输出 1kHz、50%？ | 板卡事实卡 3.4 + 本机 `bsp_pwm.c`，0.04s |
| 省赛真题考哪些模块？ | 板卡事实卡 10 + 考点统计，0.04s |
| NVIC 中断优先级怎么配置？ | 第 08 章 PPT 摘录，0.05s |
| 定时器输入捕获怎么测频率？ | `bsp_tim.c` 代码 + 第 11 章 PPT，0.05s |
| 树莓派是什么？ | 板卡事实卡第 12 节，0.04s |

## 8. 限制与后续

- 3 份真题 DOCX（87/73/55 张图）和 422 页 OneNote PDF 主要是截图，未 OCR；题面需查原文件。
- 旧平台教程（STC15/F103）只作原理参考，引脚以 `docs/board_facts.md` 为准。
- 0.5B 开放问题仍较慢；后续可换 1.5B/3B、加 OCR、或端云协同。
- 如需更新知识库：重新运行构建脚本 → 上传 → `POST /api/knowledge/reload`。
