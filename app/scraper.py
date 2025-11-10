# app/scraper.py
import os, re, time, calendar, unicodedata, contextlib
from datetime import date, timedelta
from typing import List, Tuple

import pandas as pd

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

# ==== Config de URLs já usadas no projeto ====
SITE_URL = os.getenv("SITE_URL", "https://bbz.com.br/area-do-cliente/")
AREA_GERAL = "https://servc9.webware.com.br/bin/sol/aAreaGeral.asp"
MINHA_UNIDADE_RESERVAS = "https://servc9.webware.com.br/bin/aplic/cpMinhaUnidadeReservas.asp"

# ==== Utilitários existentes (mantidos/adaptados) ====

def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def wait_table_refresh(wait: WebDriverWait, driver, prev_html: str, timeout: int = 20):
    try:
        wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "#tabelaDePeriodos tbody"))
        start = time.time()
        while time.time() - start < timeout:
            cur_el = driver.find_element(By.CSS_SELECTOR, "#tabelaDePeriodos tbody")
            cur_html = cur_el.get_attribute("innerHTML")
            if cur_html and cur_html != prev_html:
                return True
            time.sleep(0.15)
    except Exception:
        pass
    return False

def find_first(wait, selectors: List[Tuple[str, str]], must_click=False, driver=None):
    for by, sel in selectors:
        try:
            el = wait.until(EC.element_to_be_clickable((by, sel))) if must_click \
                 else wait.until(EC.presence_of_element_located((by, sel)))
            return el
        except Exception:
            continue
    return None

def try_switch_to_any_frame(driver):
    driver.switch_to.default_content()
    frames = driver.find_elements(By.TAG_NAME, "iframe")
    for fr in frames:
        try:
            driver.switch_to.frame(fr)
            if driver.find_elements(By.XPATH, "//*[contains(translate(.,'RESERVA','reserva'),'reserva')]"):
                return True
            driver.switch_to.default_content()
        except Exception:
            driver.switch_to.default_content()
    return False

def ensure_reservas_list_ready(wait, driver, tries: int = 3) -> int:
    """Está no iframe certo e os links SelectReserva já renderizaram?"""
    for _ in range(tries):
        driver.switch_to.default_content()
        try_switch_to_any_frame(driver)
        try:
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@onclick,'SelectReserva')]")
            ))
        except Exception:
            time.sleep(0.6)
            continue
        itens = list_tenis_links(driver)
        if itens:
            return len(itens)
        time.sleep(0.6)
    return 0

def switch_to_new_window_if_any(driver):
    base = driver.current_window_handle
    time.sleep(0.5)
    for h in driver.window_handles:
        if h != base:
            driver.switch_to.window(h)
            return True
    return False

def list_tenis_links(driver):
    anchors = driver.find_elements(By.XPATH, "//a[contains(@onclick,'SelectReserva')]")
    itens = []
    for a in anchors:
        onclick = a.get_attribute("onclick") or ""
        txt = (a.text or "").strip()
        m = re.search(r"'([^']*QUADRA[^']*)'", onclick, flags=re.I)
        label = m.group(1).strip() if m else (txt or "")
        norm = _strip_accents(label).lower()
        if "quadra de tenis" in norm:
            mnum = re.search(r"(\d+)", norm)
            numero = int(mnum.group(1)) if mnum else None
            itens.append((a, label, numero))
    itens.sort(key=lambda t: (9999 if t[2] is None else t[2], (t[1] or "")))
    return itens

def click_tenis_by_index(driver, idx: int):
    itens = list_tenis_links(driver)
    if not itens:
        raise RuntimeError("Links de QUADRA DE TÊNIS não encontrados.")
    alvo_num = idx + 1
    for el, label, num in itens:
        if num == alvo_num:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
            driver.execute_script("arguments[0].click();", el)
            return
    el = itens[min(idx, len(itens) - 1)][0]
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].click();", el)

# --- calendário ---

_PT_MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6,
    "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12
}

def parse_header_mes_ano(hdr_text: str):
    t = hdr_text.strip().lower()
    parts = t.split()
    if len(parts) >= 2:
        mes_nome = parts[0]; ano = int(parts[-1])
        mes = _PT_MESES.get(mes_nome, 0)
        if mes:
            from datetime import date
            return date(ano, mes, 1)
    m = re.search(r"([A-Za-zçÇáéíóúâêôãõ]+)\s+(\d{4})", hdr_text)
    if m:
        mes = _PT_MESES.get(m.group(1).lower(), 0); ano = int(m.group(2))
        if mes:
            from datetime import date
            return date(ano, mes, 1)
    raise ValueError(f"Não consegui interpretar o cabeçalho do calendário: '{hdr_text}'")

