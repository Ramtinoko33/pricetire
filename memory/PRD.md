# Pneu Price Scout - PRD

## Problema Original
O utilizador pretende criar uma aplicação para pesquisar automaticamente os preços de pneus nos websites B2B dos seus fornecedores.

### Requisitos Principais
1. **Entrada**: Carregar ficheiro Excel com detalhes dos pneus (marca, medida, modelo) e o preço de custo atual
2. **Processo**: Iniciar sessão nos websites de múltiplos fornecedores (5 a 15), procurar os pneus listados e comparar preços
3. **Saída**: Identificar se algum fornecedor oferece preço mais baixo e gerar relatório com o fornecedor e a poupança

## Arquitetura Implementada

### Backend (FastAPI + MongoDB)
- **server.py**: API REST com endpoints para suppliers, jobs, scraping
- **worker.py**: Processo independente que executa jobs de scraping
- **run_scraper.py**: Lógica de scraping com Playwright

### Frontend (React)
- Dashboard com estatísticas
- Gestão de fornecedores
- Upload de ficheiros Excel
- Página de resultados
- **Página Scraper**: Interface para scraping manual

### Scraping Architecture (Worker Desacoplado)
O scraping usa um sistema de worker desacoplado para contornar proteções anti-bot:
1. API `/scrape/enqueue` cria jobs na fila
2. `worker.py` processa jobs em background
3. Resultados guardados em `scraped_prices` collection

## O Que Foi Implementado (24/02/2026)

### P0 - Arquitetura Worker (COMPLETO)
- [x] Endpoint `/api/scrape/enqueue` para criar jobs
- [x] `worker.py` com sistema de locks por fornecedor
- [x] `run_scraper.py` com função `run_supplier()`
- [x] Reutilização de sessão de login para múltiplas medidas
- [x] Armazenamento de `password_raw` para credenciais não hashadas

### P1 - Scrapers Funcionais (PARCIAL)
- [x] **MP24**: Funcional com matchcode search
- [x] **Prismanil**: Funcional
- [x] **Dispnal**: Funcional
- [ ] **S. José Pneus**: Login não funciona (credenciais ou site mudou)
- [ ] **Euromais**: Site não responde (timeout)

### Frontend
- [x] Página Scraper mostra preços obtidos
- [x] Agrupamento por medida
- [x] Indicador de "Melhor" preço
- [x] Botão refresh funcional

### Bug Fixes
- [x] Corrigido `/api/jobs` para filtrar jobs de scrape queue
- [x] Corrigido paths da API no frontend (removido `/api/` duplicado)

## Base de Dados

### Collections
- `suppliers`: Fornecedores com credenciais
- `jobs`: Jobs de upload Excel (type undefined) + jobs de scrape (type: "scrape")
- `job_items`: Items de cada job de upload
- `scraped_prices`: Preços obtidos pelo scraper
- `locks`: Locks por fornecedor para evitar scraping concorrente

### Campos password_raw
Os fornecedores têm `password` (hashada) e `password_raw` (texto claro para scraping):
- S. José: 5010600251
- euromais: 5010600251
- MP24: Sl6dBhGf
- Prismanil: dompedro4785
- Dispnal: 501060251

## Backlog

### P1 (Prioritário)
- [ ] Corrigir scraper S. José (investigar login)
- [ ] Corrigir scraper Euromais (verificar URL/credenciais)

### P2 (Melhorias)
- [ ] Barra de progresso real-time na UI
- [ ] Integrar scraped_prices com job_items
- [ ] Configurar cronjob para worker
- [ ] Exportação melhorada para Excel

### P3 (Futuro)
- [ ] Configuração de seletores CSS por fornecedor na UI
- [ ] Adicionar mais fornecedores
- [ ] Histórico de preços
