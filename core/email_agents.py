from agents import Agent, Runner
import asyncio
from pydantic import BaseModel


class EmailResult(BaseModel):
    subject: str
    body: str
    angle: str
    score: float


class EvaluatorResult(BaseModel):
    best_index: int
    reason: str


def create_email_agents(user_context: dict, pdf_context: str = ""):

    pdf_section = f"""
ADDITIONAL CONTEXT FROM UPLOADED DOCUMENT:
{pdf_context}
Use this context to make emails more specific and relevant.
""" if pdf_context else ""

    base = f"""
You write cold sales emails on behalf of {user_context['sender_name']}
from {user_context['company']}.

Product: {user_context['product']}
Value proposition: {user_context['value_prop']}
Tone: {user_context.get('tone', 'professional')}
{pdf_section}

STRICT RULES:
- ALWAYS start with "Hi " followed by the recipient's actual first name from the lead details
- NEVER write placeholder text like [First Name] or [Name] or [Company Name] — always use the actual values provided
- Second line references their specific role and company by name
- Third line connects their industry pain point to our solution
- Keep email under 150 words
- NEVER use "I hope this email finds you well"
- NEVER start with a generic industry statement
- End with ONE simple question as call to action
- Sign off with "Best regards, {user_context['sender_name']}"
- Score your own email honestly from 1-10
"""

    agent1 = Agent(
        name="PainPoint Agent",
        instructions=base + """
YOUR ANGLE: Pain Point
After greeting, immediately identify the specific pain
this person faces in their role. Make them feel understood.
Then position the product as the exact solution to that pain.
""",
        output_type=EmailResult,
        model="gpt-4o-mini"
    )

    agent2 = Agent(
        name="Opportunity Agent",
        instructions=base + """
YOUR ANGLE: Opportunity
After greeting, highlight a specific growth opportunity
relevant to their role and company right now.
Show how acting now with our product gives them an edge.
""",
        output_type=EmailResult,
        model="gpt-4o-mini"
    )

    agent3 = Agent(
        name="SocialProof Agent",
        instructions=base + """
YOUR ANGLE: Social Proof
After greeting, reference what similar people in the same
role and industry have achieved using the product.
Make them feel peers are already benefiting.
""",
        output_type=EmailResult,
        model="gpt-4o-mini"
    )

    return agent1, agent2, agent3


def create_evaluator_agent() -> Agent:
    return Agent(
        name="Email Evaluator",
        instructions="""
You are an expert cold email evaluator. You receive 3 different
cold sales emails written for the same lead and pick the best one.

Evaluate each on:
1. Subject line strength
2. Opening hook after greeting
3. Personalization to this specific person
4. Value clarity
5. Call to action simplicity
6. Tone match to lead seniority and industry

Return the index (0, 1, or 2) of the best email.
Be decisive — always pick one clear winner.
""",
        output_type=EvaluatorResult,
        model="gpt-4o-mini"
    )


async def evaluate_emails(emails: list, lead_info: str) -> int:
    if len(emails) == 1:
        return 0

    evaluator = create_evaluator_agent()

    email_texts = ""
    for i, email in enumerate(emails):
        email_texts += f"\nEmail {i}:\nSubject: {email.subject}\nBody: {email.body}\n---"

    eval_input = f"Lead details:\n{lead_info}\n{email_texts}\nWhich email is most likely to get a response?"

    try:
        result = await Runner.run(evaluator, eval_input)
        idx = result.final_output.best_index
        return min(idx, len(emails) - 1)
    except Exception as e:
        print(f"Evaluator failed: {e}")
        return max(range(len(emails)), key=lambda i: emails[i].score)


async def write_high_email(lead: dict, user_context: dict, pdf_context: str = "") -> dict:
    agent1, agent2, agent3 = create_email_agents(user_context, pdf_context)

    first_name = lead.get('First Name', 'there')
    lead_info = f"""
First Name: {first_name}
Last Name: {lead.get('Last Name', '')}
Job Title: {lead.get('Job Title', 'Professional')}
Company: {lead.get('Company', '')}
Industry: {lead.get('Industry', '')}
Company Size: {lead.get('Employee Range', '')}
Country: {lead.get('Country', '')}
Lead Source: {lead.get('Lead Source', '')}

MUST start with "Hi {first_name}," and reference their role at {lead.get('Company', 'their company')}.
"""

    results = await asyncio.gather(
        Runner.run(agent1, lead_info),
        Runner.run(agent2, lead_info),
        Runner.run(agent3, lead_info),
        return_exceptions=True
    )

    emails = []
    angles = ["pain_point", "opportunity", "social_proof"]
    used_angles = []

    for i, r in enumerate(results):
        if isinstance(r, Exception):
            print(f"Agent {i+1} failed: {r}")
            continue
        emails.append(r.final_output)
        used_angles.append(angles[i])

    if not emails:
        return {**lead, "subject": "Quick note", "body": "Error generating email", "winning_angle": "none", "llm_scores": []}

    best_idx = await evaluate_emails(emails, lead_info)
    best = emails[best_idx]

    return {
        **lead,
        "subject": best.subject,
        "body": best.body,
        "winning_angle": used_angles[best_idx],
        "llm_scores": [{"angle": used_angles[i], "score": emails[i].score} for i in range(len(emails))]
    }


async def write_bulk_email(segment_key: str, leads: list, user_context: dict, pdf_context: str = "") -> dict:
    agent1, agent2, agent3 = create_email_agents(user_context, pdf_context)

    role, industry = segment_key.split(" | ") if " | " in segment_key else (segment_key, "")

    segment_info = f"""
Write a cold email for this segment:
Role: {role}
Industry: {industry}
Segment size: {len(leads)}

Start with "Hi there," — this goes to multiple people.
Reference role and industry specifically.
"""

    results = await asyncio.gather(
        Runner.run(agent1, segment_info),
        Runner.run(agent2, segment_info),
        Runner.run(agent3, segment_info),
        return_exceptions=True
    )

    emails = []
    angles = ["pain_point", "opportunity", "social_proof"]
    used_angles = []

    for i, r in enumerate(results):
        if isinstance(r, Exception):
            continue
        emails.append(r.final_output)
        used_angles.append(angles[i])

    if not emails:
        return {"segment": segment_key, "leads": leads, "subject": "Quick note", "body": "Error generating email", "winning_angle": "none", "llm_scores": []}

    best_idx = await evaluate_emails(emails, segment_info)
    best = emails[best_idx]

    return {
        "segment": segment_key,
        "leads": leads,
        "subject": best.subject,
        "body": best.body,
        "winning_angle": used_angles[best_idx],
        "llm_scores": [{"angle": used_angles[i], "score": emails[i].score} for i in range(len(emails))]
    }