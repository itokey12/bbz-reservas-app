from datetime import date, timedelta, datetime

from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from app.scraper import run_tenis, run_churras

app = FastAPI()
templates = Jinja2Templates(directory="app/templates")


# ----------------- Utilitário de datas -----------------


def _parse_period(start_str: str | None, end_str: str | None):
    """
    Converte strings YYYY-MM-DD em datas.
    Se vierem em branco, usa hoje e hoje+14.
    Faz validações básicas (end >= start, max 45 dias).
    Devolve (start_iso, end_iso, msg_erro).
    """
    today = date.today()

    if start_str:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
    else:
        start = today

    if end_str:
        end = datetime.strptime(end_str, "%Y-%m-%d").date()
    else:
        end = today + timedelta(days=14)

    if end < start:
        return None, None, "Data final não pode ser anterior à inicial."

    if (end - start).days > 45:
        return None, None, "Período muito longo. Máximo permitido: 45 dias."

    # devolve novamente como string YYYY-MM-DD para passar pro scraper
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"), None


# ----------------- Rotas -----------------


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """
    Tela inicial: formulário com usuário, senha, datas e tipo de recurso.
    """
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            # valores default do formulário
            "default_start": date.today().strftime("%Y-%m-%d"),
            "default_end": (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
            "default_tipo": "tenis",
            "erro": None,
        },
    )


@app.post("/run", response_class=HTMLResponse)
async def run_busca(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    tipo_recurso: str = Form("tenis"),  # "tenis" ou "churras"
    start_date: str | None = Form(None),
    end_date: str | None = Form(None),
):
    """
    Recebe o formulário, valida datas, chama o scraper HTTP
    e devolve o result.html já com os dados.
    """
    start_iso, end_iso, err = _parse_period(start_date, end_date)

    if err:
        # Volta para a tela inicial mostrando o erro
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "default_start": start_date or date.today().strftime("%Y-%m-%d"),
                "default_end": end_date
                or (date.today() + timedelta(days=14)).strftime("%Y-%m-%d"),
                "default_tipo": tipo_recurso,
                "erro": err,
            },
        )

    # Chama o scraper correto
    if tipo_recurso == "churras":
        contexto = run_churras(start_iso, end_iso, username, password)
    else:
        # default: tênis
        contexto = run_tenis(start_iso, end_iso, username, password)

    # Inclui metadados para o template
    contexto |= {
        "tipo_recurso": tipo_recurso,
        "start_iso": start_iso,
        "end_iso": end_iso,
    }

    return templates.TemplateResponse(
        "result.html",
        {
            "request": request,
            "context": contexto,
        },
    )


# opcional: para o healthcheck do Render não dar 405 em HEAD /
@app.head("/")
async def head_root():
    return PlainTextResponse("ok")
