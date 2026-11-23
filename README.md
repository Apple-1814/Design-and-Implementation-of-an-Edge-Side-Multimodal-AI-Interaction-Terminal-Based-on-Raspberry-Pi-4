# 蓝桥杯嵌入式 AI 助教：基于树莓派 4B 与 STM32G431 的端侧多模态 AI 交互终端

《嵌入式系统综合设计》课程设计项目。树莓派本地运行小参数 LLM/VLM，浏览器提供类 DeepSeek 聊天界面，通过 UART 控制 STM32G431 开发板；同时内置 **蓝桥杯 CT117E-M4 专用知识库 RAG**，可回答板卡、外设、代码与真题问题。

## 1. 系统架构

```text
浏览器（PC / 平板）
   │ HTTP + SSE
   ▼
树莓派 4B：FastAPI
   ├─ llama.cpp：Qwen2.5-1.5B、SmolVLM-500M
   ├─ 脚本引擎：自然语言 → 结构化命令
   ├─ 串口服务：/dev/ttyACM0 @ 9600
   └─ 烧录服务：pyOCD + CMSIS-DAP（P1/P2）
   │ USB（CMSIS-DAP VCP）
   ▼
STM32G431（蓝桥杯 CT117E-M4）
   通用固件：LED×8 / LCD / ADC1+ADC2 / PWM1+PWM2
```

## 2. 当前状态

| 里程碑 | 状态 |
|---|---|
| M0 环境与链路 | ✅ Pi 4B 8GB、Ubuntu 20.04、CMSIS-DAP 烧录、9600 UART 双向、原固件备份 |
| M1 固件命令协议 | ✅ PING / LED×8 / LEDALL / LCD / ADC1+ADC2 / PWM1+PWM2；固件 v0.3.0 |
| M2 Pi 后端 | ✅ `/api/device/*` + 持久串口；双 ADC/双 PWM 状态接口 |
| M3 LLM 部署 | ✅ Qwen2.5-1.5B，3.02 tok/s |
| M4 前端 | ✅ 聊天 + 蓝桥杯助教 + 紧凑板卡面板；浅蓝白默认，5 套可切换配色 |
| M5 VLM | ✅ 基础版：SmolVLM-500M，单图 34s |
| M6 整机联调 | ✅ 30 分钟稳定性：933 次检查 / 0 失败；最高 47.2°C |
| M7 报告与交付 | ✅ Word 报告 + 11 页 PPT + 9 张图 + 稳定性数据 |
| M8 蓝桥杯知识库 | ✅ 1610 片段 / 464 来源；板卡/源码/课件直答 + 1.5B RAG 回退 |
| M9 双通道控制 | ✅ 8 LED 下拉控制 + 全亮/全灭；ADC1(PB12)/ADC2(PB15)；PWM1(PA2)/PWM2(PA3) |
| M10 LCD 横幅 | ✅ 仅首次打开串口时发送，重连不覆盖 LCD 内容 |
| M11 主题 | ✅ 浅蓝白默认，5 套可切换配色，localStorage 记忆 |
| M12 上下文/历史 | ✅ 4 条/1500 字上下文；会话历史保存与单条/全部删除 |
| M13 问答回归 | ✅ **454/454**：事实/深度 211 + 回答质量 236 + 多轮 6 + 并发 1 |
| M14 代码讲解 | ✅ 控制操作后自动展示 LED/LCD/ADC/PWM 从时钟、引脚到 main 的完整代码；代码随本次操作动态变化 |
| M15 输入历史 | ✅ 输入框 ↑/↓ 召回当前会话提问，↓ 到最新恢复草稿 |
| M16 云端模型 | ✅ OpenAI/Anthropic 兼容接口、思考强度低/中/高；MiniMax-M3 真实 Key 已验证 |

## 3. 目录

```text
firmware/        STM32G431 Keil 工程（HAL + BSP + 命令解析）
pi/              树莓派后端：FastAPI、llama.cpp、串口服务、BM25 知识检索
web/             蓝桥杯 AI 助教前端（聊天 + 资料来源 + 板卡控制）
docs/            协议、验证记录、板卡事实卡、交付说明
scripts/         烧录、串口测试、知识库构建、部署辅助脚本
knowledge/       知识库索引（本地生成，已 gitignore，不上传）
计划书.md         全流程计划书
HANDOFF.md       当前状态与下一步
```

