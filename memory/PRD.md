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
- **run_scraper.py**: Lógica de scraping com Playwright + API interception

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
3. Resultados guardados em `scraped_prices` collection com **marca e modelo**

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
  - Modal de edição com campos para login e pesquisa
  - Botão `</>` na lista de fornecedores

- [x] **CORREÇÃO: Comparação por MEDIDA + MARCA**
  - Scraper MP24 agora usa **API interception** para extrair todos os produtos
  - Cada produto guardado com: medida, marca, modelo, preço
  - Comparação faz match por medida + marca (exact, partial, ou medida_only)
  - 839 produtos por medida com informação completa

### Scrapers
- [x] **MP24**: Funcional com extração de marca/modelo via API
- [x] **Prismanil**: Funcional
- [x] **Dispnal**: Funcional
- [ ] **S. José Pneus**: Login não funciona
- [ ] **Euromais**: Site não responde

## Base de Dados

### Collections
- `suppliers`: Fornecedores com credenciais e seletores
- `jobs`: Jobs de upload Excel
- `job_items`: Items de cada job com economia calculada
- `scraped_prices`: Preços obtidos pelo scraper **com marca e modelo**
- `locks`: Locks por fornecedor

### Schema scraped_prices (ACTUALIZADO)
```json
{
  "supplier_name": "MP24",
  "supplier_id": "xxx",
  "medida": "2055516",
  "marca": "MICHELIN",       // NEW: uppercase brand name
  "modelo": "PRIMACY 4",     // NEW: model name
  "price": 67.75,
  "job_id": "xxx",
  "scraped_at": "2026-02-25T00:00:00Z"
}
```

### Schema job_items (campos de comparação)
```json
{
  "melhor_preco": 67.75,
  "melhor_fornecedor": "MP24",
  "melhor_marca": "MICHELIN",  // NEW: matched brand
  "match_type": "exact",        // NEW: exact, partial, medida_only
  "economia_euro": 20.45,
  "economia_percent": 23.5,
  "supplier_prices": {"MP24 (MICHELIN)": 67.75}
}
```

## Backlog

### P1 (Prioritário)
- [ ] Atualizar scrapers Prismanil e Dispnal para extrair marca/modelo
- [ ] Corrigir scraper S. José (investigar login)
- [ ] Corrigir scraper Euromais (verificar URL/credenciais)

### P2 (Melhorias)
- [ ] Barra de progresso real-time na UI
- [ ] Cronjob para worker automático
- [ ] Usar seletores dinâmicos configurados na UI

### P3 (Futuro)
- [ ] Adicionar mais fornecedores
- [ ] Histórico de preços
- [ ] Alertas de preço
