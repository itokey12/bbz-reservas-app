import requests
from bs4 import BeautifulSoup
from datetime import date, timedelta

BASE_WW = "https://icondominio.webware.com.br"
BASE_SV = "https://servc9.webware.com.br"
BASE_BBZ = "https://bbz.com.br"

# -------------------------------------------------------------
# RECURSOS — TÊNIS E CHURRASQUEIRA
# -------------------------------------------------------------
RECURSOS = {
    "tenis_1": "EF3C995968241BD918646D3859E8532B",
    "tenis_2": "8D71C6E07E6E7E8B799AD8C8070067E8",
    "tenis_3": "057F54C28308AE8A9914A3B12A42983E",

    "ch_1": "E288DDCA32C8FFF3F88AE4740E8444DB",
    "ch_2": "18BA0F8911674F27C5072E67DF160648",
    "ch_3": "4092AEB140B1856AF190B39176DD1E01",
}

# O token `c=` fixo (confirmado por você)
TOKEN_C = "52207487"


# -------------------------------------------------------------
# LOGIN BBZ → VALIDADOR → SERVC9 → COOKIES PRONTOS
# -------------------------------------------------------------
def login_full(username: str, password: str) -> requests.Session:
    s = requests.Session()

    # 1) LOGIN NO BBZ
    r = s.get(f"{BASE_BBZ}/area-do-cliente/")
    r.raise_for_status()

    payload = {
        "usuario": username,
        "senha": password,
        "termo": "on",
    }

    r = s.post(f"{BASE_BBZ}/area-do-cliente/", data=payload, allow_redirects=True)
    r.raise_for_status()

    # Deve redirecionar para algo como: validador.webware.com.br/ValidarLogin...
    # O session já segue automaticamente.

    # 2) LOGIN NO SERVIDOR WEBARE (servc9)
    # A página Sucesso do validador redireciona para:
    # https://servc9.webware.com.br/bin/login.asp
    # Vamos garantir chamando manualmente:

    r = s.get(f"{BASE_SV}/bin/login.asp", allow_redirects=True)
    r.raise_for_status()

    # 3) servico.asp (necessário para ativar a sessão)
    r = s.get(f"{BASE_SV}/bin/servico.asp?c={TOKEN_C}", allow_redirects=True)
    r.raise_for_status()

    # 4) defaultskin.asp
    r = s.get(f"{BASE_SV}/bin/skin/defaultskin.asp", allow_redirects=True)
    r.raise_for_status()

    # 5) aInicioSkin.asp (painel principal — completa sessão)
    r = s.get(f"{BASE_SV}/bin/skin/aInicioSkin.asp", allow_redirects=True)
    r.raise_for_status()

    return s


# -------------------------------------------------------------
# BUSCAR HORÁRIOS — TÊNIS
# -------------------------------------------------------------
def buscar_tenis_dia(session: requests.Session, recurso: str, dia: date):
    params = {
        "data": dia.strftime("%d-%m-%Y"),
        "recurso": recurso,
        "unidade": "",
    }

    url = f"{BASE_WW}/Reservas/DataDisponiveis"
    r = session.get(url, params=params)
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
            reserva_url = BASE_WW + path

        linhas.append({
            "hora": hora,
            "status": status,
            "reserva_url": reserva_url
        })

    return linhas


# -------------------------------------------------------------
# BUSCAR CHURRASQUEIRA — UMA RESERVA POR DIA
# -------------------------------------------------------------
def buscar_churras_dia(session: requests.Session, recurso: str, dia: date):
    params = {
        "data": dia.strftime("%d-%m-%Y"),
        "recurso": recurso,
        "unidade": "",
    }

    r = session.get(f"{BASE_WW}/Reservas/DataDisponiveis", params=params)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    tr = soup.select_one("table tbody tr")
    if not tr:
        return None

    tds = tr.find_all("td")
    if len(tds) < 3:
        return None

    status = tds[1].get_text(strip=True)

    botao = tds[2].find("button")
    reserva_url = None
    if botao and botao.has_attr("onclick"):
        oc = botao["onclick"]
        start = oc.find("('") + 2
        end = oc.find("')", start)
        path = oc[start:end]
        reserva_url = BASE_WW + path

    return {
        "status": status,
        "reserva_url": reserva_url,
    }


# -------------------------------------------------------------
# CARREGAR PÁGINA DE CONFIRMAÇÃO (ANTES DO “CONCORDO”)
# -------------------------------------------------------------
def carregar_confirmacao(session: requests.Session, url_reserva: str):
    r = session.get(url_reserva)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    form = soup.find("form")
    if not form:
        raise RuntimeError("Formulário da página de confirmação não encontrado.")

    action = form.get("action")
    if not action.startswith("http"):
        action = BASE_WW + action

    dados = {}
    for inp in form.find_all("input", {"type": "hidden"}):
        nome = inp.get("name")
        val = inp.get("value", "")
        if nome:
            dados[nome] = val

    return action, dados


# -------------------------------------------------------------
# ENVIAR O POST FINAL (“CONCORDO”)
# -------------------------------------------------------------
def concluir_reserva(session: requests.Session, url_action: str, dados_hidden: dict):
    r = session.post(url_action, data=dados_hidden)
    r.raise_for_status()

    return r.text


# -------------------------------------------------------------
# FUNÇÕES DE ALTO NÍVEL
# -------------------------------------------------------------
def buscar_periodo(username, password, tipo, recurso, start, end):
    s = login_full(username, password)

    resultados = []
    dia = start
    while dia <= end:
        if tipo == "tenis":
            linhas = buscar_tenis_dia(s, recurso, dia)
        else:
            linhas = buscar_churras_dia(s, recurso, dia)

        resultados.append({
            "data": dia,
            "linhas": linhas
        })

        dia += timedelta(days=1)

    return resultados


def reservar(username, password, reserva_url):
    s = login_full(username, password)

    action, dados = carregar_confirmacao(s, reserva_url)
    html_final = concluir_reserva(s, action, dados)
    return html_final
