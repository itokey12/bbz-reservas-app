import requests
from bs4 import BeautifulSoup
from datetime import date, datetime, timedelta

BASE = "https://icondominio.webware.com.br"

# --------------------------------------------------------
# RECURSOS — TÊNIS & CHURRASQUEIRA
# --------------------------------------------------------
RECURSOS = {
    "tenis_1": "EF3C995968241BD918646D3859E8532B",
    "tenis_2": "8D71C6E07E6E7E8B799AD8C8070067E8",
    "tenis_3": "057F54C28308AE8A9914A3B12A42983E",

    "ch_1": "E288DDCA32C8FFF3F88AE4740E8444DB",
    "ch_2": "18BA0F8911674F27C5072E67DF160648",
    "ch_3": "4092AEB140B1856AF190B39176DD1E01",
}

# =========================================================
# LOGIN
# =========================================================
def login(username: str, password: str) -> requests.Session:
    s = requests.Session()

    # Carrega cookies iniciais
    r = s.get("https://bbz.com.br/area-do-cliente/")
    r.raise_for_status()

    # POST do formulário
    payload = {
        "usuario": username,
        "senha": password,
        "termo": "on",
    }

    r = s.post("https://bbz.com.br/area-do-cliente/", data=payload)
    r.raise_for_status()

    return s

# =========================================================
# BUSCA DE TÊNIS POR DIA
# =========================================================
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
            reserva_url = BASE + oc[start:end]

        linhas.append({
            "hora": hora,
            "status": status,
            "reserva_url": reserva_url,
        })

    return linhas

# =========================================================
# BUSCA DE CHURRASQUEIRA POR DIA (uma linha/dia)
# =========================================================
def buscar_churrasqueira_dia(session, recurso, dia: date):
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
        reserva_url = BASE + oc[start:end]

    return {
        "status": status,
        "reserva_url": reserva_url,
    }

# =========================================================
# PÁGINA DE CONFIRMAÇÃO (ANTES DO "CONCORDO")
# =========================================================
def carregar_confirmacao(session, reserva_url):
    r = session.get(reserva_url)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")

    if not form:
        raise RuntimeError("Formulário de confirmação não encontrado.")

    action = form.get("action")
    if not action.startswith("http"):
        action = BASE + action.lstrip("/")

    dados = {}
    for inp in form.find_all("input", {"type": "hidden"}):
        name = inp.get("name")
        if not name:
            continue
        dados[name] = inp.get("value", "")

    return action, dados

# =========================================================
# EFETIVAR RESERVA (POST FINAL)
# =========================================================
def confirmar_reserva(session, action_url, dados):
    r = session.post(action_url, data=dados)
    r.raise_for_status()
    return r.text

# =========================================================
# FUNÇÃO FINAL — TÊNIS (HTML consolidado)
# =========================================================
def run_tenis(username: str, password: str, start: date, end: date):
    s = login(username, password)

    html = "<h2>Resultados — Quadras de Tênis</h2>"

    dia = start
    while dia <= end:
        html += f"<h3>{dia.strftime('%d/%m/%Y')}</h3>"

        for q in (1, 2, 3):
            recurso = RECURSOS[f"tenis_1" if q == 1 else f"tenis_{q}"]
            slots = buscar_tenis_dia(s, recurso, dia)

            html += f"<h4>Quadra {q}</h4>"
            html += "<table border='1' cellpadding='6'><tr><th>Hora</th><th>Status</th></tr>"

            for sl in slots:
                if sl["reserva_url"]:
                    html += f"<tr><td>{sl['hora']}</td><td><a href='{sl['reserva_url']}' target='_blank'>Disponível</a></td></tr>"
                else:
                    html += f"<tr><td>{sl['hora']}</td><td>{sl['status']}</td></tr>"

            html += "</table><br>"

        dia += timedelta(days=1)

    return html

# =========================================================
# FUNÇÃO FINAL — CHURRASQUEIRA
# =========================================================
def run_churras(username: str, password: str, start: date, end: date):
    s = login(username, password)

    html = "<h2>Resultados — Churrasqueiras</h2>"

    dia = start
    while dia <= end:
        html += f"<h3>{dia.strftime('%d/%m/%Y')}</h3>"

        for ch in (1, 2, 3):
            recurso = RECURSOS[f"ch_{ch}"]
            info = buscar_churrasqueira_dia(s, recurso, dia)

            html += f"<h4>Churrasqueira {ch}</h4>"

            if info is None:
                html += "<p>Nenhum dado encontrado.</p>"
                continue

            if info["reserva_url"]:
                html += f"<p><b>{info['status']}</b> — <a href='{info['reserva_url']}' target='_blank'>Reservar</a></p>"
            else:
                html += f"<p>{info['status']}</p>"

        html += "<br>"
        dia += timedelta(days=1)

    return html
