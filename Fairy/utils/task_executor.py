import asyncio

from loguru import logger


class TaskExecutor:
    def __init__(self, task_name, task_desc, retry_times: int = 3):
        self.task_name = f"TASK [{task_name}]{f'({task_desc})' if task_desc is not None else ''}"
        self.retry_times = retry_times

    async def run(self, func):
        for i in range(self.retry_times+1):
            err_flag = False
            try:
               return await func()
            except Exception as e:
                logger.error(f"{self.task_name} execution failed, error details: {str(e)}.")
                err_flag = True

            if not err_flag:
                break

            elif i < self.retry_times:
                logger.error(f"{self.task_name} retrying [{i}/{self.retry_times}] ...")
                await asyncio.sleep(2)
                continue

            elif i == self.retry_times:
                logger.critical(f"{self.task_name} execution terminated, attempts exhausted.")
                raise RuntimeError(f"{self.task_name} execution terminated, attempts exhausted.")