import asyncio
import logging
import inspect
from typing import Callable, Coroutine, Any, Awaitable

logger = logging.getLogger(__name__)

class TaskTracker:
    """
    Tracks asyncio background tasks to prevent garbage collection 
    and allows graceful shutdown flushing.
    """
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def spawn(self, coro_factory: Callable[..., Coroutine | Awaitable], *args, fallback: str = "drop", **kwargs) -> asyncio.Task | None:
        """
        Safely spawn a fire-and-forget background task.
        
        fallback options:
        - "drop": If no event loop exists, drop the task and do nothing.
        - "sync": If no event loop exists, run it synchronously using asyncio.run.
        """
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            if fallback == "sync":
                logger.warning(f"TaskTracker: no event loop, executing {coro_factory.__name__} synchronously (fallback='sync')")
                try:
                    return asyncio.run(coro_factory(*args, **kwargs))
                except Exception as e:
                    logger.error(f"TaskTracker sync fallback failed: {e}")
                    return None
            else:
                logger.warning(f"TaskTracker: no event loop, dropping {coro_factory.__name__} (fallback='drop')")
                return None
                
        # Create coroutine from factory
        coro = coro_factory(*args, **kwargs)
        
        # In rare cases if the factory didn't return an awaitable
        if getattr(coro, "__await__", None) is None:
            # It might have just been a normal function
            if asyncio.iscoroutinefunction(coro_factory):
                pass # Something went wrong creating it
            return None

        task = loop.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def shutdown(self, timeout: float = 5.0):
        """
        Wait for all tracked tasks to complete, with a timeout.
        Cancel any that exceed the timeout.
        """
        if not self._tasks:
            return

        logger.info(f"TaskTracker: draining {len(self._tasks)} background tasks (timeout={timeout}s)")
        
        # wait expects a collection of tasks.
        pending = list(self._tasks)
        
        # We need to suppress the task exceptions so wait() doesn't crash if a task failed.
        # wait() automatically suppresses them and returns done/pending.
        done, pending = await asyncio.wait(pending, timeout=timeout)
        
        if pending:
            logger.warning(f"TaskTracker: {len(pending)} tasks did not finish in time, cancelling...")
            for task in pending:
                task.cancel()
                
            # Wait for cancellations to process
            await asyncio.wait(pending, timeout=1.0)
            
        logger.info("TaskTracker: shutdown complete")

# Global singleton
task_tracker = TaskTracker()
