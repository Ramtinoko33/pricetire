# Pneu Price Scout - PRD

## Problema Original
Aplicação para pesquisar automaticamente preços de pneus nos websites B2B dos fornecedores.

## Estado Atual: FUNCIONAL ✅

### Pipeline End-to-End Testado
1. **POST /api/scrape/enqueue** → Cria job na coleção `jobs`
2. **worker.py** → Lê jobs, adquire lock, chama `run_scraper.py`
3. **run_scraper.py** → Scraping com Playwright, guarda em `scraped_prices`

### Fixes Aplicados (11/03/2026)

#### FIX 1: password_raw no create_supplier
- Adicionado `password_raw` antes do hash no `server.py`
- Script `fix_passwords.py` atualizou fornecedores existentes

#### FIX 2: MONGO_URL no worker.py
- Removido fallback hardcoded para Railway
- Worker agora usa `.env` obrigatoriamente

#### FIX 3: .env no run_scraper.py
- Adicionado `load_dotenv(Path('/app/backend/.env'))`
- Scraper consegue conectar ao MongoDB corretamente

### Resultado do Teste
```
=== WORKER STARTING ===
=== IMPORTS OK ===
=== MONGODB CONNECTED OK ===
Worker started at 2026-03-11

[MP24] Captured 833 tyres from API
[MP24] Extracted 742 products with brand/model
  Saved 742 products with brand/model
  Job completed successfully
```

### Dados na Base de Dados
- **1113 preços** scraped
- **1106 com marca/modelo**
- **3 fornecedores** funcionais: MP24, Prismanil, Dispnal

## Arquitetura

```
/app/backend/
├── server.py          # FastAPI API
├── worker.py          # Processo de scraping em background
├── run_scraper.py     # Lógica de scraping com Playwright
├── fix_passwords.py   # Script para atualizar passwords
└── .env               # Credenciais MongoDB
```

### Fornecedores Configurados
| Nome | Username | Status |
|------|----------|--------|
| MP24 | PTO02101 | ✅ Funcional |
| Prismanil | dpedrov287 | ✅ Funcional |
| Dispnal | geral@pneusdpedrov.com | ✅ Funcional |
| S. José | 5010600251 | ❌ Login falha |
| Euromais | 5010600251 | ❌ Timeout |

## Como Usar

### Criar Job de Scraping
```bash
curl -X POST http://localhost:8000/api/scrape/enqueue \
  -H "Content-Type: application/json" \
  -d '{"supplier_id": "mp24", "sizes": ["2055516"]}'
```

### Executar Worker
```bash
cd /app/backend && python3 worker.py
```

### Verificar Resultados
```python
from pymongo import MongoClient
client = MongoClient(os.environ['MONGO_URL'])
db = client['test_database']

# Jobs
for job in db.jobs.find({'type': 'scrape'}):
    print(job['status'], job['supplier_id'])

# Preços
for p in db.scraped_prices.find().limit(10):
    print(p['supplier_name'], p['medida'], p['marca'], p['price'])
```

## Backlog

### P1 - Prioritário
- [ ] Corrigir S. José (investigar login)
- [ ] Corrigir Euromais (timeout)

### P2 - Melhorias
- [ ] Cronjob para worker automático
- [ ] Barra de progresso na UI
- [ ] Usar seletores CSS configurados

### P3 - Futuro
- [ ] Histórico de preços
- [ ] Alertas de variação
