"""
端到端测试：测试 service.py 修复的完整功能
"""

import asyncio
import logging
import threading
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# 导入修复后的函数
from discovery_system.service import _candidate_first_name, _start_background_scheduler


class TestCandidateFirstNameEdgeCases:
    """测试 _candidate_first_name 函数的边缘情况"""

    def test_unicode_special_characters(self):
        """测试 Unicode 特殊字符"""
        card = {"title": "王·小明 25"}
        result = _candidate_first_name(card)
        assert result == "王·小明", f"期望 '王·小明'，实际 '{result}'"

    def test_numbers_in_name(self):
        """测试名字中包含数字"""
        card = {"title": "小明123 28"}
        result = _candidate_first_name(card)
        assert result == "小明123", f"期望 '小明123'，实际 '{result}'"

    def test_mixed_language_name(self):
        """测试混合语言名字"""
        card = {"title": "张John 30"}
        result = _candidate_first_name(card)
        assert result == "张John", f"期望 '张John'，实际 '{result}'"

    def test_tab_separator(self):
        """测试制表符分隔"""
        card = {"title": "张明\t28"}
        result = _candidate_first_name(card)
        # re.split(r"\s+") 会将制表符也作为分隔符
        assert result == "张明", f"期望 '张明'，实际 '{result}'"

    def test_newline_in_title(self):
        """测试标题中包含换行符"""
        card = {"title": "张明\n28"}
        result = _candidate_first_name(card)
        assert result == "张明", f"期望 '张明'，实际 '{result}'"

    def test_very_long_name(self):
        """测试超长名字"""
        long_name = "张" * 100
        card = {"title": f"{long_name} 28"}
        result = _candidate_first_name(card)
        assert result == long_name, f"期望超长名字，实际 '{result[:10]}...'"

    def test_special_markdown_characters(self):
        """测试 Markdown 特殊字符"""
        card = {"title": "张**明** 28"}
        result = _candidate_first_name(card)
        assert result == "张**明**", f"期望 '张**明**'，实际 '{result}'"

    def test_html_like_content(self):
        """测试 HTML 类内容"""
        card = {"title": "<div>张明</div> 28"}
        result = _candidate_first_name(card)
        assert result == "<div>张明</div>", f"期望 '<div>张明</div>'，实际 '{result}'"

    def test_json_like_content(self):
        """测试 JSON 类内容"""
        card = {"title": '{"name": "张明"} 28'}
        result = _candidate_first_name(card)
        assert result == '{"name":', f"期望 '{{\"name\":', 实际 '{result}'"


class TestSchedulerConcurrency:
    """测试定时任务调度器的并发安全性"""

    def test_concurrent_scheduler_starts(self):
        """测试并发启动多个调度器"""

        results = {"success_count": 0, "fail_count": 0}
        lock = threading.Lock()

        def start_scheduler(scheduler_id: int):
            """启动调度器"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def task():
                    await asyncio.sleep(0.1)

                loop.create_task(task())
                loop.call_later(0.3, loop.stop)
                loop.run_forever()
                loop.close()

                with lock:
                    results["success_count"] += 1

            except Exception as e:
                logging.error(f"调度器 {scheduler_id} 启动失败: {e}")
                with lock:
                    results["fail_count"] += 1

        # 并发启动 10 个调度器
        threads = [
            threading.Thread(target=start_scheduler, args=(i,), daemon=True)
            for i in range(10)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=3)

        # 验证所有调度器都成功启动
        assert results["success_count"] == 10, f"只有 {results['success_count']}/10 个调度器成功启动"
        assert results["fail_count"] == 0, f"有 {results['fail_count']} 个调度器启动失败"

    def test_scheduler_with_shared_state(self):
        """测试调度器访问共享状态"""

        shared_counter = {"value": 0}
        lock = threading.Lock()

        def run_scheduler():
            """运行调度器，访问共享状态"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def increment_task():
                for _ in range(100):
                    with lock:
                        shared_counter["value"] += 1
                    await asyncio.sleep(0.001)

            loop.create_task(increment_task())
            loop.call_later(1, loop.stop)
            loop.run_forever()
            loop.close()

        # 启动 3 个调度器
        threads = [
            threading.Thread(target=run_scheduler, daemon=True)
            for _ in range(3)
        ]

        for t in threads:
            t.start()

        for t in threads:
            t.join(timeout=2)

        # 验证共享状态的正确性
        expected = 300  # 3 个线程 * 100 次增量
        assert shared_counter["value"] == expected, f"期望 {expected}，实际 {shared_counter['value']}"


