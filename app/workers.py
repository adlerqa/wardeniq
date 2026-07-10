# app/workers.py
import threading
import queue
import time
import sys
import traceback

class UnifiedWorkerPool:
    def __init__(self, num_workers=3):
        self.q = queue.Queue()
        self.workers = []
        self.stop_event = threading.Event()
        for i in range(num_workers):
            t = threading.Thread(target=self._loop, name=f"UnifiedWorker-{i}", daemon=True)
            t.start()
            self.workers.append(t)
            
    def _loop(self):
        while not self.stop_event.is_set():
            try:
                # Use a timeout so we check stop_event periodically
                job = self.q.get(timeout=1.0)
            except queue.Empty:
                continue
                
            try:
                print(f"[Worker] Running job {job['id']}: {job['func'].__name__}", flush=True)
                job["func"](*job["args"], **job["kwargs"])
                print(f"[Worker] Finished job {job['id']}", flush=True)
            except Exception as e:
                print(f"[Worker] Job {job['id']} failed: {e}", file=sys.stderr, flush=True)
                traceback.print_exc(file=sys.stderr)
            finally:
                self.q.task_done()
                
    def enqueue(self, job_id, func, *args, **kwargs):
        self.q.put({
            "id": job_id,
            "func": func,
            "args": args,
            "kwargs": kwargs
        })
        
    def stop(self):
        self.stop_event.set()
        for t in self.workers:
            t.join(timeout=1.0)

# Global pool instance
worker_pool = UnifiedWorkerPool()
