import os, re, time, calendar, unicodedata
from datetime import date, timedelta
from typing import List, Tuple
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.expected_conditions import staleness_of

SITE_URL = os.getenv("SITE_URL", "https://bbz.com.br/area-do-cliente/")
AREA_GERAL = "https://servc9.webware.com.br/bin/sol/aAreaGeral.asp"
MINHA_UNIDADE_RESERVAS = "https://servc9.webware.com.br/bin/aplic/cpMinhaUnidadeReservas.asp"

def wait_table_refresh(wait: WebDriverWait, driver, prev_html: str, timeout: int = 20):
    """Aguarda a atualização do corpo da tabela comparando HTML anterior x novo."""
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

def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))

def save_html_from_wide_to_string(wide: pd.DataFrame) -> str:
    df = wide.copy()
    quad_cols = [c for c in df.columns if c.lower().startswith("quadra ")]
    mask_header = df["Hora"].fillna("").eq("")
    df.loc[mask_header, "Hora"] = "Hora"
    for col in quad_cols:
        df.loc[mask_header, col] = col
    df.loc[mask_header, "DiaSemana"] = ""
    for col in quad_cols:
        s = df[col]
        mask_empty_str = s.fillna("").astype(str).str.strip().eq("")
        df.loc[~mask_header & mask_empty_str, col] = "indisponível"

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

    sty = (df.style
           .map(_status_to_css, subset=quad_cols)
           .set_properties(**{
               "white-space": "nowrap",
               "text-align": "center"
           }, subset=quad_cols + ["Hora", "Dia", "DiaSemana"])
           .apply(_row_header_style, axis=1)
    )
    if hasattr(sty, "hide"):
        sty = sty.hide(axis="index")
    elif hasattr(sty, "hide_index"):
        sty = sty.hide_index()

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
    html.append("<h1>Quadras de Tênis · Próximos 15 dias</h1>");
    html.append("<div class='sub'>Dia · Dia da semana · Hora · Quadra 1 · Quadra 2 · Quadra 3</div>")
    html.append("<div class='legend'>"
                "<span><span class='dot ok'></span>Disponível</span>"
                "<span><span class='dot blk'></span>Indisponível</span>"
                "</div>")
    html.append(sty.to_html())
    html.append("<div class='footer'>Gerado automaticamente</div>")
    html.append("</body></html>")
    return "\n".join(html)

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
    # alinhar mês
    while True:
        header_start = get_header_month_start(wait, driver)
        if header_start.year == target.year and header_start.month == target.month:
            break
        if month_end(header_start) < target:
            click_next_month(wait, driver)
        else:
            break

    # guarda HTML atual da tabela para detectar refresh
    prev_html = ""
    try:
        prev_html = driver.find_element(By.CSS_SELECTOR, "#tabelaDePeriodos tbody").get_attribute("innerHTML")
    except Exception:
        pass

    # clicar no dia
    day_sel = ".datepicker-days td.day:not(.old):not(.new):not(.disabled):not(.foraPeriodo)"
    days = driver.find_elements(By.CSS_SELECTOR, day_sel)
    for td in days:
        if (td.text or "").strip() == str(target.day):
            driver.execute_script("arguments[0].click();", td)
            # aguarda a tabela de períodos atualizar (sem sleep fixo)
            wait_table_refresh(wait, driver, prev_html, timeout=20)
            return True
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
    """Garante que estamos no iframe certo e que os links de quadra já renderizaram."""
    for _ in range(tries):
        driver.switch_to.default_content()
        try_switch_to_any_frame(driver)
        try:
            # espera direta pelos anchors de SelectReserva
            wait.until(EC.presence_of_element_located(
                (By.XPATH, "//a[contains(@onclick,'SelectReserva')]")
            ))
        except Exception:
            time.sleep(0.6)
            continue
        # já tem algo, contar via função padrão
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

