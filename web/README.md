# Zensers 前端

基于 Next.js 14 + TypeScript + Tailwind CSS 的市场研究系统前端。

## 快速启动

### 方式一：一键启动（推荐）

在项目根目录运行：

```bash
# Windows
start.bat

# Linux/Mac
./start.sh
```

这将同时启动前端和后端服务。

### 方式二：分别启动

```bash
# 后端（在项目根目录）
uvicorn src.api.main:app --reload --port 8000

# 前端（在 web 目录）
cd web
npm run dev
```

### 方式三：从前端启动后端

```bash
cd web
npm run dev:full  # 同时启动前后端
```

## 访问地址

- **前端**: http://localhost:3000
- **后端 API**: http://localhost:8000
- **API 文档**: http://localhost:8000/api/v1/docs

## 技术栈

- **框架**: Next.js 14 (App Router)
- **语言**: TypeScript 5
- **样式**: Tailwind CSS + shadcn/ui
- **状态管理**: Zustand
- **HTTP 客户端**: Axios
- **布局**: react-resizable-panels
- **实时通信**: SSE (EventSource)

## 开发

```bash
cd web

# 安装依赖
npm install

# 仅启动前端
npm run dev

# 启动前端 + 后端
npm run dev:full

# 构建生产版本
npm run build

# 启动生产服务器
npm run start
```

## 环境变量

创建 `web/.env.local` 文件：

```env
# 后端 API 地址
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## 核心功能

### 1. 研究对话流程

- **Step 0**: 用户输入研究需求（支持文件上传、模型选择）
- **Step 1**: 选择输出类型
- **Step 2**: 选择模板
- **Step 3**: 选择章节
- **Step 4**: 设置参数
- **Step 5**: 确认研究计划
- **Step 6**: 执行研究（SSE 实时进度）

### 2. 文件上传

支持上传 PDF、Word、Excel、TXT 等文件作为研究参考资料。

### 3. LLM 配置

在设置页面配置：
- 提供商（OpenAI、Anthropic、Azure、本地模型）
- API Key
- 模型选择
- 参数调整（Temperature、Max Tokens 等）

### 4. 主题设置

- 浅色/深色模式
- 主题色选择
- 字体大小和字体选择

### 5. 历史会话

侧边栏快速切换历史对话，或进入历史页面查看详情。

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/v1/research/start` | POST | 启动研究（支持 LLM 配置） |
| `/api/v1/research/interact` | POST | 步骤交互 |
| `/api/v1/research/preview/{task_id}` | GET | 获取预览 |
| `/api/v1/research/completed` | GET | 已完成任务列表 |
| `/api/v1/stream/{task_id}` | GET | SSE 进度流 |
| `/api/v1/upload` | POST | 文件上传 |
| `/api/v1/llm/models` | GET | 获取可用模型列表 |