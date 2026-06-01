# 面板拖拽缩放方案

## 现状

`MainLayout.tsx` 使用静态 `flex-1 w-1/2` 分割聊天和预览面板，分隔线纯装饰（`w-px bg-border`），不可拖拽。

## 方案：react-resizable-panels

库已安装（`package.json` 中 `react-resizable-panels: ^2.0.0`），提供三个组件：

| 组件 | 作用 |
|------|------|
| `PanelGroup` | 容器，`direction="horizontal"` |
| `Panel` | 可缩放面板，`defaultSize`/`minSize`/`maxSize` |
| `PanelResizeHandle` | 拖拽手柄 |

### 实现

```tsx
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'

<PanelGroup direction="horizontal">
  <Panel defaultSize={50} minSize={25}>
    <ChatPanel />
  </Panel>

  <PanelResizeHandle className="w-1 bg-border hover:w-1.5 hover:bg-primary/30 transition-all cursor-col-resize" />

  {previewVisible && (
    <Panel defaultSize={50} minSize={25}>
      <DocumentPreview />
    </Panel>
  )}
</PanelGroup>
```

### 关键细节

1. **预览隐藏时** — `PanelGroup` 只有一个 `Panel`（聊天），自动占满。预览恢复显示时，恢复到上次的大小比例
2. **大小持久化** — `PanelGroup` 的 `onLayout(sizes)` 回调保存到 `localStorage`，下次加载时通过 `PanelGroup` 的 `storage` API 恢复
3. **无额外依赖** — 库已安装，零新增依赖
4. **替换静态分隔线** — `PanelResizeHandle` 替换目前的 `w-px bg-border`，拖拽区域加宽到 8px 方便鼠标捕获

### 对比当前实现

| 方面 | 当前 | 新方案 |
|------|------|--------|
| 分隔线 | `w-px bg-border` | `PanelResizeHandle` 可拖拽 |
| 面板比例 | 固定 50/50 | 可拖拽，可保存 |
| 预览隐藏 | `previewVisible` 条件渲染 | `PanelGroup` 自动适应 |
| 依赖 | 无 | `react-resizable-panels`（已安装） |
