"""Debate Agent — multi-perspective reasoning for uncertain plans."""

from __future__ import annotations

import json

from BrainDock.base_agent import BaseAgent
from BrainDock.llm import LLMBackend
from BrainDock.preambles import build_system_prompt, DEV_OPS, BUSINESS_OPS
from .models import DebatePlan, Critique, DebateOutcome
from .prompts import (
    SYSTEM_PROMPT,
    PROPOSE_PROMPT,
    CRITIQUE_PROMPT,
    SYNTHESIZE_PROMPT,
)

MAX_ROUNDS = 3


class DebateAgent(BaseAgent):
    """Agent that debates uncertain plans from multiple perspectives.

    Generates proposals, critiques them iteratively, and synthesizes
    the best approach. Limited to MAX_ROUNDS exchanges.

    Usage:
        agent = DebateAgent(llm=my_backend)
        outcome = agent.debate(plan_dict, context)
    """

    def __init__(
        self,
        llm: LLMBackend | None = None,
        max_rounds: int = MAX_ROUNDS,
    ):
        super().__init__(llm=llm)
        self.max_rounds = max_rounds
        self._sys_prompt = build_system_prompt(SYSTEM_PROMPT, DEV_OPS, BUSINESS_OPS)

    def propose(self, plan: dict, context: str = "") -> list[DebatePlan]:
        """Generate alternative proposals for a plan.

        Args:
            plan: The uncertain ActionPlan as a dict.
            context: Additional project context.

        Returns:
            List of DebatePlan proposals from different perspectives.
        """
        prompt = PROPOSE_PROMPT.format(
            plan_json=json.dumps(plan, indent=2),
            context=context or "(no additional context)",
        )
        data = self._llm_query_json(self._sys_prompt, prompt)
        return [DebatePlan.from_dict(p) for p in data.get("proposals", [])]

    def critique(
        self,
        proposals: list[DebatePlan],
        context: str,
        previous_critiques: list[Critique],
        round_num: int,
    ) -> tuple[list[Critique], bool, str, str]:
        """Critique proposals and check for convergence.

        Returns:
            Tuple of (critiques, converged, winning_approach, synthesis).
        """
        prompt = CRITIQUE_PROMPT.format(
            proposals_json=json.dumps([p.to_dict() for p in proposals], indent=2),
            context=context or "(no additional context)",
            previous_critiques=(
                json.dumps([c.to_dict() for c in previous_critiques], indent=2)
                if previous_critiques else "(first round)"
            ),
            round=round_num,
            max_rounds=self.max_rounds,
        )
        data = self._llm_query_json(self._sys_prompt, prompt)
        critiques = [Critique.from_dict(c) for c in data.get("critiques", [])]
        converged = data.get("converged", False)
        winning = data.get("winning_approach", "")
        synthesis = data.get("synthesis", "")
        return critiques, converged, winning, synthesis

    def synthesize(
        self,
        proposals: list[DebatePlan],
        critiques: list[Critique],
        winning_approach: str,
        plan: dict,
    ) -> tuple[dict, str]:
        """Synthesize debate into an improved plan.

        Returns:
            Tuple of (improved_plan_dict, synthesis_text).
        """
        prompt = SYNTHESIZE_PROMPT.format(
            proposals_json=json.dumps([p.to_dict() for p in proposals], indent=2),
            critiques_json=json.dumps([c.to_dict() for c in critiques], indent=2),
            winning_approach=winning_approach or "No clear winner — synthesize best ideas",
            plan_json=json.dumps(plan, indent=2),
        )
        data = self._llm_query_json(self._sys_prompt, prompt)
        return data.get("improved_plan", {}), data.get("synthesis", "")

    def debate(self, plan: dict, context: str = "") -> DebateOutcome:
        """Run the full debate cycle: propose → critique → synthesize.

        Args:
            plan: The uncertain ActionPlan as a dict.
            context: Additional project context.

        Returns:
            DebateOutcome with the improved plan and debate history.
        """
        # Step 1: Generate proposals
        proposals = self.propose(plan, context)
        all_critiques: list[Critique] = []
        winning_approach = ""
        synthesis = ""
        converged = False

        # Step 2: Critique rounds
        for round_num in range(1, self.max_rounds + 1):
            critiques, converged, winning_approach, synthesis = self.critique(
                proposals, context, all_critiques, round_num
            )
            all_critiques.extend(critiques)
            if converged:
                break

        # Step 3: Synthesize
        improved_plan, final_synthesis = self.synthesize(
            proposals, all_critiques, winning_approach, plan
        )

        return DebateOutcome(
            proposals=proposals,
            critiques=all_critiques,
            winning_approach=winning_approach,
            synthesis=final_synthesis or synthesis,
            improved_plan=improved_plan,
            rounds_used=round_num if converged else self.max_rounds,
            converged=converged,
        )
