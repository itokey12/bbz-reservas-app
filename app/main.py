from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
import uuid
from app.scraper import run_scraping

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

JOBS = {}

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def _do_job(job_id: str, username: str, password: str):
    try:
        html = run_scraping(username, password)
        JOBS[job_id] = {"status": "ok", "html": html, "error": None}
    except Exception as e:
        JOBS[job_id] = {"status": "error", "html": None, "error": str(e)}

@app.post("/run", response_class=HTMLResponse)
def run(request: Request, background_tasks: BackgroundTasks,
        username: str = Form(...), password: str = Form(...)):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "pending", "html": None, "error": None}
    background_tasks.add_task(_do_job, job_id, username, password)
    return RedirectResponse(url=f"/result/{job_id}", status_code=303)

@app.get("/result/{job_id}", response_class=HTMLResponse)
def result(request: Request, job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return PlainTextResponse("Job não encontrado.", status_code=404)
    return templates.TemplateResponse("result.html", {"request": request, "job_id": job_id, "job": job})

@app.get("/api/job/{job_id}", response_class=HTMLResponse)
def api_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        return PlainTextResponse("Job não encontrado.", status_code=404)
    if job["status"] == "ok":
        return HTMLResponse(job["html"])
    elif job["status"] == "error":
        return HTMLResponse(f"<h3>Erro:</h3><pre>{job['error']}</pre>", status_code=500)
    else:
        return HTMLResponse("<em>Processando…</em>")
