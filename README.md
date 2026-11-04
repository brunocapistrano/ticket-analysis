# Banco de dados Znuny Analytics

Com o Docker e o Docker Compose em funcionamento, copie `.env.example` para `.env` na raiz do projeto e defina uma senha própria em `POSTGRES_PASSWORD`. O arquivo `.env` fica fora do Git.

```powershell
Copy-Item .env.example .env
# Preencha a senha em .env antes de executar o comando abaixo.
docker compose up -d --wait
docker compose exec db psql -U znuny_admin -d znuny_analytics -c '\dt znuny.*'
```

A conexão local usa o endereço `127.0.0.1:55433`, o banco `znuny_analytics` e o usuário `znuny_admin`. Se precisar de outra porta no computador, altere `POSTGRES_PORT` no `.env`.

Na primeira execução com um volume vazio, o PostgreSQL cria o banco e aplica `sql/001_initial.sql`. O volume `postgres_data` mantém o banco entre execuções. Novas migrações para um banco existente devem ser aplicadas explicitamente.

Para parar o banco, use `docker compose stop`. Para retomá-lo, use `docker compose up -d --wait`.

## Carga dos CSVs

Com o banco rodando, coloque os arquivos de entrada em `datas/`. Use Python 3.11 ou posterior no ambiente virtual do projeto.

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
.\venv\Scripts\python.exe carregar.py
```

O script usa a senha e a porta configuradas no `.env`. Ele registra a lista dos arquivos e suas assinaturas, os chamados tratados, suas origens e o resumo de qualidade em uma única transação. Nomes e conteúdo iguais identificam o mesmo lote. Nesse caso, a nova execução retorna `ja_carregado` e o ID do lote existente.
