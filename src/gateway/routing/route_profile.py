import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# The Structured Family Graph Priors
# Weak Informative Integer Priors to resolve Bayesian Deadlock
FAMILY_PRIORS: Dict[str, tuple[float, float]] = {
    "deepseek": (2.0, 1.0),
    "claude": (2.0, 1.0),
    "gpt-4": (2.0, 1.0),
    "nemotron": (2.0, 1.0),
    "llama": (2.0, 1.0), 
    "qwen": (2.0, 1.0),
    "default": (1.0, 1.0) # Uninformative uniform prior if completely unknown
}

# Domains that boost the alpha score if the model is explicitly specialized
# Removed to enforce strictly Beta(2,1) or Beta(1,1) per architecture directive
DOMAIN_BOOSTS: Dict[str, float] = {}

class RouteProfile:
    @staticmethod
    def extract_profile_priors(model_id: str) -> tuple[float, float]:
        """
        Implements Zero-Shot Graph-Based Profiling (RouteProfile AAAI 2026).
        Extracts structural edges (Family, Domain) from the public model ID
        and returns robust Bayesian priors (alpha, beta).
        """
        model_id_lower = model_id.lower()
        
        # 1. Extract Family Edge
        base_alpha, base_beta = FAMILY_PRIORS["default"]
        matched_family = "default"
        for family, (a, b) in FAMILY_PRIORS.items():
            if family in model_id_lower:
                # Use the one with the highest expected value
                if a / (a + b) > base_alpha / (base_alpha + base_beta):
                    base_alpha, base_beta = a, b
                    matched_family = family
        
        # 2. Extract Domain Edge
        domain_boost = 0.0
        for domain, boost in DOMAIN_BOOSTS.items():
            if domain in model_id_lower:
                if boost > domain_boost:
                    domain_boost = boost
                
        # 3. Calculate Final Structured Prior
        final_alpha = base_alpha + domain_boost
        final_beta = base_beta
        
        logger.debug(f"RouteProfile | Model: {model_id} | Family Edge: {matched_family} | Prior: Beta({final_alpha:.1f}, {final_beta:.1f})")
        return final_alpha, final_beta