## 4. 构建与烧录

### 固件

```bash
# 用 Keil MDK 打开
firmware/MDK-ARM/HAL_01_LED_TEST.uvprojx
# 编译后生成
firmware/MDK-ARM/HAL_01_LED_TEST/HAL_01_LED_TEST.hex
```

树莓派侧烧录（CMSIS-DAP + pyOCD）：

```bash
pyocd flash --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack \
  -t STM32G431RBTx -f 100k firmware/release/command_firmware.hex
pyocd reset --pack ~/Keil.STM32G4xx_DFP.1.6.0.pack -t STM32G431RBTx
```

### 串口

```bash
# 板载 CMSIS-DAP VCP 默认 9600；不要用 stty 改 115200（会阻塞）
cat /dev/ttyACM0
```

### 树莓派完整启动

```bash
# 1) Python 依赖（见 pi/README.md）
cd pi
~/.local/bin/virtualenv .venv 2>/dev/null || true
. .venv/bin/activate
pip install -r requirements.txt

# 2) 模型与 llama.cpp（见 docs/交付说明.md / docs/llama_cpp_pi_build.md）
#    模型放到 ~/ai-terminal/models，llama-server 构建到 ~/ai-terminal/llama.cpp

# 3) 一键启动 LLM(8080) + VLM(8081) + FastAPI(8000)
ROOT=$HOME/ai-terminal bash scripts/start_all.sh
```

浏览器访问 `http://<树莓派IP>:8000/`。

### 其他电脑访问

- 树莓派已连接 **OpenWrt Wi-Fi**，当前地址 **`192.168.1.165`**。
- 其他电脑连接同一个 Wi-Fi 后打开：`http://192.168.1.165:8000/`。
- 页面右侧显示“其他电脑访问”地址；LCD 也显示当前 Wi-Fi IP。
- 直连网线地址 `192.168.49.50` 只适合你的电脑维护使用。
- Wi-Fi IP 变化时，以面板/LCD 为准；可在 OpenWrt 给树莓派做 DHCP 静态租约。
- 不同网络（各自热点）默认不可互访；需要端口映射/内网穿透时，先加访问认证，避免暴露硬件控制接口。

### 跨网访问（Cloudflare 临时隧道）

- 详细步骤见 [docs/公网访问.md](docs/公网访问.md)。
- 启动：`bash scripts/start_tunnel.sh`；URL 在 `~/ai-terminal/logs/cloudflared.log`。
- 公网链接启用 Basic 密码，用户名/密码在树莓派 `~/.ai_terminal_access`（不入 Git）。
- 仅公网请求需要密码；同一 Wi-Fi/局域网的 `192.168.1.165:8000` 不受影响。
- 临时隧道无可用性保证；课堂演示前提前启动并自测，演示后可 `bash scripts/stop_tunnel.sh`。

> **开机自启已配置**：`llama.service`、`vlm.service`、`ai-terminal.service` 均为 enabled；给 Pi 上电后约 22 秒 API 上线，LCD 显示当前 Wi-Fi IP 与 `READY`。首次安装：
>
> ```bash
> ROOT=/home/apple/ai-terminal bash scripts/install_services.sh
> ```
>
> 课堂电脑/Pi 固定 IP 与手机共享网络见 [docs/课堂演示网络配置.md](docs/课堂演示网络配置.md)。

### 报告与 PPT

- [课程设计报告.docx](paper/课程设计报告.docx)
- [答辩PPT.pptx](paper/答辩PPT.pptx)
- [交付说明](docs/交付说明.md) · [验证记录](docs/verification.md) · [UART 协议](docs/protocol.md) · [知识库说明](docs/knowledge_base.md)

## 5. 验证方式

每个里程碑按 `计划书.md` 的验收标准实测；记录写入 `HANDOFF.md` 与 `docs/verification.md`。未验证项不得写成“已完成”。

## 6. 蓝桥杯知识库 RAG

知识库由外部教程资料构建，**不提交到仓库**：

