import asyncio
import logging
from gateway.model_registry import AutoModelRegistry
from gateway.smart_gateway import SmartGateway, RoutingCriteria
from gateway.providers.nvidia_nim import NVIDIAProviderAdapter
from gateway.providers.google import GoogleProviderAdapter
import os

logging.basicConfig(level=logging.INFO)

async def test_router():
    registry = AutoModelRegistry()
    
    # We only register a few for quick testing
    registry.register_provider(NVIDIAProviderAdapter(), priority=10)
    registry.register_provider(GoogleProviderAdapter(), priority=20)
    
    # Init
    print("Discovering models...")
    await registry.initialize(discover=True)
    
    gateway = SmartGateway(registry=registry)
    
    print("\n--- Model Classification ---")
    models = registry.get_active_models()
    for m in models:
        bs = m.benchmark_scores
        print(f"[{m.model_id}] Tier: {m.tier.value} | ELO: {bs.elo_rating if bs else 'N/A'} | Family: {bs.family if bs else 'N/A'}")
        
    print("\n--- Routing: Simple Task ---")
    try:
        criteria = RoutingCriteria(complexity="simple")
        decision = gateway._router.find_optimal_model(criteria)
        bs = decision.primary_model.benchmark_scores
        print(f"Selected: {decision.primary_model.model_id} (Family: {bs.family if bs else 'N/A'})")
    except Exception as e:
        print(f"Routing error: {e}")

    print("\n--- Routing: Critic Task (exclude llama) ---")
    try:
        criteria = RoutingCriteria(complexity="critic", exclude_family="llama")
        decision = gateway._router.find_optimal_model(criteria)
        bs = decision.primary_model.benchmark_scores
        print(f"Selected: {decision.primary_model.model_id} (Family: {bs.family if bs else 'N/A'})")
    except Exception as e:
        print(f"Routing error: {e}")

if __name__ == "__main__":
    asyncio.run(test_router())
