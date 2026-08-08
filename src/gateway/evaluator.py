import json
import logging
import os
import asyncio
from typing import Any, Literal
from pydantic import BaseModel, Field

# We import these locally inside methods if needed to prevent circular imports
# But since evaluator sits alongside them, it's fine.
from gateway.smart_gateway import CompletionRequest

logger = logging.getLogger(__name__)

class BatchJudgeResponse(BaseModel):
    evaluations: dict[str, float] = Field(
        description="Dictionary mapping question ID to its score between 0.0 and 1.0"
    )

class ModelEvaluator:
    """Automated LLM-as-a-judge for Offline Calibration."""

    def __init__(self, gateway: Any) -> None:
        self.gateway = gateway
        self.judge_model = "nvidia_nim/meta/llama-3.1-70b-instruct"
        
        # Load golden dataset with reference answers
        dataset_path = os.path.join(os.path.dirname(__file__), "golden_dataset.json")
        try:
            with open(dataset_path, "r", encoding="utf-8") as f:
                self.dataset = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load golden dataset: {e}")
            self.dataset = {"coding": [], "reasoning": [], "general": []}

    async def _get_model_response(self, model_id: str, prompt: str) -> str | None:
        """Fetch response from a specific model."""
        try:
            req = CompletionRequest(
                model=model_id,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0
            )
            resp = await self.gateway.complete(req)
            return resp.content
        except Exception as e:
            logger.warning(f"Error getting response from {model_id}: {e}")
            return None

    async def calibrate_offline(self, model_id: str) -> None:
        """
        Run isolated offline calibration for an unknown model against the golden dataset.
        This updates the Beta Distribution parameters (alpha, beta) for the model.
        """
        logger.info(f"Starting offline calibration for {model_id}...")
        
        completed = set()
        if hasattr(self.gateway, '_router') and hasattr(self.gateway._router, 'bayesian_tracker'):
            state = self.gateway._router.bayesian_tracker.get_state(model_id)
            # Safeguard: if it already has 80 samples, it's fully calibrated, skip it entirely
            if state.total_samples >= 80:
                logger.info(f"Model {model_id} already has {state.total_samples} samples (Fully Calibrated). Skipping.")
                return
            completed = set(state.completed_questions)
            
        all_questions = []
        for category, prompts in self.dataset.items():
            for p_data in prompts:
                if str(p_data["id"]) not in completed:
                    all_questions.append(p_data)
                    
        if not all_questions:
            logger.info(f"All questions already calibrated for {model_id}. Skipping.")
            return
                
        provider = model_id.split("/")[0] if "/" in model_id else "unknown"
        if provider in ("gemini", "google"):
            delay = 4.2  # ~14 RPM for Free Tier safety
        elif provider == "nvidia_nim":
            delay = 1.6  # ~37 RPM for safety
        else:
            delay = 2.0  # 30 RPM default
            
        batch_size = 10
        judge_model = self._get_judge_for_model(model_id)
        logger.info(f"Processing {len(all_questions)} questions for {model_id} in batches of {batch_size} (delay {delay}s)...")
        
        for i in range(0, len(all_questions), batch_size):
            batch_prompts = all_questions[i:i+batch_size]
            
            # 1. Fetch answers sequentially for this batch
            batch_results = []
            for p_data in batch_prompts:
                resp = await self._get_model_response(model_id, p_data["prompt"])
                batch_results.append((p_data, resp))
                await asyncio.sleep(delay)
            
            # 2. Evaluate this batch with Judge immediately
            logger.info(f"Evaluating batch {i//batch_size + 1}/{(len(all_questions)-1)//batch_size + 1} with Judge {judge_model}...")
            await self._evaluate_batch(model_id, batch_results, judge_model)
            await asyncio.sleep(1.6) # Safety delay for Judge (NVIDIA NIM)
        
        logger.info(f"Offline calibration completed for {model_id}.")

    def _get_judge_for_model(self, evaluated_model_id: str) -> str:
        """Prevent self-bias by assigning a judge from a different family."""
        model_lower = evaluated_model_id.lower()
        if "llama" in model_lower or "meta" in model_lower:
            # Fallback to Mistral Large for Llama/Meta family
            return "nvidia_nim/mistralai/mistral-large-2-instruct"
        return "nvidia_nim/meta/llama-3.1-70b-instruct"

    async def _evaluate_batch(self, model_id: str, batch: list, judge_model: str) -> None:
        system_prompt = (
            "You are an expert evaluator. You will be provided with multiple questions, reference answers, and model responses. "
            "For each item, compare the model's response to the REFERENCE ANSWER and evaluate correctness and helpfulness. "
            "Return a JSON dictionary mapping the EXACT Question ID to a score between 0.0 (completely wrong) and 1.0 (perfect)."
        )
        
        user_prompt = ""
        for p_data, response in batch:
            if not response:
                continue
            user_prompt += f"\n--- QUESTION ID: {p_data['id']} ---\n[PROMPT]\n{p_data['prompt']}\n"
            if p_data.get("reference_answer"):
                user_prompt += f"[REFERENCE ANSWER]\n{p_data['reference_answer']}\n"
            user_prompt += f"[MODEL RESPONSE]\n{response}\n"
            
        if not user_prompt:
            return
            
        try:
            req = CompletionRequest(
                model=judge_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                response_model=BatchJudgeResponse,
                temperature=0.0
            )
            
            resp = await self.gateway.complete_structured(req)
            
            for q_id, score in resp.evaluations.items():
                reward = float(score)
                if hasattr(self.gateway, '_router') and hasattr(self.gateway._router, 'bayesian_tracker'):
                    self.gateway._router.bayesian_tracker.update_state(model_id, reward, question_id=q_id)
                logger.info(f"Calibrated {model_id} on {q_id}: reward {reward:.2f}")
                
        except Exception as e:
            logger.error(f"Batch evaluation error for {model_id}: {e}")

