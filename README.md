# Chat Assistant · Dify 智能客服与对话数据分析平台

面向电商客服场景的智能客服与用户洞察系统，覆盖「微信触达 → Dify 工作流 → RAG 检索 → MCP 工具写库 → 对话数据分析 → 可视化大屏」全链路，单人独立完成。

## 项目亮点

- **在线客服**：Flask + wechatpy 接入微信公众号，用户发消息自动回复；后端调用 Dify 6 节点 RAG 工作流（检索 → 生成 → 工具写库）
- **工具调用（MCP）**：基于 FastMCP 将 MySQL 封装为大模型可调用工具，模型直接读写 chat_records 表，替代人工抄录对话
- **对话数据分析**：Pandas 清洗 8 万+ 条对话，jieba 分词 + LDA 聚出 3 大主题，SnowNLP 情感分析，输出词云与多维看板
- **可视化大屏**：PyEcharts/原生 ECharts 实现 KPI + 词云 + 趋势 + 情感分布看板（见 `app/dashboard_preview.png`）
- **工程化**：异步两阶段架构解决微信 5 秒超时导致的重复调用与重复入库；脏数据单条兜错；Docker Compose 部署

## 架构

```
用户微信消息 → 微信服务器 → Flask(wechat_ai.py)
                              ├─ 验签 / 去重 / 异步应答
                              └─ Dify 工作流 (RAG: bge-m3 + Reranker)
                                     └─ MCP 工具 (mysql_server.py / FastMCP)
                                            └─ MySQL (chat_records)

离线分析：MySQL → read_data.py / notebooks
          ├─ task12: LDA 主题聚类
          ├─ task13: SnowNLP 情感分析
          └─ task14: dashboard.py → ECharts 大屏 (dashboard.html)
```

## 快速开始

```bash
# 1. 配置环境变量（参考 .env.example）
# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动微信客服服务
python app/wechat_ai.py

# 4. 启动 MCP 数据库工具服务
python app/mysql_server.py

# 5. 离线分析后生成大屏
python app/dashboard.py   # 输出 dashboard.html
```

## 目录结构

```
app/
├── wechat_ai.py            # 微信公众号接入 + Dify 工作流调用（异步架构）
├── mysql_server.py         # FastMCP 工具：把数据库封装成大模型可调用工具
├── dashboard.py            # 大屏生成
├── dashboard.html          # ECharts 可视化大屏成品
├── dashboard_preview.png   # 大屏预览截图
├── read_data.py            # 数据读取
├── task12_lda_topic.py.ipynb      # LDA 主题聚类（困惑度选 K）
├── task13_sentiment_analysis.py.ipynb  # SnowNLP 情感分析
├── task14_dashboard.py.ipynb      # 大屏开发过程
├── vendor/                 # ECharts 离线依赖
└── data/                   # 聚合分析结果（原始对话数据不入库）
```

## 安全说明

- 所有密钥（微信 AppSecret、Dify API Key、数据库密码）均通过环境变量注入，仓库不含任何真实凭据
- 原始对话数据（含用户内容）不入库，仅保留聚合统计结果

## 环境

Python 3.11+ / MySQL 8.x / Dify（Docker Compose 部署）/ 微信公众号（测试号即可复现）
