# Job Search Reporter (Simple Architecture)

Projeto Node.js + TypeScript para gerar relatórios de vagas a partir de `searches.json`.

> Arquitetura simplificada (inspirada no estilo do gist): poucas camadas, poucos arquivos, fluxo direto.

## Estrutura (simples)

```txt
src/
  index.ts      # CLI e orquestração principal
  config.ts     # carrega/valida JSON
  search.ts     # monta query + busca (api/mock) + filtra/score
  output.ts     # gera markdown/json/index e grava sem reescrever igual
  types.ts      # tipos centrais
```

## Como roda

```bash
npm install
npm run search
```

### Modos úteis

```bash
npm run search -- --dry-run
npm run search -- --debug
npm run search -- --provider=mock
npm run search -- --config=./searches.json
```

## Busca real

Por padrão usa provider `api` e faz busca web real no DuckDuckGo Lite.

- Variável opcional: `SEARCH_ENGINE_URL`
- Exemplo:

```bash
SEARCH_ENGINE_URL=https://lite.duckduckgo.com/lite/ npm run search
```

## Saídas

- `reports/*.md`
- `reports/json/*.json`
- `reports/README.md`

## Princípios

- Config (`searches.json`) é a fonte da verdade.
- Código explícito e fácil de seguir.
- Dry-run e debug para rodar em cloud tasks.
- Escrita com diff-awareness (não reescreve arquivo sem mudança).