```bash
# PC 侧构建（需要 7-Zip；Python 依赖见 scripts/requirements-knowledge.txt）
python -m pip install -r scripts/requirements-knowledge.txt
python scripts/build_knowledge.py
# 输出：knowledge/chunks.jsonl、knowledge/manifest.json

# 上传到树莓派
ssh apple@<Pi-IP> 'mkdir -p ~/ai-terminal/knowledge'
scp knowledge/chunks.jsonl knowledge/manifest.json apple@<Pi-IP>:~/ai-terminal/knowledge/
scp pi/app/knowledge.py apple@<Pi-IP>:~/ai-terminal/pi/app/
```

- 覆盖：章节 PPT、CT117E-M4 产品手册、实训指导书、真题汇编目录、考点统计、官方模块源码、历年真题工程、本机验证固件、`docs/board_facts.md`。
- 检索：中文 bigram + ASCII 标识符 + 同义词，BM25；`/api/knowledge/search?q=...` 可单独测试。
- 问答策略：硬件命令规则路由 → 知识库直答（板卡/源码/课件摘录）→ 引脚/事实/概念/对比/FAQ 确定性直答 → 1.5B RAG/通用回答；天气只说明无实时数据，日期用系统时间。
- 引脚问题直接返回引脚清单，事实问题直接返回数量/命令/型号/地址，不再贴代码或 PPT；只有“怎么写/例程/配置”才给代码。
- 概念词条覆盖中断/边沿/定时器/PWM/ADC/I2C/SPI/RTC/DMA/NVIC/指针/栈等 40 个术语；未收录的术语交给 1.5B 解释，不再拒绝。
- 限制：图片型真题 Word/OneNote 未 OCR；F103/STC15 旧平台内容仅作原理参考，引脚以 `docs/board_facts.md` 为准。
- 页面左下角/顶部显示知识库片段数；每条回答下方可展开资料来源。
- 历史对话保存在浏览器 `localStorage`，刷新/重开保留；会话列表支持单条删除和“清空全部历史”。
- 输入框支持 **↑/↓ 切换当前会话的历史提问**：↑ 逐条向前、↓ 逐条向后，↓ 到最新时恢复未发送的草稿；多行输入中只在首行/末行触发，避免抢占光标移动。
- 问答回归：`scripts/qa_mass.py` 211 题（186 事实 + 25 深度/概念）、`scripts/qa_answers.py` 236 题（200 定义变体 + 6 对比 + 5 FAQ + 5 板卡 + 6 引脚 + 10 事实 + 4 开放）、`scripts/qa_stress.py` 多轮/并发，合计 **454/454**；详见 [测试报告](docs/qa_stress_report.md)。
- 代码讲解：顶栏可在“AI 对话 / 代码讲解”之间切换；右侧控制面板执行 LED、LCD、ADC、PWM 操作后会自动打开对应讲解。`web/guides.js` 提供时钟、引脚、外设初始化、main 顺序和完整 C 代码，并按本次操作动态生成关键片段：LD 编号与前后位图、LCD 实际文本、ADC 通道与采样值、PWM 两路占空比；支持一键复制，不依赖模型生成。
- 云端模型（可选）：顶栏“云”按钮支持 **OpenAI 兼容**（DeepSeek/OpenAI/通义）和 **Anthropic 兼容**（Claude/MiniMax）接口，填写 Base URL、模型名和 API Key 即可启用。启用后除硬件命令外**所有问答都走云端模型**；云端保持“蓝桥杯 AI 助教”身份，并接收板卡事实卡 + 本地知识库检索结果（最多 12 片段/9000 字）。思考强度可选 **低/中/高**，分别控制回答长度与推导深度。API Key 只保存在当前页面内存，刷新或关闭标签页即清除，不写入服务器文件或日志。
- 上下文预算：后端保留最近 4 条消息（每条 ≤600 字、总 ≤1500 字），RAG 资料 ≤700 字/3 来源；板卡直答不占生成 token，1.5B 通用回答 320–512 tokens；llama-server 仍为 `-c 2048`。

## 7. 关键约束

- 板载 VCP 仅支持 9600；115200 会阻塞，需 USB-TTL。
- USART1 TX 必须使用 `GPIO_MODE_AF_PP`，不能用 `AF_OD`。
- 网页端不得上传任意固件；烧录只允许 `firmware/release/manifest.json` 白名单。
- 默认本地模型推理，不依赖云端 API；云端模型为可选增强，Key 仅存浏览器页面内存。
