"""Market Study — competitive analysis for user-facing tasks.

Performs market research and competitive analysis for tasks tagged
with "needs_market_study", providing context on competitors,
positioning, and risks before implementation.

Usage:
    from BrainDock.market_study import MarketStudyAgent, MarketStudyResult

    agent = MarketStudyAgent(llm=my_backend)
    result = agent.analyze(task_dict, context=project_context)
"""

from .models import MarketStudyResult
from .agent import MarketStudyAgent

__all__ = [
    "MarketStudyResult",
    "MarketStudyAgent",
]
