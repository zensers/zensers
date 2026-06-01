# Knowledge Frontend Integration — Deep Analysis Plan

## Goal
完全理解知识模块（后端的 KnowledgeImporter → Compiler → Storage 管线，前端的 SSE 流、状态管理、命令模式）的每个细节，识别所有集成风险、阻塞边界、和设计盲区，形成可执行的实现方案。

## Phases

### Phase 1: 后端 KnowledgeImporter 深度分析
- [ ] 完成 importer.py 全量阅读 (1216行)
- [ ] 分析 URL 导入的完整路径（import_url → validate_url → fetch → extract → compile）
- [ ] 分析错误处理、重试、超时、取消机制
- [ ] 分析线程安全性（是否使用了 threading.Lock？）
- [ ] 分析 import_url 的 async/await 边界
- [ ] 评估 MAX_URL_SIZE=10MB 对大文档的适用性

### Phase 2: 后端 Compiler + Storage 管线分析
- [ ] 阅读 KnowledgeCompiler 实现（compile_research → save_knowledge）
- [ ] 分析 SQLite 存储模式
- [ ] 分析 entity extraction pipeline（EntityExtractor → RelationExtractor → FactVerifier → Normalizer）
- [ ] 评估编译器对大文档的内存和性能影响

### Phase 3: DreamModeScheduler + 后台任务调度分析
- [ ] 定位并阅读 DreamModeScheduler 完整实现
- [ ] 分析 background_loop 的暂停/恢复机制
- [ ] 分析 should_pause() / is_main_task_running 的实现
- [ ] 评估现有调度器扩展为 ImportTaskManager 的可行性

### Phase 4: SSE 流基础设施分析
- [ ] 完整阅读 ProgressStreamer (676行)
- [ ] 分析 ProgressStreamer 的线程安全设计
- [ ] 分析 SessionStreamer (287行) 的持久化推送
- [ ] 评估前端的 SSE 消费模式（useProgress + useSessionStream）

### Phase 5: 前端状态管理 + 命令模式分析
- [ ] 完整阅读 ChatPanel.handleSend 流程
- [ ] 分析 useResearch hook 完整调用链
- [ ] 分析 Zustand store 的同步模式（useSessionStore 订阅链）
- [ ] 分析 /template 命令模式的完整实现（作为 /knowledge 的参考模板）

### Phase 6: 事件循环安全 + 阻塞风险分析
- [ ] 分析后端所有同步阻塞点（文件 IO、网络 IO、LLM 调用）
- [ ] 分析 run_in_executor 的使用模式和覆盖率
- [ ] 分析前端 SSE 连接中断时的降级策略
- [ ] 评估大 URL 下载对事件循环的影响

### Phase 7: 集成方案设计
- [ ] 综合所有分析形成完整架构设计
- [ ] 定义 API 契约
- [ ] 定义组件接口
- [ ] 定义数据流

### Phase 8: 设计文档输出
- [ ] 更新设计文档为终版
- [ ] 包含所有风险点和缓解措施
