# BBZ Reservas — Web Scraper

Ferramenta para consultar horários de Tênis e Churrasqueiras do portal WebWare (BBZ).

### Tecnologias
- FastAPI
- Jinja2
- Requests
- BeautifulSoup4
- Docker

### Deploy no Render
1. Crie novo serviço Web Service  
2. Build Command: *(vazio — Dockerfile já define)*  
3. Start Command: `uvicorn app.main:app --host 0.0.0.0 --port 10000`  
4. Configure Variáveis de ambiente se quiser.

### Uso
Acesse `/` → preencha login do BBZ → selecione:
- tipo: tênis ou churrasco  
- recurso: quadra/churrasqueira  
- intervalo de datas

O app faz login no BBZ, segue sessão e extrai a tabela de horários diretamente do HTML.

