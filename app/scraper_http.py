import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta

BASE = "https://icondominio.webware.com.br"

# --------------------------
# RECURSOS (tênis e churras)
# --------------------------
RECURSOS = {
    "tenis_1": "EF3C995968241BD918646D3859E8532B",
    "tenis_2": "8D71C6E07E6E7E8B799AD8C8070067E8",
    "tenis_3": "057F54C28308AE8A9914A3B12A42983E",

    "ch_1": "E288DDCA32C8FFF3F88AE4740E8444DB",
    "ch_2": "18BA0F8911674F27C5072E67DF160648",
    "ch_3": "4092AEB140B1856AF190B39176DD1E01",
}

# --------------------------
# LOGIN
# --------------------------
def login(username: str, password: str) -> requests.Session:
    s = requests.Session()

    # 1) Abre a tela inicial (carrega cookies ASP.NET)
    r = s.get("https://bbz.com.br/area-do-cliente/")
    r.raise_for_status()

    # 2) Envia o form de login da BBZ
    payload = {
        "usuario": username,
        "senha": password,
        "termo": "on",
    }

    r = s.post("https://bbz.com.br/area-do-cliente/", data=payload)
    r.raise_for_status()

    return s

# ------------------------------------
# BUSCAR HORÁRIOS — TÊNIS (com horas)
# ------------------------------------
def buscar_tenis_dia(session, recurso, dia: date):
    params = {
        "data": dia.strftime("%d-%m-%Y"),
        "recurso": recurso,
        "unidade": "",
    }

    r = session.get(f"{BASE}/Reservas/DataDisponiveis", params=params)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    linhas = []

    for tr in soup.select("table tbody tr"):
        tds = tr.find_all("td")
        if len(tds) < 3:
            continue

        hora = tds[0].get_text(strip=True)
        status = tds[1].get_text(strip=True)
        botao = tds[2].find("button")

        reserva_url = None
        if botao and botao.has_attr("onclick"):
            oc = botao["onclick"]
            start = oc.find("('") + 2
            end = oc.find("')", start)
            path = oc[start:end]
            reserva_url = BASE + path

        linhas.append({
            "hora": hora,
            "status": status,
            "reserva_url": reserva_url,
        })

    return linhas

# -------------------------------------------------
# BUSCAR CHURRASQUEIRA — sem horas, só 1 reserva
# -------------------------------------------------
def buscar_churrasqueira_dia(session, recurso, dia: date):
    """
    A churrasqueira retorna uma tabela parecida,
    mas normalmente só tem 1 linha por dia.
    """
    params = {
        "data": dia.strftime("%d-%m-%Y"),
        "recurso": recurso,
        "unidade": "",
    }

    r = session.get(f"{BASE}/Reservas/DataDisponiveis", params=params)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")

    tr = soup.select_one("table tbody tr")
    if not tr:
        return None

    tds = tr.find_all("td")
    status = tds[1].get_text(strip=True)
    botao = tds[2].find("button")

    reserva_url = None
    if botao and botao.has_attr("onclick"):
        oc = botao["onclick"]
        start = oc.find("('") + 2
        end = oc.find("')", start)
        path = oc[start:end]
        reserva_url = BASE + path

    return {
        "status": status,
        "reserva_url": reserva_url,
    }

# -----------------------------------------
# PÁGINA DE CONFIRMAÇÃO (antes do Concordo)
# -----------------------------------------
def carregar_confirmacao(session, reserva_url):
    r = session.get(reserva_url)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")

    if form is None:
        raise RuntimeError("Não foi possível localizar o formulário de confirmação.")

    action = form.get("action")
    if not action.startswith("http"):
        action = BASE + action.lstrip("/")

    # hidden fields
    dados = {}
    for inp in form.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        value = inp.get("value", "")
        if name:
            dados[name] = value

    return action, dados

# -------------------------
# REALIZAR RESERVA FINAL
# -------------------------
def confirmar_reserva(session, action_url, dados):
    r = session.post(action_url, data=dados)
    r.raise_for_status()
    return r.text
