import pandas as pd
import asyncio
from core.scoring_agent import score_all_leads
from core.email_agents import write_high_email, write_bulk_email
from core.guardrails import check_campaign_intent
import sendgrid
import os
from sendgrid.helpers.mail import Mail, Email, To, Content


def build_segments(bulk_leads: list) -> dict:
    segments = {}
    for lead in bulk_leads:
        role = lead.get("Job Title", "Unknown")
        industry = lead.get("Industry", "Unknown")
        key = f"{role} | {industry}"
        if key not in segments:
            segments[key] = []
        segments[key].append(lead)
    return segments


def send_email_via_sendgrid(to_email: str, subject: str, body: str) -> bool:
    try:
        sg = sendgrid.SendGridAPIClient(api_key=os.getenv("SENDGRID_API_KEY"))
        from_email = Email(os.getenv("SENDER_EMAIL"))
        to_addr = To(to_email)
        content = Content("text/plain", body)
        mail = Mail(from_email, to_addr, subject, content).get()
        sg.client.mail.send.post(request_body=mail)
        return True
    except Exception as e:
        print(f"Failed to send to {to_email}: {e}")
        return False


async def run_pipeline(csv_path: str, user_context: dict, pdf_context: str = "") -> dict:

    # Step 1 — Guardrail
    print("Checking campaign intent...")
    safety = await check_campaign_intent(user_context["intent"])
    if not safety["safe"]:
        return {"error": f"Campaign blocked: {safety['reason']}", "blocked": True}

    # Step 2 — Load CSV
    print("Loading leads...")
    df = pd.read_csv(csv_path)
    leads = df.fillna("").to_dict(orient="records")
    print(f"Loaded {len(leads)} leads")

    # Step 3 — Score
    print("Scoring leads...")
    scored_leads = await score_all_leads(leads, user_context)

    # Step 4 — Split
    high_leads = [l for l in scored_leads if l["tier"] == "HIGH"]
    bulk_leads = [l for l in scored_leads if l["tier"] == "BULK"]
    skip_leads = [l for l in scored_leads if l["tier"] == "SKIP"]
    print(f"HIGH: {len(high_leads)} | BULK: {len(bulk_leads)} | SKIP: {len(skip_leads)}")

    # Step 5 — Write + send HIGH
    print("Writing HIGH emails...")
    high_tasks = [write_high_email(lead, user_context, pdf_context) for lead in high_leads]
    high_results = await asyncio.gather(*high_tasks, return_exceptions=True)
    high_emails = [r for r in high_results if not isinstance(r, Exception)]

    print("Sending HIGH emails...")
    for email in high_emails:
        to = email.get("Work Email", "")
        if to:
            sent = send_email_via_sendgrid(to, email["subject"], email["body"])
            email["sent"] = sent
            print(f"  {'✅' if sent else '❌'} {to}")

    # Step 6 — Write + send BULK
    print("Writing BULK emails...")
    segments = build_segments(bulk_leads)
    bulk_tasks = [write_bulk_email(k, v, user_context, pdf_context) for k, v in segments.items()]
    bulk_results = await asyncio.gather(*bulk_tasks, return_exceptions=True)
    bulk_emails = [r for r in bulk_results if not isinstance(r, Exception)]

    print("Sending BULK emails...")
    for segment in bulk_emails:
        for lead in segment["leads"]:
            to = lead.get("Work Email", "")
            if to:
                sent = send_email_via_sendgrid(to, segment["subject"], segment["body"])
                lead["sent"] = sent
                print(f"  {'✅' if sent else '❌'} {to}")

    return {
        "blocked": False,
        "total": len(leads),
        "high_count": len(high_leads),
        "bulk_count": len(bulk_leads),
        "skip_count": len(skip_leads),
        "scored_leads": scored_leads,
        "high_emails": high_emails,
        "bulk_emails": bulk_emails,
        "skip_leads": skip_leads,
        "segments": list(segments.keys()),
        "llm_stats": compute_llm_stats(high_emails + bulk_emails)
    }


def compute_llm_stats(all_emails: list) -> dict:
    angle_wins = {"pain_point": 0, "opportunity": 0, "social_proof": 0}
    for email in all_emails:
        angle = email.get("winning_angle", "")
        if angle in angle_wins:
            angle_wins[angle] += 1
    return angle_wins
