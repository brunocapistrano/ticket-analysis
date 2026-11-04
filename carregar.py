"""Carrega um lote de CSVs do Znuny no PostgreSQL local."""

import hashlib
import json
import os
from pathlib import Path

import psycopg
from dotenv import dotenv_values
from psycopg.types.json import Jsonb

from transformacao import preparar_lote


RAIZ = Path(__file__).resolve().parent
COLUNAS_CHAMADOS = (
    'numero_chamado', 'criado_em', 'fechado_em', 'primeira_resposta_em',
    'primeiro_bloqueio_em', 'estado', 'fila', 'prioridade',
    'tempo_solucao_informado_min', 'tempo_fechamento_corrido_min',
    'tempo_primeira_resposta_corrido_min',
)


def manifesto_csvs(pasta):
    arquivos = []
    for caminho in sorted(pasta.glob('*.csv')):
        with caminho.open('rb') as entrada:
            arquivos.append({'arquivo': caminho.name, 'sha256': hashlib.file_digest(entrada, 'sha256').hexdigest()})
    return arquivos


def conectar():
    config = dotenv_values(RAIZ / '.env')
    senha = os.environ.get('POSTGRES_PASSWORD', config.get('POSTGRES_PASSWORD'))
    if not senha:
        raise ValueError('Defina POSTGRES_PASSWORD no .env do projeto.')
    porta = os.environ.get('POSTGRES_PORT', config.get('POSTGRES_PORT') or '55433')
    return psycopg.connect(
        host='127.0.0.1', port=porta, dbname='znuny_analytics',
        user='znuny_admin', password=senha, connect_timeout=5,
    )


def gravar_lote(conexao, assinatura, arquivos, lote):
    qualidade = dict(lote['qualidade'])
    qualidade['revisao'] = lote['revisao'].to_dict('records')
    with conexao.transaction(), conexao.cursor() as cursor:
        # A restrição única também protege duas cargas simultâneas do mesmo lote.
        cursor.execute(
            """
            INSERT INTO znuny.lotes_importacao (fingerprint_sha256, arquivos, resumo_qualidade)
            VALUES (%s, %s, %s)
            ON CONFLICT (fingerprint_sha256) DO NOTHING
            RETURNING id
            """,
            (assinatura, Jsonb(arquivos), Jsonb(qualidade)),
        )
        inserido = cursor.fetchone()
        if inserido is None:
            cursor.execute('SELECT id FROM znuny.lotes_importacao WHERE fingerprint_sha256 = %s', (assinatura,))
            return cursor.fetchone()[0], False

        lote_id = inserido[0]
        with cursor.copy(
            """
            COPY znuny.chamados (
                lote_id, numero_chamado, criado_em, fechado_em, primeira_resposta_em,
                primeiro_bloqueio_em, estado, fila, prioridade, tempo_solucao_informado_min,
                tempo_fechamento_corrido_min, tempo_primeira_resposta_corrido_min
            ) FROM STDIN
            """
        ) as copia:
            for linha in lote['chamados'].loc[:, list(COLUNAS_CHAMADOS)].itertuples(index=False, name=None):
                copia.write_row((lote_id, *linha))

        with cursor.copy(
            'COPY znuny.chamados_origem (lote_id, numero_chamado, arquivo, ocorrencias) FROM STDIN'
        ) as copia:
            for linha in lote['origens'][['numero_chamado', 'arquivo', 'ocorrencias']].itertuples(index=False, name=None):
                copia.write_row((lote_id, *linha))

    return lote_id, True


def main():
    pasta = RAIZ / 'datas'
    arquivos = manifesto_csvs(pasta)
    lote = preparar_lote(pasta)
    if manifesto_csvs(pasta) != arquivos:
        raise ValueError('Os CSVs mudaram durante a leitura. Execute a carga novamente.')
    if lote['chamados'].empty:
        raise ValueError('Nenhum chamado apto para carga. Confira os diagnósticos da EDA.')

    assinatura = hashlib.sha256(json.dumps(arquivos, sort_keys=True).encode('utf-8')).hexdigest()
    with conectar() as conexao:
        lote_id, inserido = gravar_lote(conexao, assinatura, arquivos, lote)
    print(json.dumps({
        'lote_id': lote_id,
        'resultado': 'carregado' if inserido else 'ja_carregado',
        'qualidade': lote['qualidade'],
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