def month_end(d: date) -> date:
    last = calendar.monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)

def get_header_month_start(wait, driver) -> date:
    hdr = wait.until(EC.presence_of_element_located(
        (By.CSS_SELECTOR, ".datepicker-days th.datepicker-switch")
    )).text.strip()
    return parse_header_mes_ano(hdr)

def click_next_month(wait, driver):
    nxt = wait.until(EC.element_to_be_clickable(
        (By.CSS_SELECTOR, ".datepicker-days th.next")
    ))
    driver.execute_script("arguments[0].click();", nxt)
    time.sleep(1.0)

def click_day_in_calendar(wait, driver, target: date):
    while True:
        header_start = get_header_month_start(wait, driver)
        if header_start.year == target.year and header_start.month == target.month:
            break
        if month_end(header_start) < target:
            click_next_month(wait, driver)
        else:
            break
    prev_html = ""
    try:
        prev_html = driver.find_element(By.CSS_SELECTOR, "#tabelaDePeriodos tbody").get_attribute("innerHTML")
    except Exception:
        pass
    day_sel = ".datepicker-days td.day:not(.old):not(.new):not(.disabled):not(.foraPeriodo)"
    days = driver.find_elements(By.CSS_SELECTOR, day_sel)
    for td in days:
        if (td.text or "").strip() == str(target.day):
            driver.execute_script("arguments[0].click();", td)
            wait_table_refresh(wait, driver, prev_html, timeout=20)
            return True
    return False

# --- login/navegação ---

def open_nova_reserva_list(wait, driver):
    driver.get(AREA_GERAL); time.sleep(0.8)
    driver.get(MINHA_UNIDADE_RESERVAS); time.sleep(0.8)
    switch_to_new_window_if_any(driver)
    try_switch_to_any_frame(driver)
    nova = find_first(wait, [
        (By.XPATH, "//*[self::a or self::button][contains(.,'Nova Reserva')]"),
        (By.XPATH, "//a[@href='javascript:void(0);' and contains(.,'Reserva')]"),
    ], must_click=True, driver=driver)
    if nova:
        driver.execute_script("arguments[0].click();", nova); time.sleep(0.8)
        switch_to_new_window_if_any(driver); try_switch_to_any_frame(driver)

