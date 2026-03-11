import React, { useState, useEffect } from 'react';
import { scrapedPricesAPI, scrapeAPI, suppliersAPI } from '../lib/api';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/card';
import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Badge } from '../components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '../components/ui/table';
import { Search, RefreshCw, TrendingDown, TrendingUp, Loader2, Zap } from 'lucide-react';
import { toast } from 'sonner';

const Precos = () => {
  const [medida, setMedida] = useState('');
  const [prices, setPrices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [scraping, setScraping] = useState(false);
  const [suppliers, setSuppliers] = useState([]);
  const [stats, setStats] = useState(null);

  useEffect(() => {
    loadSuppliers();
    // Load all prices on initial load
    loadAllPrices();
  }, []);

  const loadSuppliers = async () => {
    try {
      const { data } = await suppliersAPI.getAll();
      setSuppliers(data.filter(s => s.is_active));
    } catch (error) {
      console.error('Error loading suppliers:', error);
    }
  };

  const loadAllPrices = async () => {
    setLoading(true);
    try {
      const { data } = await scrapedPricesAPI.getAll();
      processPrices(data);
    } catch (error) {
      console.error('Error loading prices:', error);
      toast.error('Erro ao carregar preços');
    } finally {
      setLoading(false);
    }
  };

  const searchPrices = async () => {
    if (!medida.trim()) {
      loadAllPrices();
      return;
    }

    setLoading(true);
    try {
      // Normalize medida: remove / and R
      const medidaNorm = medida.replace(/\//g, '').replace(/R/gi, '');
      const { data } = await scrapedPricesAPI.getAll(medidaNorm);
      processPrices(data);
      
      if (data.length === 0) {
        toast.info(`Nenhum preço encontrado para "${medida}". Execute um novo scraping.`);
      }
    } catch (error) {
      console.error('Error searching prices:', error);
      toast.error('Erro ao pesquisar preços');
    } finally {
      setLoading(false);
    }
  };

  const processPrices = (data) => {
    // Sort by price (lowest first)
    const sorted = [...data].sort((a, b) => (a.price || 999) - (b.price || 999));
    setPrices(sorted);

    // Calculate stats
    const withPrice = sorted.filter(p => p.price && p.price > 0);
    if (withPrice.length > 0) {
      const minPrice = Math.min(...withPrice.map(p => p.price));
      const maxPrice = Math.max(...withPrice.map(p => p.price));
      const best = withPrice.find(p => p.price === minPrice);
      
      setStats({
        total: sorted.length,
        withPrice: withPrice.length,
        minPrice,
        maxPrice,
        difference: maxPrice - minPrice,
        bestSupplier: best?.supplier_name,
        bestBrand: best?.marca,
      });
    } else {
      setStats(null);
    }
  };

  const startScraping = async () => {
    if (!medida.trim()) {
      toast.error('Introduza uma medida para fazer scraping');
      return;
    }

    setScraping(true);
    const medidaNorm = medida.replace(/\//g, '').replace(/R/gi, '');
    
    try {
      // Start scraping for all active suppliers
      const promises = suppliers.map(s => 
        scrapeAPI.enqueue(s.name.toLowerCase(), [medidaNorm])
          .catch(err => ({ error: err, supplier: s.name }))
      );
      
      const results = await Promise.all(promises);
      const successful = results.filter(r => !r.error).length;
      
      toast.success(`Scraping iniciado para ${successful} fornecedores. Aguarde alguns minutos e atualize.`);
    } catch (error) {
      console.error('Error starting scraping:', error);
      toast.error('Erro ao iniciar scraping');
    } finally {
      setScraping(false);
    }
  };

  const handleKeyPress = (e) => {
    if (e.key === 'Enter') {
      searchPrices();
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return '-';
    const date = new Date(dateStr);
    return date.toLocaleDateString('pt-PT', { 
      day: '2-digit', 
      month: '2-digit', 
      year: '2-digit',
      hour: '2-digit',
      minute: '2-digit'
    });
  };

  // Group prices by medida for display
  const medidas = [...new Set(prices.map(p => p.medida))];

  return (
    <div className="space-y-6" data-testid="precos-page">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pesquisa de Preços</h1>
          <p className="text-slate-500">Pesquise e compare preços de pneus dos fornecedores</p>
        </div>
      </div>

      {/* Search Bar */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex gap-4">
            <div className="flex-1">
              <Input
                placeholder="Introduza a medida do pneu (ex: 205/55R16 ou 2055516)"
                value={medida}
                onChange={(e) => setMedida(e.target.value)}
                onKeyPress={handleKeyPress}
                className="text-lg"
                data-testid="medida-input"
              />
            </div>
            <Button onClick={searchPrices} disabled={loading} data-testid="search-btn">
              {loading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Search className="w-4 h-4 mr-2" />
              )}
              Pesquisar
            </Button>
            <Button variant="outline" onClick={loadAllPrices} disabled={loading} data-testid="refresh-btn">
              <RefreshCw className="w-4 h-4 mr-2" />
              Ver Todos
            </Button>
            <Button 
              variant="secondary" 
              onClick={startScraping} 
              disabled={scraping || !medida.trim()}
              data-testid="scrape-btn"
            >
              {scraping ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Zap className="w-4 h-4 mr-2" />
              )}
              Novo Scraping
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Stats Card */}
      {stats && (
        <Card className="bg-gradient-to-r from-emerald-50 to-teal-50 border-emerald-200">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-8">
                <div>
                  <p className="text-sm text-slate-600">Melhor Preço</p>
                  <p className="text-3xl font-bold text-emerald-600">€{stats.minPrice.toFixed(2)}</p>
                  <p className="text-sm text-slate-500">{stats.bestSupplier} • {stats.bestBrand}</p>
                </div>
                <div className="h-16 w-px bg-slate-200"></div>
                <div>
                  <p className="text-sm text-slate-600">Pior Preço</p>
                  <p className="text-2xl font-semibold text-red-500">€{stats.maxPrice.toFixed(2)}</p>
                </div>
                <div className="h-16 w-px bg-slate-200"></div>
                <div>
                  <p className="text-sm text-slate-600">Diferença</p>
                  <p className="text-2xl font-semibold text-amber-600">€{stats.difference.toFixed(2)}</p>
                </div>
              </div>
              <div className="text-right">
                <p className="text-sm text-slate-600">Resultados</p>
                <p className="text-2xl font-bold text-slate-700">{stats.withPrice}</p>
                <p className="text-xs text-slate-500">de {stats.total} produtos</p>
              </div>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Results Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span>Resultados ({prices.length} produtos)</span>
            {medidas.length > 1 && (
              <Badge variant="outline">{medidas.length} medidas diferentes</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
          ) : prices.length === 0 ? (
            <div className="text-center py-12 text-slate-500">
              <Search className="w-12 h-12 mx-auto mb-4 opacity-50" />
              <p>Nenhum preço encontrado.</p>
              <p className="text-sm">Introduza uma medida e clique em "Novo Scraping" para obter preços.</p>
            </div>
          ) : (
            <div className="max-h-[600px] overflow-auto">
              <Table>
                <TableHeader className="sticky top-0 bg-white">
                  <TableRow>
                    <TableHead className="w-[120px]">Marca</TableHead>
                    <TableHead>Modelo</TableHead>
                    <TableHead className="w-[100px] text-right">Preço</TableHead>
                    <TableHead className="w-[120px]">Fornecedor</TableHead>
                    <TableHead className="w-[100px]">Medida</TableHead>
                    <TableHead className="w-[140px]">Atualizado</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {prices.map((price, index) => {
                    const isBest = stats && price.price === stats.minPrice;
                    const isWorst = stats && price.price === stats.maxPrice;
                    
                    return (
                      <TableRow 
                        key={`${price.supplier_name}-${price.medida}-${price.marca}-${index}`}
                        className={isBest ? 'bg-emerald-50 hover:bg-emerald-100' : isWorst ? 'bg-red-50 hover:bg-red-100' : ''}
                        data-testid={`price-row-${index}`}
                      >
                        <TableCell className="font-medium">
                          <div className="flex items-center gap-2">
                            {price.marca || '-'}
                            {isBest && (
                              <Badge className="bg-emerald-500 text-xs">
                                <TrendingDown className="w-3 h-3 mr-1" />
                                Melhor
                              </Badge>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-slate-600 max-w-[300px] truncate" title={price.modelo}>
                          {price.modelo || '-'}
                        </TableCell>
                        <TableCell className="text-right font-bold">
                          {price.price ? (
                            <span className={isBest ? 'text-emerald-600' : isWorst ? 'text-red-500' : ''}>
                              €{price.price.toFixed(2)}
                            </span>
                          ) : '-'}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">{price.supplier_name}</Badge>
                        </TableCell>
                        <TableCell className="text-slate-500 font-mono text-sm">
                          {price.medida}
                        </TableCell>
                        <TableCell className="text-slate-400 text-sm">
                          {formatDate(price.scraped_at)}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

export default Precos;
