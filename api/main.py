from fastapi import FastAPI, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import asyncio
import shutil
import os
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from typing import Optional

from pipeline.runner import run_pipeline

load_dotenv()

app = FastAPI(title="NeuralSDR")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="frontend"), name="static")

latest_results = {}
pipeline_status = {"running": False, "step": "idle", "progress": 0}


@app.get("/")
async def root():
    return FileResponse("frontend/index.html")


@app.get("/api/status")
async def get_status():
    return JSONResponse(content=pipeline_status)


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from PDF using pdfplumber"""
    try:
        import pdfplumber
        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                text += page.extract_text() or ""
        return text[:3000]  # limit to 3000 chars to avoid token overflow
    except ImportError:
        print("pdfplumber not installed — install with: pip install pdfplumber")
        return ""
    except Exception as e:
        print(f"PDF extraction failed: {e}")
        return ""


@app.post("/api/run")
async def run_campaign(
    company: str = Form(...),
    product: str = Form(...),
    intent: str = Form(...),
    sender_name: str = Form(...),
    value_prop: str = Form(...),
    tone: str = Form("professional"),
    csv_file: UploadFile = File(...),
    pdf_file: Optional[UploadFile] = File(None)
):
    global latest_results, pipeline_status

    # Save CSV
    csv_path = "data/temp_upload.csv"
    with open(csv_path, "wb") as f:
        shutil.copyfileobj(csv_file.file, f)

    # Extract PDF text if uploaded
    pdf_context = ""
    if pdf_file and pdf_file.filename:
        pdf_path = "data/temp_upload.pdf"
        with open(pdf_path, "wb") as f:
            shutil.copyfileobj(pdf_file.file, f)
        pdf_context = extract_pdf_text(pdf_path)
        os.remove(pdf_path)
        if pdf_context:
            print(f"PDF extracted: {len(pdf_context)} chars")

    user_context = {
        "company": company,
        "product": product,
        "intent": intent,
        "sender_name": sender_name,
        "value_prop": value_prop,
        "tone": tone
    }

    pipeline_status = {"running": True, "step": "scoring", "progress": 20}
    results = await run_pipeline(csv_path, user_context, pdf_context)
    pipeline_status = {"running": False, "step": "complete", "progress": 100}

    latest_results = results
    if os.path.exists(csv_path):
        os.remove(csv_path)

    return JSONResponse(content=results)


@app.get("/api/results")
async def get_results():
    return JSONResponse(content=latest_results)


@app.post("/api/send-skip")
async def send_skip_emails(data: dict):
    skip_leads = data.get("leads", [])
    subject = data.get("subject", "")
    body = data.get("body", "")

    sent_count = 0
    for lead in skip_leads:
        to = lead.get("Work Email", "")
        if to:
            try:
                sg = sendgrid.SendGridAPIClient(api_key=os.getenv("SENDGRID_API_KEY"))
                from_email = Email(os.getenv("SENDER_EMAIL"))
                content = Content("text/plain", body)
                mail = Mail(from_email, To(to), subject, content).get()
                sg.client.mail.send.post(request_body=mail)
                sent_count += 1
            except Exception as e:
                print(f"Failed: {to} — {e}")

    return {"sent": sent_count}
