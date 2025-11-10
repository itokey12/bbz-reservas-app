from fastapi import FastAPI, Request, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates
import uuid, datetime as dt, sqlite3, traceback, os

from app.scraper import run_full_parallel, run_fast_parallel

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")

# ----------------- Persistência simples de jobs (SQLite) -----------------

DBPATH = os.getenv("JOBS_DB", "/tmp/jobs.db")

def _db():
    conn = sqlite3.connect(DBPATH, check_same_thread=False)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs(
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,    -- pending | ok | error
            html TEXT,
            error TEXT,
            created_at TEXT NOT NULL
        )
    """)
    return conn

def jobs_put(job_id: str, status: str, html: str | None = None, error: str | None = None):
    with _db() as c:
        c.execute(
            "REPLACE INTO jobs(id,status,html,error,created_at) VALUES(?,?,?,?,?)",
            (job_id, status, html, error, dt.datetime.utcnow().isoformat())
        )

def jobs_get(job_id: str):
    with _db() as c:
        r = c.execute("SELECT status, html, error FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not r:
            return None
        return {"status": r[0], "html": r[1], "error": r[2]}

# ----------------- Utilitário de datas -----------------

def _parse_dates(start_date: str | None, end_date: str | None):
    start = dt.datetime.strptime(start_date, "%Y-%m-%d").date() if start_date else dt.date.today()
    end   = dt.datetime.strptime(end_date, "%Y-%m-%d").date()   if end_date   else dt.date.today() + dt.timedelta(days=14)
    if end < start:
        raise ValueError("Data final anterior à inicial.")
    if (end - start).days > 45:
        raise ValueError("Período muito longo. Máximo permitido: 45 dias.")
    return start, end

# ----------------- Rotas -----------------

@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/run_full_parallel", response_class=HTMLResponse)
def run_full(request: Request, background_tasks: BackgroundTasks,
             username: str = Form(...), password: str = Form(...),
             start_date: str = Form(None), end_date: str = Form(None)):
    job_id = uuid.uuid4().hex
    jobs_put(job_id, "pending")
    try:
        start, end = _parse_dates(start_date, end_date)
    except Exception as e:
        jobs_put(job_id, "error", error=str(e))
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)

    def _job():
        try:
            html = run_full_parallel(username, password, start, end)
            jobs_put(job_id, "ok", html=html)
        except Exception:
            jobs_put(job_id, "error", error=traceback.format_exc())

    background_tasks.add_task(_job)
    return RedirectResponse(url=f"/result/{job_id}", status_code=303)

@app.post("/run_fast_parallel", response_class=HTMLResponse)
def run_fast(request: Request, background_tasks: BackgroundTasks,
             username: str = Form(...), password: str = Form(...),
             start_date: str = Form(None), end_date: str = Form(None)):
    job_id = uuid.uuid4().hex
    jobs_put(job_id, "pending")
    try:
        start, end = _parse_dates(start_date, end_date)
    except Exception as e:
        jobs_put(job_id, "error", error=str(e))
        return RedirectResponse(url=f"/result/{job_id}", status_code=303)

    def _job():
        try:
            html = run_fast_parallel(username, password, start, end)
            jobs_put(job_id, "ok", html=html)
        except Exception:
            jobs_put(job_id, "error", error=traceback.format_exc())

    background_tasks.add_task(_job)
    return RedirectResponse(url=f"/result/{job_id}", status_code=303)

@app.get("/result/{job_id}", response_class=HTMLResponse)
def result(request: Request, job_id: str):
    # entrega a página que faz polling
    return templates.TemplateResponse("result.html", {"request": request, "job_id": job_id})

@app.get("/api/job/{job_id}", response_class=HTMLResponse)
def api_job(job_id: str):
    job = jobs_get(job_id)
    if not job:
        # nunca 404 — mostra instrução clara na própria página
        return HTMLResponse("<h3>Job não encontrado</h3><p>A instância pode ter reiniciado. Refaça a busca.</p>")
    if job["status"] == "ok":
        return HTMLResponse(job["html"])
    if job["status"] == "error":
        return HTMLResponse(f"<h3>Erro</h3><pre>{job['error']}</pre>")
    return HTMLResponse("<em>Processando…</em>")

# opcional: para remover 405 do healthcheck HEAD /
@app.head("/")
def head_root():
    return PlainTextResponse("ok")
