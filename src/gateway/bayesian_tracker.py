import json
import math
import logging
from dataclasses import dataclass, asdict
from datetime import datetime, UTC
from pathlib import Path
import random

logger = logging.getLogger(__name__)

from dataclasses import dataclass, asdict, field

@dataclass
class BetaState:
    alpha: float        # Successes + 1
    beta: float         # Failures + 1
    last_updated: float # UNIX timestamp
    total_samples: int  = 0
    completed_questions: list[str] = field(default_factory=list)
    
    @property
    def expected_value(self) -> float:
        return self.alpha / (self.alpha + self.beta)

class BayesianTracker:
    """
    Bayesian Performance Tracker for LLM Routing.
    Uses Beta Distribution (alpha, beta) and Thompson Sampling for exploration/exploitation.
    Guarantees mathematically bounded probabilities [0, 1].
    """
    
    def __init__(self):
        self.state_file = Path(__file__).parent / "bayesian_state.json"
        self._states: dict[str, BetaState] = {}
        self._time_decay_rate = 0.01  # Push towards uniform distribution per day
        self._load()

    def _load(self):
        if self.state_file.exists():
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for k, v in data.items():
                        self._states[k] = BetaState(**v)
                logger.info(f"Loaded Bayesian states for {len(self._states)} models.")
            except Exception as e:
                logger.error(f"Failed to load bayesian state: {e}")

    def _save(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({k: asdict(v) for k, v in self._states.items()}, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save bayesian state: {e}")

    def _apply_time_decay(self, state: BetaState) -> BetaState:
        """Apply time decay to increase uncertainty (push alpha/beta towards 1.0) over time."""
        now = datetime.now(UTC).timestamp()
        days_passed = max(0.0, (now - state.last_updated) / 86400.0)
        
        if days_passed > 0:
            decay_factor = math.exp(-self._time_decay_rate * days_passed)
            # Shrink alpha and beta towards 1.0 (Uniform distribution = max uncertainty)
            state.alpha = 1.0 + (state.alpha - 1.0) * decay_factor
            state.beta = 1.0 + (state.beta - 1.0) * decay_factor
            state.last_updated = now
            
        return state

    def get_state(self, model_id: str, default_alpha: float = 1.0, default_beta: float = 1.0) -> BetaState:
        """Get the current state for a model, applying time decay."""
        if model_id not in self._states:
            self._states[model_id] = BetaState(
                alpha=default_alpha,
                beta=default_beta,
                last_updated=datetime.now(UTC).timestamp(),
                total_samples=0
            )
        else:
            self._states[model_id] = self._apply_time_decay(self._states[model_id])
            
        return self._states[model_id]

    def update_state(self, model_id: str, reward: float, question_id: str = None):
        """
        Bayesian update for a Beta distribution.
        Reward is expected to be between 0.0 (terrible) and 1.0 (perfect).
        """
        reward = max(0.0, min(1.0, reward)) # Clamp between 0 and 1
        
        state = self.get_state(model_id)
        
        # Beta update: add successes to alpha, failures to beta
        state.alpha += reward
        state.beta += (1.0 - reward)
        
        state.last_updated = datetime.now(UTC).timestamp()
        state.total_samples += 1
        if question_id and question_id not in state.completed_questions:
            state.completed_questions.append(question_id)
        
        self._save()
        logger.info(f"Beta update for {model_id}: alpha={state.alpha:.2f}, beta={state.beta:.2f} (reward={reward:.2f})")

    def sample(self, model_id: str, default_alpha: float = 1.0, default_beta: float = 1.0) -> float:
        """
        Thompson Sampling: Sample from the model's performance distribution Beta(alpha, beta).
        The router will pick the model with the highest sampled value.
        Guarantees returned value is exactly in [0, 1].
        """
        state = self.get_state(model_id, default_alpha, default_beta)
        
        # Sample from Beta distribution
        sampled_score = random.betavariate(state.alpha, state.beta)
        
        # Log for debugging routing choices
        logger.debug(f"Thompson Sample for {model_id}: {sampled_score:.3f} (alpha={state.alpha:.2f}, beta={state.beta:.2f})")
        
        return sampled_score
