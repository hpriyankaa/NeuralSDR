from agents import Agent, Runner
from pydantic import BaseModel
import asyncio


# ── Structured output for each lead score ────────────────────────
class LeadScore(BaseModel):
    score: float     # 1-10
    tier: str        # HIGH / BULK / SKIP
    reason: str      # specific reason based on campaign intent


# ── Create scoring agent ──────────────────────────────────────────
def create_scoring_agent(user_context: dict) -> Agent:

    instructions = f"""
You are an intelligent lead scoring agent.

Your only job is to read the campaign details below and decide
how relevant each lead is to THAT specific campaign.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CAMPAIGN DETAILS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Company:        {user_context['company']}
Product:        {user_context['product']}
Value Prop:     {user_context.get('value_prop', '')}
Sender:         {user_context['sender_name']}

Campaign Intent (READ THIS CAREFULLY):
{user_context['intent']}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HOW TO SCORE:

Before scoring any lead ask yourself:
"Is this person someone who would BENEFIT from or BUY this product
 based on what the campaign is trying to achieve?"

Score 1-10 based on that answer alone.

TIER RULES:
→ HIGH (7-10)
  This person is exactly who the campaign is targeting.
  They would directly benefit from or purchase this product.
  Send them a fully personalized email.

→ BULK (4-6)
  This person is somewhat relevant.
  They might benefit indirectly or could refer others.
  Send them a segment-level email.

→ SKIP (1-3)
  This person has no meaningful connection to this campaign.
  Emailing them would be a waste.
  Do not email them.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CRITICAL RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. FORGET generic B2B rules.
   CTOs are NOT always high value.
   Interns are NOT always low value.
   It depends entirely on the campaign intent above.

2. REAL EXAMPLES of how intent changes scoring:

   Campaign: "SOC2 compliance tool for tech companies"
   → CTO at Fintech = HIGH (needs compliance)
   → Intern at Restaurant = SKIP (irrelevant)

   Campaign: "Career upskilling platform for people switching to tech"
   → Student = HIGH (exactly the target)
   → Receptionist = HIGH (wants career switch)
   → CTO = SKIP (already in tech, not looking to switch)
   → Intern = HIGH (early career, wants to grow)

   Campaign: "HR hiring tool for companies"
   → HR Manager = HIGH (direct buyer)
   → CTO = BULK (influences hiring decisions)
   → Student = SKIP (not a buyer)

   Campaign: "Food delivery app for restaurants"
   → Restaurant Owner = HIGH (direct customer)
   → CTO at SaaS = SKIP (irrelevant)
   → Operations Manager at F&B = HIGH (decision maker)

3. ALWAYS re-read the campaign intent before scoring.
   Do not use memory from previous leads.
   Each lead is scored fresh against the intent.

4. Give a SPECIFIC reason that references the campaign.
   BAD:  "This person is a CTO so they are high value"
   GOOD: "CTO at a 200 person Fintech — exactly the profile
          that needs SOC2 compliance tooling"

   BAD:  "Student has no purchasing power"
   GOOD: "Student looking to grow their career — exactly the
          audience SkillUp targets for tech upskilling"
"""

    return Agent(
        name="Lead Scorer",
        instructions=instructions,
        output_type=LeadScore,
        model="gpt-4o-mini"
    )


# ── Score a single lead ───────────────────────────────────────────
async def score_lead(agent: Agent, lead: dict) -> dict:
    lead_info = f"""
Score this lead against the campaign intent:

Name:           {lead.get('First Name', '')} {lead.get('Last Name', '')}
Job Title:      {lead.get('Job Title', 'Unknown')}
Company:        {lead.get('Company', 'Unknown')}
Industry:       {lead.get('Industry', 'Unknown')}
Employee Range: {lead.get('Employee Range', 'Unknown')}
Country:        {lead.get('Country', 'Unknown')}
Lead Source:    {lead.get('Lead Source', 'Unknown')}

Remember: Score based purely on the campaign intent you were given.
"""
    result = await Runner.run(agent, lead_info)
    score_data = result.final_output

    return {
        **lead,
        "score": score_data.score,
        "tier": score_data.tier,
        "reason": score_data.reason
    }


# ── Score all leads concurrently ─────────────────────────────────
async def score_all_leads(leads: list, user_context: dict) -> list:
    agent = create_scoring_agent(user_context)
    tasks = [score_lead(agent, lead) for lead in leads]
    scored = await asyncio.gather(*tasks)
    return list(scored)