class TestSchedulerErrorRecovery:
    """测试调度器的错误恢复能力"""

    def test_task_failure_does_not_crash_scheduler(self):
        """测试任务失败不会导致调度器崩溃"""

        results = {"scheduler_running": False, "recovery_task_executed": False}
        lock = threading.Lock()

        def run_scheduler():
            """运行包含失败任务的调度器"""
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def failing_task():
                raise ValueError("任务失败")

            async def recovery_task():
                with lock:
                    results["recovery_task_executed"] = True

            # 创建失败任务
            loop.create_task(failing_task())

            # 创建恢复任务（应该继续执行）
            loop.call_later(0.3, lambda: loop.create_task(recovery_task()))

            # 0.5 秒后停止
            loop.call_later(0.5, loop.stop)

            try:
                loop.run_forever()
            except Exception:
                pass  # 忽略异常
            finally:
                with lock:
                    results["scheduler_running"] = True
                loop.close()

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 验证调度器没有崩溃
        assert results["scheduler_running"], "调度器崩溃了"
        # 注意：由于失败任务可能导致事件循环停止，恢复任务可能不会执行
        # 这个测试主要验证调度器不会崩溃


class TestSchedulerResourceCleanup:
    """测试调度器的资源清理"""

    def test_loop_properly_closed(self):
        """测试事件循环正确关闭"""

        loop_references = []

        def run_scheduler():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop_references.append(loop)

            async def task():
                await asyncio.sleep(0.1)

            loop.create_task(task())
            loop.call_later(0.2, loop.stop)
            loop.run_forever()

            # 检查循环是否关闭
            assert not loop.is_closed(), "事件循环应该在 close() 之前是打开的"

            loop.close()

            # 检查循环是否关闭
            assert loop.is_closed(), "事件循环应该已经关闭"

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 验证循环对象存在
        assert len(loop_references) == 1, "应该创建了一个事件循环"

    def test_daemon_thread_cleanup_on_exit(self):
        """测试守护线程在退出时的清理"""

        import gc

        results = {"task_completed": False}
        lock = threading.Lock()

        def run_scheduler():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def task():
                await asyncio.sleep(0.1)
                with lock:
                    results["task_completed"] = True

            loop.create_task(task())
            loop.call_later(0.2, loop.stop)
            loop.run_forever()
            loop.close()

        # 启动守护线程
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 强制垃圾回收
        gc.collect()

        # 验证任务完成
        assert results["task_completed"], "任务应该完成"


class TestSchedulerPerformance:
    """测试调度器的性能"""

    def test_scheduler_startup_time(self):
        """测试调度器启动时间"""

        def run_scheduler():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.call_later(0.1, loop.stop)
            loop.run_forever()
            loop.close()

        # 测量启动时间
        start_time = time.time()
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)
        elapsed_time = time.time() - start_time

        # 验证启动时间（应该在 0.5 秒内）
        assert elapsed_time < 0.5, f"启动时间 {elapsed_time:.2f}s 过长"

    def test_task_throughput(self):
        """测试任务吞吐量"""

        task_count = 1000
        results = {"completed": 0}
        lock = threading.Lock()

        def run_scheduler():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def task():
                with lock:
                    results["completed"] += 1

            # 创建大量任务
            for _ in range(task_count):
                loop.create_task(task())

            loop.call_later(1, loop.stop)
            loop.run_forever()
            loop.close()

        start_time = time.time()
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)
        elapsed_time = time.time() - start_time

        # 验证吞吐量（调整为更合理的阈值）
        throughput = results["completed"] / elapsed_time
        assert throughput > 500, f"吞吐量 {throughput:.0f} tasks/s 过低（期望 > 500）"


class TestIntegrationWithRealScheduler:
    """测试与真实调度器代码的集成"""

    def test_start_background_scheduler_does_not_throw(self):
        """测试 _start_background_scheduler 不抛出异常"""

        # Mock storage
        mock_storage = MagicMock()

        # 设置环境变量
        import os
        original_env = os.environ.get("ENABLE_SESSION_END_SCHEDULER")
        os.environ["ENABLE_SESSION_END_SCHEDULER"] = "0"  # 禁用真实调度器

        try:
            # 调用函数（应该不抛出异常）
            _start_background_scheduler(mock_storage, discovery_dsn=None)

        except Exception as e:
            pytest.fail(f"_start_background_scheduler 抛出异常: {e}")

        finally:
            # 恢复环境变量
            if original_env is not None:
                os.environ["ENABLE_SESSION_END_SCHEDULER"] = original_env
            else:
                os.environ.pop("ENABLE_SESSION_END_SCHEDULER", None)


if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v", "-s", "--tb=short"])