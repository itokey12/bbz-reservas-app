from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from datetime import datetime
from app.scraper_http import buscar_periodo, RECURSOS

app = FastAPI()

app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ===============================================================
# HOME — FORMULÁRIO
# ===============================================================
@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ===============================================================
# RUN — PROCESSA BUSCA
# ===============================================================
@app.post("/run", response_class=HTMLResponse)
async def run_busca(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    tipo: str = Form(...),          # "tenis" ou "churras"
    recurso: str = Form(...),       # tenis_1, tenis_2, ch_1, ch_2 ...
    start_date: str = Form(...),
    end_date: str = Form(...),
):

    try:
        start = datetime.strptime(start_date, "%Y-%m-%d").date()
        end = datetime.strptime(end_date, "%Y-%m-%d").date()

        # EXECUTA SCRAPER
        resultado = buscar_periodo(
            username=username,
            password=password,
            tipo=tipo,
            recurso=RECURSOS[recurso],
            start=start,
            end=end
        )

        return templates.TemplateResponse(
            "result.html",
            {
                "request": request,
                "resultado": resultado,
                "tipo": tipo,
                "recurso": recurso,
                "start": start,
                "end": end,
            }
        )

    except Exception as e:
        return HTMLResponse(
            f"<h2>Erro ao processar:</h2><pre>{e}</pre>",
            status_code=500
        )
