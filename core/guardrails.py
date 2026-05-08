from agents import Agent, Runner, input_guardrail, GuardrailFunctionOutput
from pydantic import BaseModel


# ── Guardrail output structure ────────────────────────────────────
class IntentCheck(BaseModel):
    is_harmful: bool
    reason: str


# ── Guardrail agent ───────────────────────────────────────────────
guardrail_agent = Agent(
    name="Intent Checker",
    instructions="""
Check if the user's campaign intent is harmful or inappropriate.

Flag as harmful if the intent:
- Promotes illegal activities
- Is designed to scam or defraud people
- Contains hate speech or targeted harassment
- Is clearly spam with no legitimate value

Do NOT flag:
- Normal sales outreach
- Job postings
- Product announcements
- Event invitations
- Any legitimate business communication
""",
    output_type=IntentCheck,
    model="gpt-4o-mini"
)


# ── Guardrail function ────────────────────────────────────────────
async def check_campaign_intent(intent: str) -> dict:
    """
    Run before starting the pipeline.
    Returns {"safe": True} or {"safe": False, "reason": "..."}
    """
    result = await Runner.run(guardrail_agent, intent)
    check = result.final_output

    if check.is_harmful:
        return {"safe": False, "reason": check.reason}

    return {"safe": True, "reason": "Campaign intent looks legitimate"}