def parse_period_table(wait, driver, day: date, quadra_nome: str) -> pd.DataFrame:
    wait.until(EC.presence_of_element_located((By.ID, "tabelaDePeriodos")))
    rows = driver.find_elements(By.CSS_SELECTOR, "#tabelaDePeriodos tbody tr")
    out = []
    for tr in rows:
        try:
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
                    try:
                        mid_txt = tr.find_element(By.CSS_SELECTOR, "td.indisponivel, td.disponivel").text.strip()
                    except Exception:
                        pass
                    status = mid_txt.lower() if mid_txt else "indisponível"
            out.append({"data": day, "quadra": quadra_nome, "hora": hora, "status": status})
        except Exception:
            continue
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
        ok = click_day_in_calendar(wait, driver, current)
        if not ok:
            current += timedelta(days=1)
            continue
        df = parse_period_table(wait, driver, current, quadra_nome)
        if not df.empty:
            all_rows.append(df)
        current += timedelta(days=1)

    return pd.concat(all_rows, ignore_index=True) if all_rows else pd.DataFrame(columns=["data","quadra","hora","status"])

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
    try:
        try:
            cb = driver.find_element(By.ID, "termo")
            driver.execute_script("if(!arguments[0].checked){arguments[0].click();}", cb)
        except Exception:
            for cb in driver.find_elements(By.CSS_SELECTOR, "input[type='checkbox']"):
                if cb.is_displayed() and cb.is_enabled():
                    driver.execute_script("if(!arguments[0].checked){arguments[0].click();}", cb)
                    break
    except Exception:
        pass
    btn = find_first(wait, [
        (By.XPATH, "//button[contains(.,'ENTRAR')]"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.XPATH, "//input[@type='submit']"),
    ], must_click=True, driver=driver)
    if not btn:
        raise RuntimeError("Botão ENTRAR não encontrado.")
    driver.execute_script("arguments[0].click();", btn)
    try:
        wait.until(lambda d: "webware" in d.current_url or "servc" in d.current_url)
    except TimeoutException:
        pass

