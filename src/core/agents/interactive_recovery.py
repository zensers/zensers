"""
交互式恢复模块

提供用户友好的崩溃恢复体验：
1. 用户输入 `.resume` 命令
2. 系统扫描并列出可恢复的 session
3. 用户选择要恢复的 session
4. 系统显示恢复信息并等待用户指令

设计文档: docs/SESSION_PERSISTENCE_DESIGN.md Section 5
"""
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from dataclasses import dataclass
import json


@dataclass
class RecoveryCandidate:
    """恢复候选项"""
    session_id: str
    topic: str
    status: str
    total_agents: int
    running_agents: int
    pending_agents: int
    completed_agents: int
    created_at: Optional[datetime] = None
    progress: float = 0.0
    
    def to_display_string(self, index: int) -> str:
        """生成显示字符串"""
        progress_bar = self._progress_bar(self.progress)
        return (
            f"  [{index}] {self.session_id}\n"
            f"      主题: {self.topic}\n"
            f"      状态: {self.status}\n"
            f"      进度: {progress_bar} {self.progress*100:.0f}%\n"
            f"      Agent: {self.completed_agents}/{self.total_agents} 完成, "
            f"{self.running_agents} 运行中, {self.pending_agents} 待执行"
        )
    
    def _progress_bar(self, progress: float, width: int = 20) -> str:
        """生成进度条"""
        filled = int(progress * width)
        return "█" * filled + "░" * (width - filled)


