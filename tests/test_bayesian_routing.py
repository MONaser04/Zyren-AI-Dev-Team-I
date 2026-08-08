import asyncio
from datetime import datetime, UTC
from gateway.bayesian_tracker import BayesianTracker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_bayesian_routing():
    tracker = BayesianTracker()
    
    model_id = "test/unknown-model-1"
    
    print("--- Initial State (Unknown Model) ---")
    state = tracker.get_state(model_id)
    print(f"mu={state.mu:.3f}, sigma={state.sigma:.3f}, samples={state.total_samples}")
    
    print("\n--- Thompson Sampling (Exploration) ---")
    # Sample 5 times. High sigma means high variance in scores
    samples = [tracker.sample(model_id) for _ in range(5)]
    print(f"Sampled scores: {[round(s, 3) for s in samples]}")
    
    print("\n--- Simulating Feedback (Exploitation Phase) ---")
    # Suppose the model did a great job 3 times in a row
    tracker.update_state(model_id, 0.9)
    tracker.update_state(model_id, 0.85)
    tracker.update_state(model_id, 0.95)
    
    state = tracker.get_state(model_id)
    print(f"New state: mu={state.mu:.3f}, sigma={state.sigma:.3f}, samples={state.total_samples}")
    
    print("\n--- Thompson Sampling After Feedback ---")
    # Now the variance should be much tighter around the high mean
    samples = [tracker.sample(model_id) for _ in range(5)]
    print(f"Sampled scores: {[round(s, 3) for s in samples]}")
    
    print("\n--- Time Decay Simulation ---")
    # Force the last_updated time to be 10 days ago
    state.last_updated = datetime.now(UTC).timestamp() - (86400 * 10)
    
    # Get state again (will trigger time decay)
    state = tracker.get_state(model_id)
    print(f"State after 10 days of inactivity: mu={state.mu:.3f}, sigma={state.sigma:.3f}")
    
if __name__ == "__main__":
    test_bayesian_routing()
