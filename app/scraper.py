from datetime import datetime, timedelta
from app.scraper_http import (
    login,
    RECURSOS,
    buscar_tenis_dia,
    buscar_churrasqueira_dia,
    carregar_confirmacao,
    confirmar_reserva,
)

# -----------------------------------
# UTILITÁRIO: converte "YYYY-MM-DD"
# -----------------------------------
def parse_date(d):
    return datetime.strptime(d, "%Y-%m-%d").date()


# ================================
#   TÊNIS — 3 quadras, com horas
# ================================
def run_tenis(start_date: str, end_date: str, username: str, password: str):
    """
    Faz login, coleta horários das quadras 1/2/3 do período informado
    e retorna um dicionário pronto para usar no template result.html
    """
    start = parse_date(start_date)
    end = parse_date(end_date)

    session = login(username, password)

    resultados = []  # lista de { "data": d, "quadras": {1:[],2:[],3:[]} }

    d = start
    while d <= end:
        dia_info = {
            "data": d.strftime("%d/%m/%Y"),
            "quadras": {
                1: [],
                2: [],
                3: [],
            }
        }

        # Buscar 3 quadras
        q1 = buscar_tenis_dia(session, RECURSOS["tenis_1"], d)
        q2 = buscar_tenis_dia(session, RECURSOS["tenis_2"], d)
        q3 = buscar_tenis_dia(session, RECURSOS["tenis_3"], d)

        dia_info["quadras"][1] = q1
        dia_info["quadras"][2] = q2
        dia_info["quadras"][3] = q3

        resultados.append(dia_info)
        d += timedelta(days=1)

    return {
        "tipo": "tenis",
        "resultados": resultados,
    }


# ====================================
#   CHURRASQUEIRA — 3 espaços, 1 linha
# ====================================
def run_churras(start_date: str, end_date: str, username: str, password: str):
    """
    Busca disponibilidade das churrasqueiras 1/2/3 por dia (apenas 1 reserva/dia).
    """
    start = parse_date(start_date)
    end = parse_date(end_date)

    session = login(username, password)

    resultados = []   # [{data, churrasqueiras: {1: {...}, 2:{...}, 3:{...}}]

    d = start
    while d <= end:
        dia_info = {
            "data": d.strftime("%d/%m/%Y"),
            "churrasqueiras": {
                1: None,
                2: None,
                3: None,
            }
        }

        c1 = buscar_churrasqueira_dia(session, RECURSOS["ch_1"], d)
        c2 = buscar_churrasqueira_dia(session, RECURSOS["ch_2"], d)
        c3 = buscar_churrasqueira_dia(session, RECURSOS["ch_3"], d)

        dia_info["churrasqueiras"][1] = c1
        dia_info["churrasqueiras"][2] = c2
        dia_info["churrasqueiras"][3] = c3

        resultados.append(dia_info)
        d += timedelta(days=1)

    return {
        "tipo": "churras",
        "resultados": resultados,
    }


# ====================================
#    RESERVA (2 etapas)
# ====================================

def etapa_confirmacao(username, password, reserva_url: str):
    """
    1) Login  
    2) Carrega tela de condição  
    3) Retorna action_url + hidden fields, para permitir POST final  
    """
    session = login(username, password)
    action, dados = carregar_confirmacao(session, reserva_url)
    return {"action": action, "hidden": dados}


def etapa_concordo(username, password, action_url, dados):
    """
    Envia o POST da etapa final (botão CONCORDO)
    """
    session = login(username, password)
    html = confirmar_reserva(session, action_url, dados)
    return html
