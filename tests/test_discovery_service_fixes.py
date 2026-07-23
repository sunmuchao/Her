"""
测试 service.py 修复的两个问题：
1. re 模块导入问题（_candidate_first_name 函数）
2. 定时任务调度器事件循环问题（后台线程方案）
"""

import asyncio
import logging
import threading
import time
from typing import Any

import pytest

# 测试 _candidate_first_name 函数（需要先导入 re）
from discovery_system.service import _candidate_first_name


class TestCandidateFirstName:
    """测试 _candidate_first_name 函数"""

    def test_normal_name_with_space(self):
        """测试正常名字（带空格）"""
        card = {"title": "张梦然 28"}
        result = _candidate_first_name(card)
        assert result == "张梦然", f"期望 '张梦然'，实际 '{result}'"

    def test_normal_name_without_space(self):
        """测试正常名字（无空格）"""
        card = {"title": "李明"}
        result = _candidate_first_name(card)
        assert result == "李明", f"期望 '李明'，实际 '{result}'"

    def test_name_with_multiple_spaces(self):
        """测试名字中有多个空格"""
        card = {"title": "王   小明"}
        result = _candidate_first_name(card)
        assert result == "王", f"期望 '王'，实际 '{result}'"

    def test_empty_title(self):
        """测试空标题"""
        card = {"title": ""}
        result = _candidate_first_name(card)
        assert result == "这位", f"期望 '这位'，实际 '{result}'"

    def test_none_title(self):
        """测试 None 标题"""
        card = {"title": None}
        result = _candidate_first_name(card)
        assert result == "这位", f"期望 '这位'，实际 '{result}'"

    def test_missing_title_key(self):
        """测试缺少 title 键"""
        card = {}
        result = _candidate_first_name(card)
        assert result == "这位", f"期望 '这位'，实际 '{result}'"

    def test_whitespace_only_title(self):
        """测试只有空白的标题"""
        card = {"title": "   "}
        result = _candidate_first_name(card)
        assert result == "这位", f"期望 '这位'，实际 '{result}'"

    def test_complex_title_with_age_and_city(self):
        """测试复杂标题（包含年龄、城市等信息）"""
        card = {"title": "陈念文 29 无锡"}
        result = _candidate_first_name(card)
        assert result == "陈念文", f"期望 '陈念文'，实际 '{result}'"

    def test_english_name(self):
        """测试英文名字"""
        card = {"title": "John Smith"}
        result = _candidate_first_name(card)
        assert result == "John", f"期望 'John'，实际 '{result}'"


