"""
Performance Optimizer
=========

Used to optimize the performance of the survey simulation system, including batch processing, concurrency control, and caching strategies.

Main Components:
1. PerformanceOptimizer: Main optimizer
2. BatchProcessor: Batch processor
3. CacheStrategy: Cache strategy
4. PerformanceReport: Performance report
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
import asyncio
import time
import sys
from collections import OrderedDict


@dataclass
class PerformanceReport:
    """Performance Report"""
    operation: str
    total_time: float
    item_count: int
    avg_time_per_item: float
    throughput: float  # items per second
    memory_usage_mb: float = 0.0
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "operation": self.operation,
            "total_time": self.total_time,
            "item_count": self.item_count,
            "avg_time_per_item": self.avg_time_per_item,
            "throughput": self.throughput,
            "memory_usage_mb": self.memory_usage_mb,
            "recommendations": self.recommendations,
        }


class CacheStrategy:
    """Cache strategy

    Uses LRU (Least Recently Used) cache strategy.
    """
    
    def __init__(self, max_size: int = 1000):
        """Initialize cache

        Args:
            max_size: Maximum cache entries
        """
        self.max_size = max_size
        self._cache: OrderedDict = OrderedDict()
        self._hits = 0
        self._misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value

        Args:
            key: Cache key

        Returns:
            Cached value, or None if not found
        """
        if key in self._cache:
            # Move to end (most recently used)
            self._cache.move_to_end(key)
            self._hits += 1
            return self._cache[key]
        
        self._misses += 1
        return None
    
    def set(self, key: str, value: Any) -> None:
        """Set cache value

        Args:
            key: Cache key
            value: Cache value
        """
        if key in self._cache:
            # Update and move to end
            self._cache.move_to_end(key)
            self._cache[key] = value
        else:
            # Add new entry
            self._cache[key] = value
            
            # Check if eviction is needed
            if len(self._cache) > self.max_size:
                self._cache.popitem(last=False)  # Remove oldest
    
    def clear(self) -> None:
        """Clear cache"""
        self._cache.clear()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics

        Returns:
            Statistics dictionary
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        
        return {
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "hit_rate": hit_rate,
        }


class BatchProcessor:
    """Batch processor

    Used for efficiently processing large batches of tasks, with concurrency control and error handling.
    """
    
    def __init__(
        self,
        batch_size: int = 100,
        max_concurrent: int = 10,
        timeout_seconds: int = 300
    ):
        """Initialize batch processor

        Args:
            batch_size: Batch size
            max_concurrent: Maximum concurrency
            timeout_seconds: Timeout in seconds
        """
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.timeout_seconds = timeout_seconds
    
    async def process_batch(
        self,
        items: List[Any],
        process_func: Callable,
        continue_on_error: bool = False
    ) -> List[Any]:
        """Process items in batch

        Args:
            items: List of items to process
            process_func: Processing function
            continue_on_error: Whether to continue on error

        Returns:
            List of results
        """
        semaphore = asyncio.Semaphore(self.max_concurrent)
        results = [None] * len(items)
        
        async def process_with_semaphore(index: int, item: Any):
            async with semaphore:
                try:
                    result = await process_func(item)
                    results[index] = result
                except Exception as e:
                    if not continue_on_error:
                        raise
                    results[index] = None
        
        # Create all tasks
        tasks = [
            process_with_semaphore(i, item)
            for i, item in enumerate(items)
        ]
        
        # Execute in parallel
        await asyncio.gather(*tasks)
        
        return results


