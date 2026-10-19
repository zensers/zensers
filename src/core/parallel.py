# -*- coding: utf-8 -*-
"""
Parallel Optimization Module
============================

Phase 4 Week 18: Performance Optimization - Parallel Optimization

Features:
- Task parallel scheduling - thread pool/process pool
- Task dependency management - DAG scheduling
- Parallel execution monitoring - progress tracking
- Resource limiting - concurrency control

Core classes:
- Task - Parallel task
- TaskResult - Task result
- ParallelExecutor - Parallel executor
"""

import os
import time
import threading
import multiprocessing
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, Future, as_completed
from typing import Dict, Any, Optional, List, Callable, Tuple, Set
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
import logging
import queue

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status enumeration"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutorType(Enum):
    """Executor type enumeration"""
    THREAD = "thread"
    PROCESS = "process"


@dataclass
class TaskResult:
    """Task result"""
    task_id: str
    status: TaskStatus
    result: Any = None
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    
    @property
    def duration(self) -> float:
        """Get execution duration"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration": self.duration,
        }


@dataclass
class Task:
    """Parallel task"""
    task_id: str
    func: Callable
    args: Tuple = field(default_factory=tuple)
    kwargs: Dict[str, Any] = field(default_factory=dict)
    dependencies: Set[str] = field(default_factory=set)
    status: TaskStatus = TaskStatus.PENDING
    result: Optional[TaskResult] = None
    
    def execute(self) -> TaskResult:
        """Execute task"""
        start_time = time.time()
        self.status = TaskStatus.RUNNING
        
        try:
            result = self.func(*self.args, **self.kwargs)
            self.status = TaskStatus.COMPLETED
            
            return TaskResult(
                task_id=self.task_id,
                status=self.status,
                result=result,
                start_time=start_time,
                end_time=time.time()
            )
        except Exception as e:
            self.status = TaskStatus.FAILED
            
            return TaskResult(
                task_id=self.task_id,
                status=self.status,
                error=str(e),
                start_time=start_time,
                end_time=time.time()
            )


class ParallelExecutor:
    """
    Parallel executor
    
    Supports task parallel scheduling and dependency management.
    
    Usage example:
        executor = ParallelExecutor(max_workers=4)
        
        # Add tasks
        executor.submit("task1", func1, args=(1, 2))
        executor.submit("task2", func2, dependencies={"task1"})
        
        # Execute and get results
        results = executor.execute_all()
    """
    
    def __init__(
        self,
        max_workers: int = 4,
        executor_type: ExecutorType = ExecutorType.THREAD
    ):
        """
        Initialize parallel executor
        
        Args:
            max_workers: Maximum worker threads/processes
            executor_type: Executor type
        """
        self.max_workers = max_workers
        self.executor_type = executor_type
        
        self._tasks: Dict[str, Task] = {}
        self._results: Dict[str, TaskResult] = {}
        self._lock = Lock()
        
        # Create executor
        if executor_type == ExecutorType.THREAD:
            self._executor = ThreadPoolExecutor(max_workers=max_workers)
        else:
            self._executor = ProcessPoolExecutor(max_workers=max_workers)
    
    def submit(
        self,
        task_id: str,
        func: Callable,
        args: Tuple = (),
        kwargs: Optional[Dict[str, Any]] = None,
        dependencies: Optional[Set[str]] = None
    ) -> None:
        """
        Submit task
        
        Args:
            task_id: Task ID
            func: Execution function
            args: Positional arguments
            kwargs: Keyword arguments
            dependencies: Set of dependent task IDs
        """
        with self._lock:
            task = Task(
                task_id=task_id,
                func=func,
                args=args,
                kwargs=kwargs or {},
                dependencies=dependencies or set()
            )
            self._tasks[task_id] = task
    
    def execute_all(self) -> Dict[str, TaskResult]:
        """
        Execute all tasks
        
        Returns:
            Task result dictionary
        """
        with self._lock:
            tasks = dict(self._tasks)
        
        # Topological sort
        execution_order = self._topological_sort(tasks)
        
        # Execute tasks
        futures: Dict[str, Future] = {}
        completed: Set[str] = set()
        
        for task_id in execution_order:
            task = tasks[task_id]
            
            # Wait for dependencies to complete
            for dep_id in task.dependencies:
                if dep_id in self._results:
                    dep_result = self._results[dep_id]
                    if dep_result.status == TaskStatus.FAILED:
                        # Dependency failed, skip this task
                        task.status = TaskStatus.CANCELLED
                        self._results[task_id] = TaskResult(
                            task_id=task_id,
                            status=TaskStatus.CANCELLED,
                            error=f"Dependency task {dep_id} failed"
                        )
                        continue
            
            if task.status == TaskStatus.CANCELLED:
                continue
            
            # Submit to executor
            future = self._executor.submit(task.execute)
            futures[task_id] = future
        
        # Collect results
        for task_id, future in futures.items():
            try:
                result = future.result()
                self._results[task_id] = result
            except Exception as e:
                self._results[task_id] = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=str(e)
                )
        
        return dict(self._results)
    
    def _topological_sort(self, tasks: Dict[str, Task]) -> List[str]:
        """Topological sort"""
        # Build dependency graph
        in_degree: Dict[str, int] = {tid: 0 for tid in tasks}
        graph: Dict[str, Set[str]] = {tid: set() for tid in tasks}
        
        for tid, task in tasks.items():
            for dep_id in task.dependencies:
                if dep_id in tasks:
                    graph[dep_id].add(tid)
                    in_degree[tid] += 1
        
        # BFS sort
        queue_list = [tid for tid, degree in in_degree.items() if degree == 0]
        result = []
        
        while queue_list:
            tid = queue_list.pop(0)
            result.append(tid)
            
            for neighbor in graph[tid]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue_list.append(neighbor)
        
        # Detect circular dependency
        if len(result) != len(tasks):
            missing = set(tasks.keys()) - set(result)
            raise ValueError(f"Circular dependency detected: {missing}")
        
        return result
    
    def execute_parallel(
        self,
        funcs: List[Tuple[str, Callable, Tuple, Dict]],
        max_workers: Optional[int] = None
    ) -> Dict[str, TaskResult]:
        """
        Execute multiple functions in parallel (no dependencies)
        
        Args:
            funcs: Function list [(task_id, func, args, kwargs), ...]
            max_workers: Maximum concurrency
        
        Returns:
            Result dictionary
        """
        workers = max_workers or self.max_workers
        
        futures: Dict[str, Future] = {}
        results: Dict[str, TaskResult] = {}
        
        for task_id, func, args, kwargs in funcs:
            task = Task(task_id=task_id, func=func, args=args, kwargs=kwargs)
            future = self._executor.submit(task.execute)
            futures[task_id] = future
        
        for task_id, future in futures.items():
            try:
                results[task_id] = future.result()
            except Exception as e:
                results[task_id] = TaskResult(
                    task_id=task_id,
                    status=TaskStatus.FAILED,
                    error=str(e)
                )
        
        return results
    
    def map_parallel(
        self,
        func: Callable,
        items: List[Any],
        max_workers: Optional[int] = None
    ) -> List[Any]:
        """
        Parallel map
        
        Args:
            func: Map function
            items: Input item list
            max_workers: Maximum concurrency
        
        Returns:
            Result list
        """
        workers = max_workers or self.max_workers
        
        results = list(self._executor.map(func, items))
        return results
    
    def shutdown(self, wait: bool = True) -> None:
        """Shutdown executor"""
        self._executor.shutdown(wait=wait)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics"""
        with self._lock:
            total = len(self._tasks)
            completed = sum(1 for r in self._results.values() if r.status == TaskStatus.COMPLETED)
            failed = sum(1 for r in self._results.values() if r.status == TaskStatus.FAILED)
            
            return {
                "total_tasks": total,
                "completed": completed,
                "failed": failed,
                "max_workers": self.max_workers,
                "executor_type": self.executor_type.value,
            }
    
    def clear(self) -> None:
        """Clear all tasks and results"""
        with self._lock:
            self._tasks.clear()
            self._results.clear()


# Convenience functions
def parallel_map(func: Callable, items: List[Any], max_workers: int = 4) -> List[Any]:
    """Parallel map (convenience function)"""
    executor = ParallelExecutor(max_workers=max_workers)
    try:
        return executor.map_parallel(func, items)
    finally:
        executor.shutdown()


def parallel_execute(
    funcs: List[Tuple[str, Callable, Tuple, Dict]],
    max_workers: int = 4
) -> Dict[str, TaskResult]:
    """Execute multiple functions in parallel (convenience function)"""
    executor = ParallelExecutor(max_workers=max_workers)
    try:
        return executor.execute_parallel(funcs)
    finally:
        executor.shutdown()
