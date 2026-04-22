# Contribuindo

## Filosofia

Manter simples:
- poucos arquivos
- funções pequenas
- fluxo direto

## Fluxo atual

1. `config.ts` carrega/valida `searches.json`
2. `search.ts` monta query e coleta resultados (Google API ou mock)
3. `search.ts` também normaliza, deduplica, filtra e pontua
4. `output.ts` gera arquivos markdown/json/index

## Comandos

```bash
npm run test
npm run search -- --dry-run
npm run search -- --debug
```

## Busca real

A busca real usa Google Custom Search JSON API.

Variáveis obrigatórias:
- `GOOGLE_API_KEY`
- `GOOGLE_CSE_ID`

## Adicionando provider

Hoje temos `api` (Google API) e `mock` dentro de `search.ts`.
Para adicionar outro provider:
1. criar função de coleta
2. integrar no `executeSearch`
3. adicionar teste simples em `tests/unit/search.test.ts`
