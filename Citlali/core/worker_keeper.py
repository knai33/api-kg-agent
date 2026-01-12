from loguru import logger

class WorkerKeeper:
    def __init__(self):
        self._workers = dict()

    def register(self, worker):
        worker_instance = worker()
        self._workers[worker_instance.name] = worker_instance
        return worker_instance

    def get_worker(self, worker_name):
        if worker_name in self._workers:
            return self._workers[worker_name]
        else:
            logger.error(f"Worker {worker_name} not found")
            return None