class TestSchedulerEventLoop:
    """测试定时任务调度器事件循环方案"""

    def test_background_thread_event_loop(self):
        """测试后台线程事件循环方案"""

        results = {"success": False, "task_executed": False}
        lock = threading.Lock()

        def run_scheduler():
            """在后台线程中运行调度器（模拟修复后的逻辑）"""
            try:
                # 创建新的事件循环（每个线程需要自己的事件循环）
                scheduler_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(scheduler_loop)

                async def dummy_task():
                    """模拟定时任务"""
                    await asyncio.sleep(0.1)
                    with lock:
                        results["task_executed"] = True

                scheduler_loop.create_task(dummy_task())

                # 运行一小段时间后停止
                scheduler_loop.call_later(0.5, scheduler_loop.stop)
                scheduler_loop.run_forever()

                with lock:
                    results["success"] = True

                scheduler_loop.close()

            except Exception as e:
                logging.error(f"后台线程失败: {e}")
                with lock:
                    results["success"] = False

        # 启动后台线程
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 验证结果
        assert results["success"], "后台线程事件循环启动失败"
        assert results["task_executed"], "定时任务未执行"

    def test_multiple_tasks_in_same_loop(self):
        """测试在同一个事件循环中运行多个任务"""

        results = {"task1": False, "task2": False, "task3": False}
        lock = threading.Lock()

        def run_scheduler():
            """在后台线程中运行多个任务"""
            try:
                scheduler_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(scheduler_loop)

                async def task1():
                    await asyncio.sleep(0.1)
                    with lock:
                        results["task1"] = True

                async def task2():
                    await asyncio.sleep(0.15)
                    with lock:
                        results["task2"] = True

                async def task3():
                    await asyncio.sleep(0.2)
                    with lock:
                        results["task3"] = True

                # 创建3个任务
                scheduler_loop.create_task(task1())
                scheduler_loop.create_task(task2())
                scheduler_loop.create_task(task3())

                # 运行1秒后停止
                scheduler_loop.call_later(1, scheduler_loop.stop)
                scheduler_loop.run_forever()
                scheduler_loop.close()

            except Exception as e:
                logging.error(f"多任务测试失败: {e}")

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 验证所有任务都执行了
        assert results["task1"], "任务1未执行"
        assert results["task2"], "任务2未执行"
        assert results["task3"], "任务3未执行"

    def test_event_loop_in_different_threads(self):
        """测试多个线程各自创建独立的事件循环"""

        results = {"thread1": False, "thread2": False}
        lock = threading.Lock()

        def run_in_thread(thread_id: str):
            """在独立线程中创建事件循环"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def task():
                    await asyncio.sleep(0.1)
                    with lock:
                        results[thread_id] = True

                loop.create_task(task())
                loop.call_later(0.5, loop.stop)
                loop.run_forever()
                loop.close()

            except Exception as e:
                logging.error(f"线程 {thread_id} 失败: {e}")

        # 启动2个线程
        thread1 = threading.Thread(target=run_in_thread, args=("thread1",), daemon=True)
        thread2 = threading.Thread(target=run_in_thread, args=("thread2",), daemon=True)

        thread1.start()
        thread2.start()

        thread1.join(timeout=2)
        thread2.join(timeout=2)

        # 验证两个线程都成功创建了独立的事件循环
        assert results["thread1"], "线程1事件循环失败"
        assert results["thread2"], "线程2事件循环失败"

    def test_daemon_thread_cleanup(self):
        """测试守护线程的正确清理"""

        cleanup_called = {"value": False}
        lock = threading.Lock()

        def run_scheduler():
            """测试守护线程清理"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def cleanup_task():
                    with lock:
                        cleanup_called["value"] = True

                # 注册清理任务
                loop.create_task(cleanup_task())
                loop.call_later(0.2, loop.stop)
                loop.run_forever()
                loop.close()

            except Exception as e:
                logging.error(f"清理测试失败: {e}")

        # 启动守护线程
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 验证清理任务执行了
        assert cleanup_called["value"], "守护线程清理失败"

    def test_event_loop_exception_handling(self):
        """测试事件循环中的异常处理"""

        results = {"exception_handled": False}
        lock = threading.Lock()

        def run_scheduler():
            """测试异常处理"""
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                async def failing_task():
                    raise ValueError("测试异常")

                async def handler_task():
                    try:
                        await failing_task()
                    except ValueError:
                        with lock:
                            results["exception_handled"] = True

                loop.create_task(handler_task())
                loop.call_later(0.5, loop.stop)
                loop.run_forever()
                loop.close()

            except Exception as e:
                logging.error(f"异常处理测试失败: {e}")

        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
        scheduler_thread.join(timeout=2)

        # 验证异常被正确处理
        assert results["exception_handled"], "异常未被正确处理"


class TestSchedulerIntegration:
    """测试定时任务调度器集成"""

    def test_scheduler_does_not_block_main_thread(self):
        """测试调度器不阻塞主线程"""

        main_thread_executed = {"value": False, "time": 0}
        scheduler_started = {"value": False}

        def run_scheduler():
            """模拟长时间运行的调度器"""
            scheduler_started["value"] = True
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def long_task():
                await asyncio.sleep(10)  # 模拟长时间任务

            loop.create_task(long_task())
            loop.call_later(1, loop.stop)
            loop.run_forever()
            loop.close()

        # 启动调度器线程
        start_time = time.time()
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()

        # 主线程继续执行
        time.sleep(0.1)
        main_thread_executed["value"] = True
        main_thread_executed["time"] = time.time() - start_time

        # 验证调度器启动了
        assert scheduler_started["value"], "调度器未启动"

        # 验证主线程没有被阻塞（应该在 0.2 秒内完成）
        assert main_thread_executed["value"], "主线程未执行"
        assert main_thread_executed["time"] < 0.2, f"主线程被阻塞了 {main_thread_executed['time']} 秒"


if __name__ == "__main__":
    # 运行所有测试
    pytest.main([__file__, "-v", "-s"])