class InteractiveRecovery:
    """
    交互式恢复管理器
    
    提供用户友好的恢复流程：
    ```
    用户: .resume
    
    系统: 扫描中断的任务...
          
          发现 3 个可恢复的任务:
          
          [1] research_a1b2c3d4
              主题: 新能源汽车市场
              状态: 中断
              进度: ████████░░░░░░░░░░░░ 40%
              Agent: 2/5 完成, 1 运行中, 2 待执行
          
          [2] research_e5f6g7h8
              主题: 医疗AI行业分析
              状态: 中断
              进度: ████████████████░░░░ 80%
              Agent: 4/5 完成, 0 运行中, 1 待执行
          
          [3] research_i9j0k1l2
              主题: 半导体产业链研究
              状态: 中断
              进度: █░░░░░░░░░░░░░░░░░░░ 5%
              Agent: 0/3 完成, 1 运行中, 2 待执行
          
          请选择要恢复的任务 (1-3)，或输入 'q' 退出:
    
    用户: 2
    
    系统: 已选择: research_e5f6g7h8
          
          任务详情:
          - 主题: 医疗AI行业分析
          - 创建时间: 2026-04-10 14:30:00
          - 中断时间: 2026-04-10 15:45:23
          - 总进度: 80%
          
          已完成的 Agent:
            ✓ 数据收集Agent (100%)
            ✓ 市场规模分析Agent (100%)
            ✓ 竞争格局分析Agent (100%)
            ✓ 政策环境分析Agent (100%)
          
          未完成的 Agent:
            ○ 报告生成Agent (待执行)
          
          可用操作:
            [c] 继续执行 - 从中断点恢复
            [v] 查看详情 - 查看已完成的中间结果
            [d] 放弃任务 - 删除此任务
            [b] 返回列表 - 返回任务列表
          
          请选择操作:
    
    用户: c
    
    系统: 正在恢复任务...
          [research_e5f6g7h8] 恢复成功!
          
          开始执行报告生成Agent...
    ```
    """
    
    def __init__(self, storage_path: Path):
        """
        初始化交互式恢复管理器
        
        Args:
            storage_path: 存储路径
        """
        self.storage_path = Path(storage_path)
        self._candidates: List[RecoveryCandidate] = []
    
    def scan_interrupted_tasks(self) -> List[RecoveryCandidate]:
        """
        扫描中断的任务
        
        Returns:
            可恢复的任务列表
        """
        from src.core.agents.agent_session import AgentSessionRegistry, AgentSessionStatus
        
        self._candidates = []
        registries_dir = self.storage_path / "registries"
        
        if not registries_dir.exists():
            return self._candidates
        
        for registry_file in registries_dir.glob("*.json"):
            try:
                registry = AgentSessionRegistry.load(registry_file)
                
                # 检查是否有未完成的 Session
                running = registry.get_running()
                pending = registry.get_pending()
                completed = registry.get_completed()
                
                if running or pending:
                    # 获取任务主题（从第一个 Session 的 context 中提取）
                    topic = "未知主题"
                    if registry.child_sessions:
                        first_session = list(registry.child_sessions.values())[0]
                        if first_session.context:
                            topic = first_session.context.get("topic", "未知主题")
                    
                    # 计算总进度
                    total_progress = sum(s.progress for s in registry.child_sessions.values())
                    avg_progress = total_progress / len(registry.child_sessions) if registry.child_sessions else 0
                    
                    # 读取创建时间
                    created_at = None
                    if registry.child_sessions:
                        first_session = list(registry.child_sessions.values())[0]
                        created_at = first_session.created_at
                    
                    candidate = RecoveryCandidate(
                        session_id=registry.parent_session_id,
                        topic=topic,
                        status="中断",
                        total_agents=registry.count(),
                        running_agents=len(running),
                        pending_agents=len(pending),
                        completed_agents=len(completed),
                        created_at=created_at,
                        progress=avg_progress,
                    )
                    
                    self._candidates.append(candidate)
                    
            except Exception as e:
                print(f"Warning: Failed to load registry {registry_file}: {e}")
                continue
        
        return self._candidates
    
    def display_candidates(self) -> str:
        """
        生成候选任务显示字符串
        
        Returns:
            格式化的显示字符串
        """
        if not self._candidates:
            return "未发现可恢复的任务。"
        
        lines = [
            "",
            "═" * 60,
            f"  发现 {len(self._candidates)} 个可恢复的任务",
            "═" * 60,
            "",
        ]
        
        for i, candidate in enumerate(self._candidates, 1):
            lines.append(candidate.to_display_string(i))
            lines.append("")
        
        lines.append(f"请选择要恢复的任务 (1-{len(self._candidates)})，或输入 'q' 退出:")
        
        return "\n".join(lines)
    
    def get_candidate(self, index: int) -> Optional[RecoveryCandidate]:
        """
        获取指定索引的候选项
        
        Args:
            index: 1-based 索引
            
        Returns:
            RecoveryCandidate 或 None
        """
        if 1 <= index <= len(self._candidates):
            return self._candidates[index - 1]
        return None
    
    def get_task_details(self, session_id: str) -> Dict[str, Any]:
        """
        获取任务详情
        
        Args:
            session_id: Session ID
            
        Returns:
            任务详情字典
        """
        from src.core.agents.agent_session import AgentSessionRegistry
        
        registry_path = self.storage_path / "registries" / f"{session_id}.json"
        if not registry_path.exists():
            return {"error": "Session not found"}
        
        registry = AgentSessionRegistry.load(registry_path)
        
        # 构建详情
        details = {
            "session_id": session_id,
            "total_agents": registry.count(),
            "completed_agents": [],
            "running_agents": [],
            "pending_agents": [],
            "failed_agents": [],
        }
        
        for session in registry.child_sessions.values():
            agent_info = {
                "agent_id": session.agent_id,
                "progress": session.progress,
                "has_result": session.result is not None,
            }
            
            if session.status.value == "completed":
                details["completed_agents"].append(agent_info)
            elif session.status.value == "running":
                details["running_agents"].append(agent_info)
            elif session.status.value == "pending":
                details["pending_agents"].append(agent_info)
            elif session.status.value == "failed":
                details["failed_agents"].append(agent_info)
        
        return details
    
    def display_task_details(self, session_id: str) -> str:
        """
        生成任务详情显示字符串
        
        Args:
            session_id: Session ID
            
        Returns:
            格式化的显示字符串
        """
        details = self.get_task_details(session_id)
        
        if "error" in details:
            return f"错误: {details['error']}"
        
        lines = [
            "",
            "─" * 60,
            f"  任务详情: {session_id}",
            "─" * 60,
            "",
            f"  总 Agent 数: {details['total_agents']}",
            "",
        ]
        
        # 已完成的 Agent
        if details["completed_agents"]:
            lines.append("  ✓ 已完成的 Agent:")
            for agent in details["completed_agents"]:
                lines.append(f"      • {agent['agent_id']} ({agent['progress']*100:.0f}%)")
            lines.append("")
        
        # 运行中的 Agent
        if details["running_agents"]:
            lines.append("  ▶ 运行中的 Agent:")
            for agent in details["running_agents"]:
                lines.append(f"      • {agent['agent_id']} ({agent['progress']*100:.0f}%)")
            lines.append("")
        
        # 待执行的 Agent
        if details["pending_agents"]:
            lines.append("  ○ 待执行的 Agent:")
            for agent in details["pending_agents"]:
                lines.append(f"      • {agent['agent_id']}")
            lines.append("")
        
        # 失败的 Agent
        if details["failed_agents"]:
            lines.append("  ✗ 失败的 Agent:")
            for agent in details["failed_agents"]:
                lines.append(f"      • {agent['agent_id']}")
            lines.append("")
        
        lines.extend([
            "  可用操作:",
            "    [c] 继续执行 - 从中断点恢复",
            "    [v] 查看详情 - 查看已完成的中间结果",
            "    [d] 放弃任务 - 删除此任务",
            "    [b] 返回列表 - 返回任务列表",
            "",
            "  请选择操作:",
        ])
        
        return "\n".join(lines)


