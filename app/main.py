from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
import uuid, datetime as dt
import traceback

from app.scraper import run_full_parallel, run_fast_parallel

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

JOBS = {}

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

def _parse_dates(start_date: str | None, end_date: str | None):
    start, end = None, None
    if start_date:
        start = dt.datetime.strptime(start_date, "%Y-%m-%d").date()
    if end_date:
        end = dt.datetime.strptime(end_date, "%Y-%m-%d").date()
    if start and end and end < start:
        raise ValueError("Data final anterior à inicial.")
    ref_start = start or dt.date.today()
    ref_end = end or (dt.date.today() + dt.timedelta(days=14))
    max_span = 45
    if (ref_end - ref_start).days > max_span:
        raise ValueError(f"Período muito longo. Máximo permitido: {max_span} dias.")
    return start or ref_start, end or ref_end

@app.post("/run_full_parallel", response_class=HTMLResponse)
def run_full(request: Request, background_tasks: BackgroundTasks,
             username: str = Form(...), password: str = Form(...),
             start_date: str = Form(None), end_date: str = Form(None)):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "pending", "html": None, "error": None}
    try:
        start, end = _parse_dates(start_date, end_date)
    except Exception as e:
        JOBS[job_id] = {"status":"error","html":None,"error":f"Datas inválidas: {e}"}
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)

    def _job():
        try:
            html = run_full_parallel(username, password, start, end)  # ou fast
            JOBS[job_id] = {"status":"ok","html":html,"error":None}
        except Exception as e:
            tb = traceback.format_exc()
            JOBS[job_id] = {"status":"error","html":None,"error":tb}

    background_tasks.add_task(_job)
    return RedirectResponse(url=f"/result/{job_id}", status_code=303)

@app.post("/run_fast_parallel", response_class=HTMLResponse)
def run_fast(request: Request, background_tasks: BackgroundTasks,
             username: str = Form(...), password: str = Form(...),
             start_date: str = Form(None), end_date: str = Form(None)):
    job_id = uuid.uuid4().hex
    JOBS[job_id] = {"status": "pending", "html": None, "error": None}
    try:
        start, end = _parse_dates(start_date, end_date)
    except Exception as e:
        JOBS[job_id] = {"status":"error","html":None,"error":f"Datas inválidas: {e}"}
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)

    def _job():
        try:
            html = run_full_parallel(username, password, start, end)  # ou fast
            JOBS[job_id] = {"status":"ok","html":html,"error":None}
        except Exception as e:
            tb = traceback.format_exc()
            JOBS[job_id] = {"status":"error","html":None,"error":tb}
    
        background_tasks.add_task(_job)
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
        # Em vez de 404, devolva 200 com mensagem legível (evita “loop de erro” no polling)
        return HTMLResponse("<h3>Job não encontrado</h3><p>Talvez o app tenha reiniciado ou a instância mudou. Refaça a busca.</p>")

    if job["status"] == "ok":
        return HTMLResponse(job["html"])

    if job["status"] == "error":
        # Mostra o erro como HTML (status 200) para o usuário ver no /result
        err = job.get("error") or "Erro desconhecido"
        return HTMLResponse(f"<h3>Erro na execução</h3><pre>{err}</pre>")

    # pending
    return HTMLResponse("<em>Processando…</em>")