def run_scraping(username: str, password: str, start_date: date = None, end_date: date = None) -> str:
    from datetime import date as _date
    if not start_date:
        start_date = _date.today()
    if not end_date:
        end_date = _date.today() + timedelta(days=14)

    log = []
    def L(msg):
        log.append(msg)

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1366,900")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                         "AppleWebKit/537.36 (KHTML, like Gecko) "
                         "Chrome/122.0.0.0 Safari/537.36")

    driver = webdriver.Chrome(service=Service(), options=options)
    wait = WebDriverWait(driver, 25)

    try:
        L(f"Abrindo {SITE_URL}")
        driver.get(SITE_URL)
        L(f"URL inicial: {driver.current_url}")

        # === LOGIN ===
        try:
            user_input = wait.until(EC.presence_of_element_located((By.ID, "mem")))
            pass_input = wait.until(EC.presence_of_element_located((By.ID, "pass")))
            user_input.clear(); user_input.send_keys(username)
            pass_input.clear(); pass_input.send_keys(password)
            L("Campos de login localizados e preenchidos.")

            try:
                cb = driver.find_element(By.ID, "termo")
                driver.execute_script("if(!arguments[0].checked){arguments[0].click();}", cb)
                L("Checkbox de termos marcado.")
            except Exception:
                L("Checkbox de termos não encontrado (ok).")

            btn = find_first(wait, [
                (By.XPATH, "//button[contains(.,'ENTRAR')]"),
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.XPATH, "//input[@type='submit' or @value='ENTRAR']"),
            ], must_click=True, driver=driver)
            if not btn:
                raise RuntimeError("Botão ENTRAR não encontrado.")
            driver.execute_script("arguments[0].click();", btn)
            L("Clique no ENTRAR enviado.")

        except Exception as e:
            html = f"<h3>Falha ao preparar login</h3><pre>{e}</pre>"
            html += f"<details><summary>Log</summary><pre>{chr(10).join(log)}</pre></details>"
            return html

        # === PÓS LOGIN ===
        try:
            wait.until(lambda d: "webware" in d.current_url or "servc" in d.current_url)
            L(f"Redirecionado para: {driver.current_url}")
        except TimeoutException:
            page = driver.page_source[:5000]
            L("Timeout aguardando redirecionamento pós-login.")
            html = "<h3>Login não confirmou</h3><p>O site não redirecionou para a área interna.</p>"
            html += "<details><summary>Diagnóstico</summary>"
            html += "<pre>" + "\n".join(log) + "</pre>"
            html += "<h4>Trecho da página</h4><pre>" + (page.replace('<','&lt;')) + "</pre>"
            html += "</details>"
            return html

        # === ACESSA LISTA DE RESERVAS ===
        L("Abrindo 'Minha Unidade > Reservas'.")
        open_nova_reserva_list(wait, driver)
        L(f"Após abrir lista: URL={driver.current_url}")

        L(f"URL atual antes de buscar quadras: {driver.current_url}")
        html_preview = driver.page_source[:2000]
        L(f"Prévia do HTML: {html_preview[:500].replace('<','&lt;')}")
        itens = list_tenis_links(driver)
        L(f"Links de QUADRA encontrados: {len(itens)}")

        if not itens:
            page = driver.page_source[:5000]
            html = "<h3>Nenhuma quadra encontrada na lista</h3><p>Os seletores podem ter mudado ou o portal bloqueou o acesso.</p>"
            html += "<details><summary>Diagnóstico</summary><pre>" + "\n".join(log) + "</pre>"
            html += "<h4>Trecho da página</h4><pre>" + (page.replace('<','&lt;')) + "</pre></details>"
            return html

        # === COLETA POR INTERVALO ===
        dfs = []
        for i in range(3):
            try:
                L(f"Preparando lista para Quadra {i+1}…")
                driver.get(MINHA_UNIDADE_RESERVAS)
                switch_to_new_window_if_any(driver)
                
                count = ensure_reservas_list_ready(wait, driver, tries=4)
                L(f"Links de QUADRA visíveis agora: {count}")
                
                # fallback: se ainda 0, reabrir via fluxo oficial (às vezes o GET direto não injeta o iframe certo)
                if count == 0:
                    L("Fallback: reabrindo via 'open_nova_reserva_list'.")
                    open_nova_reserva_list(wait, driver)
                    count = ensure_reservas_list_ready(wait, driver, tries=4)
                    L(f"Links após fallback: {count}")
                    if count == 0:
                        raise RuntimeError("Links de QUADRA de TÊNIS não renderizaram (iframe/JS).")

                L(f"Coletando Quadra {i+1} ({(end_date - start_date).days + 1} dias)…")
                df = extract_range_for_quadra(wait, driver, i, start_date, end_date)
                L(f"Quadra {i+1}: {len(df)} linhas.")
                if not df.empty:
                    dfs.append(df)
            except Exception as e:
                L(f"Quadra {i+1}: erro {e}")

        if not dfs:
            page = driver.page_source[:5000]
            html = "<h3>Nenhum dado coletado</h3><p>Pode ser bloqueio do site, mudança no HTML, ou sem slots publicados.</p>"
            html += "<details><summary>Diagnóstico</summary><pre>" + "\n".join(log) + "</pre>"
            html += "<h4>Trecho da página</h4><pre>" + (page.replace('<','&lt;')) + "</pre></details>"
            return html

        # === TRATAMENTO FINAL E RENDER HTML ===
        full = pd.concat(dfs, ignore_index=True)
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
            full.pivot_table(index=["Dia", "hora", "DiaSemana"],
                             columns="quadra", values="status", aggfunc="first")
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

        html = save_html_from_wide_to_string(wide)
        html += "<details style='margin:16px 0;'><summary>Log de execução</summary><pre>"
        html += "\n".join(log)
        html += "</pre></details>"
        return html

    finally:
        try:
            driver.quit()
        except Exception:
            pass