class PerformanceOptimizer:
    """Performance Optimizer

    Used to optimize the overall performance of the survey simulation system.
    """
    
    def __init__(
        self,
        default_batch_size: int = 100,
        default_max_concurrent: int = 10
    ):
        """Initialize Performance Optimizer

        Args:
            default_batch_size: Default batch size
            default_max_concurrent: Default maximum concurrency
        """
        self.default_batch_size = default_batch_size
        self.default_max_concurrent = default_max_concurrent
        self._cache = CacheStrategy()
    
    async def optimize_simulation(
        self,
        personas: List[Any],
        survey: Any,
        max_concurrent: Optional[int] = None
    ) -> Dict[str, Any]:
        """Optimize simulation process

        Args:
            personas: Persona list
            survey: Survey
            max_concurrent: Maximum concurrency

        Returns:
            Dict containing responses and performance_report
        """
        from src.survey.services.simulation_engine import SimulationEngine
        
        if max_concurrent is None:
            max_concurrent = self.default_max_concurrent
        
        # Create simulation engine
        engine = SimulationEngine()
        
        # Record start time
        start_time = time.time()
        
        # Execute simulation
        responses = await engine.simulate_survey(
            personas, survey,
            parallel=True,
            max_concurrent=max_concurrent
        )
        
        # Calculate performance metrics
        elapsed_time = time.time() - start_time
        throughput = len(personas) / elapsed_time if elapsed_time > 0 else 0
        avg_time = elapsed_time / len(personas) if personas else 0
        
        # Estimate memory usage
        memory_mb = self.estimate_memory_usage(len(responses))
        
        # Generate recommendations
        recommendations = []
        if throughput < 5:
            recommendations.append("Low throughput, consider checking LLM call performance")
        if max_concurrent < 5 and len(personas) > 50:
            recommendations.append("Consider increasing concurrency to improve performance")
        if not recommendations:
            recommendations.append("Good performance")
        
        report = PerformanceReport(
            operation="simulation",
            total_time=elapsed_time,
            item_count=len(personas),
            avg_time_per_item=avg_time,
            throughput=throughput,
            memory_usage_mb=memory_mb,
            recommendations=recommendations
        )
        
        return {
            "responses": responses,
            "performance_report": report,
        }
    
    async def benchmark(
        self,
        operation: Callable,
        iterations: int = 10
    ) -> PerformanceReport:
        """Benchmark

        Args:
            operation: Operation to test
            iterations: Number of iterations

        Returns:
            Performance report
        """
        start_time = time.time()
        
        for _ in range(iterations):
            await operation()
        
        elapsed_time = time.time() - start_time
        throughput = iterations / elapsed_time if elapsed_time > 0 else 0
        avg_time = elapsed_time / iterations if iterations else 0
        
        return PerformanceReport(
            operation="benchmark",
            total_time=elapsed_time,
            item_count=iterations,
            avg_time_per_item=avg_time,
            throughput=throughput,
        )
    
    def estimate_memory_usage(self, response_count: int) -> float:
        """Estimate memory usage

        Args:
            response_count: Number of responses

        Returns:
            Estimated memory usage in MB
        """
        # Each SurveyResponse takes ~1KB
        # Each Answer takes ~0.5KB
        # Average 5 answers per response
        
        base_size = 0.001  # 1KB per response
        answer_size = 0.0005  # 0.5KB per answer
        avg_answers = 5
        
        memory_mb = response_count * (base_size + avg_answers * answer_size)
        
        return memory_mb
    
    def recommend_batch_size(self, total_items: int) -> int:
        """Recommend batch size

        Args:
            total_items: Total number of items

        Returns:
            Recommended batch size
        """
        if total_items < 100:
            return total_items
        elif total_items < 1000:
            return 50
        elif total_items < 10000:
            return 100
        else:
            return 200
    
    def recommend_concurrency(self) -> int:
        """Recommend concurrency level

        Returns:
            Recommended concurrency level
        """
        # Based on CPU core count
        cpu_count = self._get_cpu_count()
        
        # Recommended concurrency is 2-4x CPU count
        recommended = min(cpu_count * 2, 20)
        
        return max(1, recommended)
    
    def _get_cpu_count(self) -> int:
        """Get CPU core count"""
        try:
            import os
            return os.cpu_count() or 4
        except (ImportError, NotImplementedError):
            return 4
    
    async def process_with_progress(
        self,
        items: List[Any],
        process_func: Callable,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> List[Any]:
        """Process with progress tracking

        Args:
            items: Items to process
            process_func: Processing function
            progress_callback: Progress callback function

        Returns:
            List of results
        """
        total = len(items)
        completed = 0
        results = []
        
        semaphore = asyncio.Semaphore(self.default_max_concurrent)
        
        async def process_item(item: Any) -> Any:
            nonlocal completed
            async with semaphore:
                result = await process_func(item)
                completed += 1
                
                if progress_callback:
                    progress = completed / total
                    progress_callback(progress)
                
                return result
        
        tasks = [process_item(item) for item in items]
        results = await asyncio.gather(*tasks)
        
        return list(results)