# === CLI 命令入口 ===

def cmd_resume(storage_path: Optional[Path] = None) -> None:
    """
    CLI 命令: .resume
    
    交互式恢复中断的任务。
    """
    from src.core.orchestrator.research_orchestrator import ResearchOrchestrator
    
    storage = storage_path or Path("data")
    recovery = InteractiveRecovery(storage)
    
    # 1. 扫描中断的任务
    print("\n扫描中断的任务...\n")
    candidates = recovery.scan_interrupted_tasks()
    
    if not candidates:
        print("未发现可恢复的任务。")
        return
    
    # 2. 显示候选任务
    print(recovery.display_candidates())
    
    # 3. 等待用户选择
    while True:
        try:
            choice = input("> ").strip().lower()
            
            if choice == 'q':
                print("已取消恢复。")
                return
            
            index = int(choice)
            candidate = recovery.get_candidate(index)
            
            if candidate:
                break
            else:
                print(f"无效选择，请输入 1-{len(candidates)} 或 'q':")
                
        except ValueError:
            print("请输入数字或 'q':")
        except KeyboardInterrupt:
            print("\n已取消恢复。")
            return
    
    # 4. 显示任务详情
    print(recovery.display_task_details(candidate.session_id))
    
    # 5. 等待用户操作
    while True:
        try:
            action = input("> ").strip().lower()
            
            if action == 'c':
                # 继续执行
                print(f"\n正在恢复任务 {candidate.session_id}...\n")
                
                orchestrator = ResearchOrchestrator.recover_task(
                    candidate.session_id,
                    storage
                )
                
                # 返回 orchestrator 供后续使用
                print(f"[{candidate.session_id}] 恢复成功!")
                print("使用 orchestrator.resume() 继续执行任务。")
                
                return orchestrator
                
            elif action == 'v':
                # 查看详情
                _display_intermediate_results(storage, candidate.session_id)
                
            elif action == 'd':
                # 放弃任务
                confirm = input("确认删除此任务? (y/n): ").strip().lower()
                if confirm == 'y':
                    _delete_task(storage, candidate.session_id)
                    print(f"任务 {candidate.session_id} 已删除。")
                    return
                    
            elif action == 'b':
                # 返回列表
                print(recovery.display_candidates())
                
            else:
                print("无效操作，请输入 c/v/d/b:")
                
        except KeyboardInterrupt:
            print("\n已取消操作。")
            return


def _display_intermediate_results(storage_path: Path, session_id: str) -> None:
    """显示中间结果"""
    print(f"\n查看任务 {session_id} 的中间结果...\n")
    # TODO: 实现中间结果显示
    print("(功能开发中)")


def _delete_task(storage_path: Path, session_id: str) -> None:
    """删除任务"""
    from src.core.agents.session_persistence import SessionPersistenceManager
    
    persistence = SessionPersistenceManager(storage_path)
    persistence.cleanup_completed_session(session_id)


# === 导出 ===

__all__ = [
    'InteractiveRecovery',
    'RecoveryCandidate',
    'cmd_resume',
]