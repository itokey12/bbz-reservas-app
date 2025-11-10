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
        username: str = Form(...), password: str = Form(...),
        start_date: str = Form(None), end_date: str = Form(None)):
    import datetime as dt
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "pending", "html": None, "error": None}

    # Parse e validação leve
    start, end = None, None
    try:
        if start_date:
            start = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
        if end_date:
            end = dt.datetime.strptime(end_date, "%Y-%m-%d").date()
        if start and end and end < start:
            raise ValueError("Data final anterior à inicial.")
        # limites razoáveis de janela (para não travar headless)
        ref_start = start or dt.date.today()
        ref_end = end or (dt.date.today() + dt.timedelta(days=14))
        max_span = 45  # dias
        if (ref_end - ref_start).days > max_span:
            raise ValueError(f"Período muito longo. Máximo permitido: {max_span} dias.")
    except Exception as e:
        JOBS[job_id] = {"status": "error", "html": None, "error": f"Datas inválidas: {e}"}
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)

    def _do_job(job_id: str, username: str, password: str, start, end):
        from app.scraper import run_scraping
        try:
            html = run_scraping(username, password, start_date=start, end_date=end)
            JOBS[job_id] = {"status": "ok", "html": html, "error": None}
        except Exception as e:
            JOBS[job_id] = {"status": "error", "html": None, "error": str(e)}

    background_tasks.add_task(_do_job, job_id, username, password, start, end)
    return RedirectResponse(url=f"/result/{job_id}", status_code=303)
@app.post("/run_fast", response_class=HTMLResponse)
def run_fast(request: Request, background_tasks: BackgroundTasks,
             username: str = Form(...), password: str = Form(...),
             start_date: str = Form(None), end_date: str = Form(None)):
    import datetime as dt, uuid
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "pending", "html": None, "error": None}

    # parse datas – mesmo critério do /run
    start = dt.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else None
    end   = dt.datetime.strptime(end_date, "%Y-%m-%d").date()   if end_date   else None
    if start and end and end < start:
        JOBS[job_id] = {"status":"error","html":None,"error":"Data final anterior à inicial."}
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)
    ref_start = start or dt.date.today()
    ref_end   = end or (dt.date.today() + dt.timedelta(days=14))
    if (ref_end - ref_start).days > 45:  # mesmo limite do /run
        JOBS[job_id] = {"status":"error","html":None,"error":"Período muito longo. Máximo permitido: 45 dias."}
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)

    def _do_job_fast(job_id: str, username: str, password: str, start, end):
        from app.scraper import run_scraping_fast
        try:
            html = run_scraping_fast(username, password, start_date=start, end_date=end)
            JOBS[job_id] = {"status":"ok","html":html,"error":None}
        except Exception as e:
            JOBS[job_id] = {"status":"error","html":None,"error":str(e)}

    background_tasks.add_task(_do_job_fast, job_id, username, password, start, end)
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
