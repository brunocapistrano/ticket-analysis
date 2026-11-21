# Ticket Analytics

Analisa exportações de chamados do Znuny e carrega os registros tratados em um PostgreSQL local. O fluxo permite conferir a qualidade dos CSVs antes da importação e rastrear em quais arquivos cada chamado apareceu.

## Requisitos

- Python 3.11 ou posterior
- Docker em execução com Docker Compose v2

## Preparar o ambiente

Clone o repositório e execute os comandos a partir da raiz do projeto.

```sh
git clone https://github.com/brunocapistrano/ticket-analysis.git
cd ticket-analysis
```

**Linux e macOS**

```sh
cp .env.example .env
mkdir -p datas
python3 -m venv venv
./venv/bin/python -m pip install -r requirements.txt
```

**Windows (PowerShell)**

```powershell
Copy-Item .env.example .env
New-Item -ItemType Directory -Force datas
py -3 -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Defina uma senha em `POSTGRES_PASSWORD` no arquivo `.env`. A porta local padrão é `55433`. Se ela estiver ocupada, altere `POSTGRES_PORT` no mesmo arquivo. O Git ignora o `.env` e os arquivos em `datas/`.

## Preparar e conferir os CSVs

Coloque as exportações `.csv` diretamente em `datas/`. Use UTF-8 (com ou sem BOM) e ponto e vírgula como separador. Todos os arquivos devem ter as mesmas colunas na mesma ordem.

O cabeçalho precisa incluir `Número do Chamado`, `Idade`, `Criado`, `Fechado`, `Primeira Resposta`, `Primeiro Bloqueio`, `Estado`, `Fila`, `Prioridade`, `Tempo contabilizado` e `Tempo de solução em minutos`. O formato esperado para datas preenchidas é `AAAA-MM-DD HH:MM:SS`.

Execute a análise exploratória para conferir cobertura dos arquivos, duplicatas e problemas de qualidade. Ela exibe o relatório no terminal e preserva os CSVs.

| Ambiente | Comando |
| --- | --- |
| Linux e macOS | `./venv/bin/python eda.py` |
| Windows (PowerShell) | `.\venv\Scripts\python.exe eda.py` |

## Subir o PostgreSQL e importar

Depois de preencher o `.env`, inicie o banco e verifique as tabelas.

```sh
docker compose up -d --wait
docker compose exec db psql -U znuny_admin -d znuny_analytics -c '\dt znuny.*'
```

Para conectar um cliente SQL pelo computador, use o host `127.0.0.1`, a porta configurada em `POSTGRES_PORT`, o banco `znuny_analytics`, o usuário `znuny_admin` e a senha do `.env`.

| Ambiente | Comando de importação |
| --- | --- |
| Linux e macOS | `./venv/bin/python carregar.py` |
| Windows (PowerShell) | `.\venv\Scripts\python.exe carregar.py` |

O carregador imprime um JSON com o ID do lote, o resultado e o resumo de qualidade. Ele grava o lote, os chamados e suas origens em uma única transação. Se os nomes e o conteúdo de todos os arquivos forem os mesmos de um lote anterior, a execução retorna `ja_carregado` com o ID existente.

## Como os dados são tratados

- Registros com o mesmo número de chamado e valores equivalentes são consolidados em um chamado por lote. A comparação ignora a coluna `Idade`.
- Registros sem número de chamado e versões divergentes do mesmo chamado ficam no resumo de revisão do lote, com referência ao arquivo e à posição do registro.
- Os tempos de fechamento e primeira resposta são calculados em minutos corridos e devem ser interpretados dessa forma, fora do contexto de SLA. O tempo de solução informado na exportação é armazenado separadamente. O fuso horário das exportações ainda precisa ser confirmado.

| Tabela | Conteúdo |
| --- | --- |
| `znuny.lotes_importacao` | Arquivos, hashes SHA-256, data da carga e resumo de qualidade com referências para revisão |
| `znuny.chamados` | Chamados tratados, com datas, estado, fila, prioridade e tempos |
| `znuny.chamados_origem` | Arquivos de origem e número de ocorrências de cada chamado por arquivo e lote |

## Persistência do banco

Na primeira inicialização com um volume vazio, o PostgreSQL 18 executa [`sql/001_initial.sql`](sql/001_initial.sql). O volume `postgres_data` preserva os dados entre execuções. Aplique novas migrações explicitamente quando o banco já estiver inicializado.

Use `docker compose stop` para parar o banco e `docker compose up -d --wait` para retomá-lo.
