import asyncio
from datetime import datetime, UTC
from gateway.bayesian_tracker import BayesianTracker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_beta_routing():
    tracker = BayesianTracker()
    
    model_id = "test/unknown-beta-model"
    
    print("--- Initial State (Unknown Model) ---")
    state = tracker.get_state(model_id)
    print(f"alpha={state.alpha:.3f}, beta={state.beta:.3f}, expected_value={state.expected_value:.3f}")
    
    print("\n--- Thompson Sampling (Beta Distribution) ---")
    # Sample 5 times. High uncertainty means values can be anywhere from 0 to 1, but NEVER outside.
    samples = [tracker.sample(model_id) for _ in range(5)]
    print(f"Sampled scores: {[round(s, 3) for s in samples]}")
    assert all(0.0 <= s <= 1.0 for s in samples), "Math Error: Samples outside [0, 1]"
    
    print("\n--- Simulating Feedback (Offline Calibration) ---")
    # Suppose the model did a great job 3 times in a row against reference answers
    tracker.update_state(model_id, 0.9)
    tracker.update_state(model_id, 0.85)
    tracker.update_state(model_id, 0.95)
    
    state = tracker.get_state(model_id)
    print(f"New state: alpha={state.alpha:.3f}, beta={state.beta:.3f}, expected_value={state.expected_value:.3f}")
    
    print("\n--- Thompson Sampling After Calibration ---")
    # Now the variance should be much tighter around the high mean
    samples = [tracker.sample(model_id) for _ in range(5)]
    print(f"Sampled scores: {[round(s, 3) for s in samples]}")
    assert all(0.0 <= s <= 1.0 for s in samples), "Math Error: Samples outside [0, 1]"
    
    print("\n--- Time Decay Simulation ---")
    # Force the last_updated time to be 100 days ago to show strong decay
    state.last_updated = datetime.now(UTC).timestamp() - (86400 * 100)
    
    # Get state again (will trigger time decay, pushing alpha/beta towards 1.0)
    state = tracker.get_state(model_id)
    print(f"State after 100 days of inactivity: alpha={state.alpha:.3f}, beta={state.beta:.3f}, expected_value={state.expected_value:.3f}")
    
if __name__ == "__main__":
    test_beta_routing()
