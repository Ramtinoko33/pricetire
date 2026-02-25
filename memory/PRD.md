# Pneu Price Scout - PRD

## Problema Original
O utilizador pretende criar uma aplicação para pesquisar automaticamente os preços de pneus nos websites B2B dos seus fornecedores.

### Requisitos Principais
1. **Entrada**: Carregar ficheiro Excel com detalhes dos pneus (marca, medida, modelo) e o preço de custo atual
2. **Processo**: Iniciar sessão nos websites de múltiplos fornecedores (5 a 15), procurar os pneus listados e comparar preços
3. **Saída**: Identificar se algum fornecedor oferece preço mais baixo e gerar relatório com o fornecedor e a poupança

## Arquitetura Implementada

### Backend (FastAPI + MongoDB)
- **server.py**: API REST com endpoints para suppliers, jobs, scraping, comparação
- **worker.py**: Processo independente que executa jobs de scraping
- **run_scraper.py**: Lógica de scraping com Playwright

### Frontend (React)
- Dashboard com estatísticas
- Gestão de fornecedores
- Upload de ficheiros Excel
- Página de resultados com botão "Comparar Preços"
- **Página Scraper**: Interface para scraping manual
- **Modal Seletores CSS**: Configuração de seletores por fornecedor

### Scraping Architecture (Worker Desacoplado)
O scraping usa um sistema de worker desacoplado para contornar proteções anti-bot:
1. API `/scrape/enqueue` cria jobs na fila
2. `worker.py` processa jobs em background
3. Resultados guardados em `scraped_prices` collection

## O Que Foi Implementado

### Sessão 24/02/2026
- [x] Arquitetura Worker desacoplado (P0)
- [x] Scrapers funcionais: MP24, Prismanil, Dispnal
- [x] Página Scraper no frontend
- [x] Fix `/api/jobs` para filtrar scrape jobs

### Sessão 25/02/2026
- [x] **Integração scraped_prices com job_items**
  - Endpoint `/api/jobs/{id}/compare` compara preços scraped com job items
  - Calcula economia por item e total
  - Botão "Comparar Preços" na página de Resultados
  
- [x] **Configuração de Seletores CSS na UI**
  - Endpoints `/api/suppliers/{id}/selectors` GET/PUT
  - Modal de edição com campos:
    - Seletor Username/Password
    - Seletor Botão Login
    - Seletor Campo/Botão Pesquisa
    - Padrão de Preço (Regex)
    - Notas
  - Botão `</>` na lista de fornecedores

### Scrapers
- [x] **MP24**: Funcional (matchcode search)
- [x] **Prismanil**: Funcional
- [x] **Dispnal**: Funcional
- [ ] **S. José Pneus**: Login não funciona
- [ ] **Euromais**: Site não responde

## Base de Dados

### Collections
- `suppliers`: Fornecedores com credenciais e seletores
- `jobs`: Jobs de upload Excel
- `job_items`: Items de cada job com economia calculada
- `scraped_prices`: Preços obtidos pelo scraper
- `locks`: Locks por fornecedor

### Schema suppliers.selectors
```json
{
  "login_username": "#username",
  "login_password": "#password",
  "login_button": "button[type='submit']",
  "search_input": "#searchBox",
  "search_button": "#searchBtn",
  "price_pattern": "€\\s*(\\d+[,.]\\d{2})",
  "notes": "Notas sobre o scraping"
}
```

## Backlog

### P1 (Prioritário)
- [ ] Corrigir scraper S. José (investigar login)
- [ ] Corrigir scraper Euromais (verificar URL/credenciais)
- [ ] Usar seletores dinâmicos no run_scraper.py

### P2 (Melhorias)
- [ ] Barra de progresso real-time na UI
- [ ] Cronjob para worker automático
- [ ] Histórico de preços

### P3 (Futuro)
- [ ] Adicionar mais fornecedores
- [ ] Alertas de preço
