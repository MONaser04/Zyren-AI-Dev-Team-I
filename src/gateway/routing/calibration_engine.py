import asyncio
import logging
import random
from gateway.bayesian_tracker import BayesianTracker
from gateway.model_registry import AutoModelRegistry
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class CalibrationTask:
    model_id: str
    
class CalibrationEngine:
    """
    Offline Calibration Queue for unknown models.
    Updates the Bayesian Posterior based on empirical tests.
    """
    _instance = None
    
    @classmethod
    def get_instance(cls, registry=None, tracker=None):
        if cls._instance is None:
            if registry and tracker:
                cls._instance = cls(registry, tracker)
        return cls._instance
        
    def __init__(self, registry: AutoModelRegistry, tracker: BayesianTracker):
        self.registry = registry
        self.tracker = tracker
        self.queue: asyncio.Queue[CalibrationTask] = asyncio.Queue()
        self._worker_task = None
        self.gateway = None
        CalibrationEngine._instance = self

    def set_gateway(self, gateway):
        self.gateway = gateway

    def start(self):
        if self._worker_task is None:
            try:
                loop = asyncio.get_running_loop()
                self._worker_task = loop.create_task(self._worker_loop())
                logger.info("CalibrationEngine started background worker.")
            except RuntimeError:
                pass # Event loop not running yet.

    def enqueue(self, model_id: str):
        if not hasattr(self, '_enqueued_models'):
            self._enqueued_models = set()
            
        if model_id in self._enqueued_models:
            return
            
        self._enqueued_models.add(model_id)
        self.start() # Ensure it's started lazily if the loop is now running
        self.queue.put_nowait(CalibrationTask(model_id=model_id))
        logger.debug(f"Enqueued {model_id} for offline calibration.")

    async def _worker_loop(self):
        while True:
            task = await self.queue.get()
            try:
                await self._calibrate_model(task.model_id)
            except Exception as e:
                logger.error(f"Calibration failed for {task.model_id}: {e}")
            finally:
                self.queue.task_done()

    async def _calibrate_model(self, model_id: str):
        logger.info(f"Starting empirical calibration (80 Golden Questions - MT-Bench Standard) for {model_id}...")
        
        if self.gateway:
            from gateway.evaluator import ModelEvaluator
            evaluator = ModelEvaluator(self.gateway)
            await evaluator.calibrate_offline(model_id)
            logger.info(f"Real MT-Bench calibration completed for {model_id}.")
        else:
            logger.error("CalibrationEngine has no gateway set. Cannot run real evaluation.")
            return
            
        try:
            import json
            from pathlib import Path
            state = self.tracker.get_state(model_id)
            expected = state.expected_value
            estimated_elo = int(1000 + (expected * 300))
            
            bench_file = Path(__file__).parent.parent / "model_benchmarks.json"
            
            data = {"models": {}}
            if bench_file.exists():
                with open(bench_file, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                    except json.JSONDecodeError:
                        pass
                
            if "models" not in data:
                data["models"] = {}
                
            data["models"][model_id] = {
                "coding_score": expected,
                "reasoning_score": expected,
                "general_score": expected,
                "elo_rating": estimated_elo,
                "recommended_tier": "complex" if expected >= 0.7 else "fast",
                "family": "default" # Fallback family
            }
            
            with open(bench_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            logger.info(f"Persisted empirical benchmark for {model_id} to JSON.")
        except Exception as e:
            logger.error(f"Failed to persist benchmarks: {e}")