def do_login(wait, driver, username: str, password: str):
    driver.get(SITE_URL)
    user_input = wait.until(EC.presence_of_element_located((By.ID, "mem")))
    pass_input = wait.until(EC.presence_of_element_located((By.ID, "pass")))
    user_input.clear(); user_input.send_keys(username)
    pass_input.clear(); pass_input.send_keys(password)
    # marca termos, se tiver
    with contextlib.suppress(Exception):
        try:
            cb = driver.find_element(By.ID, "termo")
            driver.execute_script("if(!arguments[0].checked){arguments[0].click();}", cb)
        except Exception:
            for cb in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
                if cb.is_displayed() and cb.is_enabled():
                    driver.execute_script("if(!arguments[0].checked){arguments[0].click();}", cb)
                    break
    btn = find_first(wait, [
        (By.XPATH, "//button[contains(.,'ENTRAR')]"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//input[@type='submit' or @value='ENTRAR']"),
    ], must_click=True, driver=driver)
    if not btn:
        raise RuntimeError("Botão ENTRAR não encontrado.")
    driver.execute_script("arguments[0].click();", btn)
    with contextlib.suppress(TimeoutException):
        wait.until(lambda d: "webware" in d.current_url or "servc" in d.current_url)

# --- parsing da tabela ---

def parse_period_table(wait, driver, day: date, quadra_nome: str) -> pd.DataFrame:
    wait.until(EC.presence_of_element_located((By.ID, "tabelaDePeriodos")))
    rows = driver.find_elements(By.CSS_SELECTOR, "#tabelaDePeriodos tbody tr")
    out = []
    for tr in rows:
        with contextlib.suppress(Exception):
            td_hora = tr.find_element(By.CSS_SELECTOR, "td.integral")
            hora_txt = (td_hora.text or "").strip()
            m = re.search(r"(\d{2}:\d{2})", hora_txt)
            hora = m.group(1) if m else hora_txt.split()[0] if hora_txt else ""
            td_res = tr.find_element(By.CSS_SELECTOR, "td.reservar")
            btns = td_res.find_elements(By.XPATH, ".//button[contains(translate(.,'RESERVAR','reservar'),'reservar')]")
            if btns:
                status = "disponível"
            else:
                status = (td_res.text or "").strip().lower()
                if not status:
                    mid_txt = ""
                    with contextlib.suppress(Exception):
                        mid_txt = tr.find_element(By.CSS_SELECTOR, "td.indisponivel, td.disponivel").text.strip()
                    status = mid_txt.lower() if mid_txt else "indisponível"
            out.append({"data": day, "quadra": quadra_nome, "hora": hora, "status": status})
    return pd.DataFrame(out)

def extract_range_for_quadra(wait, driver, idx: int, start: date, end: date) -> pd.DataFrame:
    quadra_nome = f"Quadra {idx+1}"
    ensure_reservas_list_ready(wait, driver, tries=4)
    click_tenis_by_index(driver, idx)
    switch_to_new_window_if_any(driver)
    try_switch_to_any_frame(driver)

    all_rows = []
    current = start
    while current <= end:
        if not click_day_in_calendar(wait, driver, current):
            current += timedelta(days=1); continue
        df = parse_period_table(wait, driver, current, quadra_nome)
        if not df.empty:
            all_rows.append(df)
        current += timedelta(days=1)

    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame(columns=["data","quadra","hora","status"])

# --- Chrome factory para rodar em paralelo ---

def _build_chrome():
    from selenium.webdriver.chrome.options import Options
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--blink-settings=imagesEnabled=false")
    options.add_experimental_option("prefs", {
        "profile.managed_default_content_settings.images": 2,
        "profile.managed_default_content_settings.stylesheets": 2,
        "profile.managed_default_content_settings.fonts": 2,
    })
    options.page_load_strategy = "eager"

    # >>> aponto para o binário do Chrome/Chromium presente no container
    chrome_bin = (
        os.getenv("CHROME_BIN")
        or os.getenv("GOOGLE_CHROME_BIN")
        or "/usr/bin/chromium"
        or "/usr/bin/chromium-browser"
    )
    if os.path.exists(chrome_bin):
        options.binary_location = chrome_bin

    drv = webdriver.Chrome(service=Service(), options=options)
    with contextlib.suppress(Exception):
        drv.execute_cdp_cmd("Network.enable", {})
        drv.execute_cdp_cmd("Network.setBlockedURLs", {
            "urls": ["*.png","*.jpg","*.jpeg","*.gif","*.webp","*.svg","*.css","*.woff","*.woff2","*.ttf"]
        })
    return drv

# ========= WORKERS (um processo por quadra) =========

def worker_full(username: str, password: str, qi: int, start: date, end: date) -> pd.DataFrame:
    """Retorna DataFrame completo (com disponíveis e indisponíveis) dessa quadra."""
    drv = _build_chrome()
    wait = WebDriverWait(drv, 25)
    try:
        do_login(wait, drv, username, password)
        open_nova_reserva_list(wait, drv)
        ensure_reservas_list_ready(wait, drv, tries=4)
        df = extract_range_for_quadra(wait, drv, qi, start, end)
        return df
    finally:
        with contextlib.suppress(Exception):
            drv.quit()

def worker_fast(username: str, password: str, qi: int, start: date, end: date) -> list[dict]:
    """Retorna SOMENTE slots disponíveis dessa quadra."""
    drv = _build_chrome()
    wait = WebDriverWait(drv, 25)
    hits: list[dict] = []
    try:
        do_login(wait, drv, username, password)
        open_nova_reserva_list(wait, drv)
        ensure_reservas_list_ready(wait, drv, tries=4)

        quadra_nome = f"Quadra {qi+1}"
        click_tenis_by_index(drv, qi)
        switch_to_new_window_if_any(drv)
        try_switch_to_any_frame(drv)

        cur = start
        while cur <= end:
            if not click_day_in_calendar(wait, drv, cur):
                cur += timedelta(days=1); continue
            rows = drv.find_elements(By.CSS_SELECTOR, "#tabelaDePeriodos tbody tr")
            for tr in rows:
                with contextlib.suppress(Exception):
                    hora_txt = (tr.find_element(By.CSS_SELECTOR, "td.integral").text or "").strip()
                    m = re.search(r"(\d{2}:\d{2})", hora_txt)
                    hora = m.group(1) if m else (hora_txt.split()[0] if hora_txt else "")
                    btns = tr.find_elements(By.XPATH, ".//button[contains(translate(.,'RESERVAR','reservar'),'reservar')]")
                    if btns:
                        hits.append({"data": cur.strftime("%Y-%m-%d"), "hora": hora, "quadra": quadra_nome})
            cur += timedelta(days=1)
        return hits
    finally:
        with contextlib.suppress(Exception):
            drv.quit()

# ========= Renderizações =========

def _style_and_render_full_html(full: pd.DataFrame, log: List[str]) -> str:
    full = full.copy()
    full["data"] = pd.to_datetime(full["data"])
    full["hora"] = full["hora"].fillna("").astype(str).str.strip()
    full["status"] = full["status"].astype(str).str.strip()

    horas_catalogo = (
        full.loc[full["hora"].str.len().gt(0) & ~full["hora"].str.lower().eq("integral"), "hora"]
            .dropna().unique().tolist()
    )

    mask_integral = full["hora"].str.lower().eq("integral")
    mask_integral_indisp = mask_integral & full["status"].str.contains("indispon", case=False, na=False)

    headers = []
    if mask_integral_indisp.any():
        pairs = full.loc[mask_integral_indisp, ["data", "quadra"]].drop_duplicates()
        for _, r in pairs.iterrows():
            full = full[~(full["data"].eq(r["data"]) & full["quadra"].eq(r["quadra"]))]
        novas = []
        for _, r in pairs.iterrows():
            for h in horas_catalogo:
                novas.append({"data": r["data"], "quadra": r["quadra"], "hora": h, "status": "indisponível"})
            headers.append(r["data"])
        full = pd.concat([full, pd.DataFrame(novas)], ignore_index=True)

    dias_semana = ["segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo"]
    full["Dia"] = full["data"].dt.strftime("%d/%m/%Y")
    full["DiaSemana"] = full["data"].dt.dayofweek.map(lambda i: dias_semana[i])

    wide = (
        full.pivot_table(index=["Dia", "hora", "DiaSemana"], columns="quadra",
                         values="status", aggfunc="first")
            .reset_index()
    )

    if headers:
        dias_hdr = pd.to_datetime(pd.Series(headers)).dt.strftime("%d/%m/%Y").unique().tolist()
        add = pd.DataFrame([
            {"Dia": d, "hora": "Hora", "DiaSemana": "DiaSemana",
             "Quadra 1": "Quadra 1", "Quadra 2": "Quadra 2", "Quadra 3": "Quadra 3"}
            for d in dias_hdr
        ])
        wide = pd.concat([wide, add], ignore_index=True)
        wide["_d"] = pd.to_datetime(wide["Dia"], format="%d/%m/%Y", errors="coerce")
        wide["_t"] = pd.to_datetime(wide["hora"], format="%H:%M", errors="coerce")
        wide = wide.sort_values(["_d", "_t"], kind="stable", na_position="first").drop(columns=["_d","_t"])

    for i in range(1, 4):
        col = f"Quadra {i}"
        if col not in wide.columns:
            wide[col] = None

    wide = wide.rename(columns={"hora": "Hora"})
    wide = wide[["Dia", "DiaSemana", "Hora", "Quadra 1", "Quadra 2", "Quadra 3"]]

    # Styler e CSS (igual ao seu fluxo atual)
    def _status_to_css(val) -> str:
        if val is None:
            return ""
        s = str(val).strip().lower()
        if s == "nan":
            return ""
        if "indispon" in s:
            return "background:#ffe4b5;border:1px solid #f0c88b;text-align:center;font-weight:600;"
        if "dispon" in s:
            return "background:#c6efce;border:1px solid #b7ddb9;font-weight:600;text-align:center;"
        return "text-align:center;"

    def _row_header_style(row):
        if str(row.get("Hora", "")).strip() == "Hora":
            return ["font-weight:700;background:#e0e0e0;border-bottom:2px solid #bbb"] * len(row)
        return [""] * len(row)

    quad_cols = [c for c in wide.columns if c.lower().startswith("quadra ")]
    mask_header = wide["Hora"].fillna("").eq("")
    wide.loc[mask_header, "Hora"] = "Hora"
    for col in quad_cols:
        wide.loc[mask_header, col] = col
    wide.loc[mask_header, "DiaSemana"] = ""
    for col in quad_cols:
        s = wide[col]
        mask_empty_str = s.fillna("").astype(str).str.strip().eq("")
        wide.loc[~mask_header & mask_empty_str, col] = "indisponível"

    sty = (wide.style
           .map(_status_to_css, subset=quad_cols)
           .set_properties(**{"white-space": "nowrap", "text-align": "center"},
                           subset=quad_cols + ["Hora", "Dia", "DiaSemana"])
           .apply(_row_header_style, axis=1))
    if hasattr(sty, "hide"): sty = sty.hide(axis="index")
    elif hasattr(sty, "hide_index"): sty = sty.hide_index()

    css = """
    <style>
      body{font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;margin:20px;color:#222;}
      h1{font-size:20px;margin:0 0 8px 0}
      .sub{color:#666;margin-bottom:14px}
      .legend{display:flex;gap:14px;margin:10px 0 18px 0;font-size:13px}
      .dot{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:6px;vertical-align:middle}
      .ok  {background:#c6efce;border:1px solid #b7ddb9}
      .blk {background:#ffe4b5;border:1px solid #f0c88b}
      table{border-collapse:collapse;width:100%;font-size:13px}
      thead{display:none;}
      th,td{padding:8px 10px;border-bottom:1px solid #eee}
      tbody tr:nth-child(even){background:#fafafa}
      .footer{margin-top:16px;color:#777;font-size:12px}
    </style>
    """
    html = []
    html.append("<!doctype html><html><head><meta charset='utf-8'>")
    html.append(css)
    html.append("</head><body>")
    html.append("<h1>Quadras de Tênis · Próximos 15 dias</h1>")
    html.append("<div class='sub'>Dia · Dia da semana · Hora · Quadra 1 · Quadra 2 · Quadra 3</div>")
    html.append("<div class='legend'>"
                "<span><span class='dot ok'></span>Disponível</span>"
                "<span><span class='dot blk'></span>Indisponível</span>"
                "</div>")
    html.append(sty.to_html())
    html.append("<div class='footer'>Gerado automaticamente</div>")
    html.append("</body></html>")
    html.append("<details style='margin:16px 0;'><summary>Log de execução</summary><pre>")
    html.append("\n".join(log))
    html.append("</pre></details>")
    return "\n".join(html)

def _render_fast_html(hits: list[dict]) -> str:
    head = """
    <style>
      body{font-family:Inter,Segoe UI,Roboto,Arial,sans-serif;margin:20px;color:#222;}
      table{border-collapse:collapse;width:100%;font-size:13px}
      th,td{padding:8px 10px;border-bottom:1px solid #eee; text-align:left}
      tbody tr:nth-child(even){background:#fafafa}
    </style>
    """
    if not hits:
        return f"<!doctype html><html><head>{head}</head><body><h1>Nenhuma disponibilidade encontrada</h1></body></html>"
    rows = "\n".join(f"<tr><td>{r['data']}</td><td>{r['hora']}</td><td>{r['quadra']}</td></tr>" for r in hits)
    return f"<!doctype html><html><head>{head}</head><body><h1>Disponíveis (paralelo)</h1><table><thead><tr><th>Data</th><th>Hora</th><th>Quadra</th></tr></thead><tbody>{rows}</tbody></table></body></html>"

# ========= Funções públicas: executam em paralelo =========

def run_full_parallel(username: str, password: str, start_date: date, end_date: date) -> str:
    """Modo COMPLETO, paralelo por quadra."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    log = [f"Parallel full: {start_date}..{end_date}"]
    dfs = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(worker_full, username, password, qi, start_date, end_date) for qi in (0,1,2)]
        for fu in as_completed(futs):
            df = fu.result()
            if not df.empty:
                dfs.append(df)
    if not dfs:
        return "<h3>Nenhum dado coletado</h3><p>Sem slots ou bloqueio/erro no site.</p>"
    full = pd.concat(dfs, ignore_index=True)
    return _style_and_render_full_html(full, log)

def run_fast_parallel(username: str, password: str, start_date: date, end_date: date) -> str:
    """Modo RÁPIDO, paralelo por quadra (só slots disponíveis)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    hits: list[dict] = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(worker_fast, username, password, qi, start_date, end_date) for qi in (0,1,2)]
        for fu in as_completed(futs):
            hits.extend(fu.result())
    hits.sort(key=lambda r: (r["data"], r["hora"], r["quadra"]))
    return _render_fast_html(hits)
