"""Prepara em memória um lote de chamados do Znuny."""

import json
from pathlib import Path

import pandas as pd

from eda import ABERTOS, CHAVE, ESTADOS, FECHADOS, ORIGEM, carregar_csvs


COLUNAS_DATAS = {
    'Criado': 'criado_em',
    'Fechado': 'fechado_em',
    'Primeira Resposta': 'primeira_resposta_em',
    'Primeiro Bloqueio': 'primeiro_bloqueio_em',
}
TEMPO_INFORMADO = 'Tempo de solução em minutos'


def transformar(dados):
    """Devolve chamados, origens, referências para revisão e contagens do lote."""
    campos_comparados = dados.columns.drop([CHAVE, ORIGEM, 'Idade'])
    chave = dados[CHAVE].str.strip()
    sem_chave = chave.eq('')
    identificados = dados.loc[~sem_chave].copy()
    identificados[CHAVE] = chave.loc[~sem_chave]

    # Uma versão divergente não pode ser escolhida pela ordem dos arquivos.
    divergencias = identificados.groupby(CHAVE)[campos_comparados].nunique(dropna=False).gt(1)
    conflitos = divergencias.loc[divergencias.any(axis=1)]
    tem_conflito = chave.isin(conflitos.index)
    aceitos = identificados.loc[~tem_conflito.loc[identificados.index]]

    pendentes = sem_chave | tem_conflito
    registro_no_arquivo = dados.groupby(ORIGEM, sort=False).cumcount() + 1
    campos_divergentes = {
        numero: tuple(linha.index[linha]) for numero, linha in conflitos.iterrows()
    }
    revisao = pd.DataFrame({
        'numero_chamado': chave.loc[pendentes].astype(object).where(~sem_chave, None),
        'arquivo': dados.loc[pendentes, ORIGEM],
        'registro_no_arquivo': registro_no_arquivo.loc[pendentes],
        'motivo': sem_chave.loc[pendentes].map({True: 'identificador_vazio', False: 'conflito'}),
        'campos_divergentes': chave.loc[pendentes].map(lambda numero: campos_divergentes.get(numero, ())),
    }).reset_index(drop=True)

    origens = (aceitos.groupby([CHAVE, ORIGEM], sort=False).size()
               .reset_index(name='ocorrencias')
               .rename(columns={CHAVE: 'numero_chamado', ORIGEM: 'arquivo'}))
    unicos = aceitos.drop_duplicates(CHAVE)
    chamados = pd.DataFrame({'numero_chamado': unicos[CHAVE]})
    qualidade = {
        'linhas_lidas': len(dados),
        'chamados_preparados': len(unicos),
        'repeticoes_excedentes_aceitas': len(aceitos) - len(unicos),
        'linhas_sem_identificador': int(sem_chave.sum()),
        'identificadores_fora_do_padrao_numerico': int((~sem_chave & ~chave.str.fullmatch(r'\d+')).sum()),
        'chamados_em_conflito': len(conflitos),
        'linhas_em_conflito': int(tem_conflito.sum()),
        'vinculos_de_origem': len(origens),
        'datas_invalidas': {},
    }

    for origem, destino in COLUNAS_DATAS.items():
        texto = unicos[origem].str.strip()
        formato = texto.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
        chamados[destino] = pd.to_datetime(
            texto.where(formato), format='%Y-%m-%d %H:%M:%S', errors='coerce'
        )
        qualidade['datas_invalidas'][destino] = int((texto.ne('') & chamados[destino].isna()).sum())

    for origem, destino in [('Estado', 'estado'), ('Fila', 'fila'), ('Prioridade', 'prioridade')]:
        chamados[destino] = unicos[origem].str.strip().replace('', None)

    texto_informado = unicos[TEMPO_INFORMADO].str.strip()
    informado = pd.to_numeric(texto_informado, errors='coerce')
    informado_valido = informado.ge(0) & informado.lt(float('inf'))
    chamados['tempo_solucao_informado_min'] = informado.where(informado_valido)
    qualidade['tempos_informados_invalidos'] = int((texto_informado.ne('') & ~informado_valido).sum())

    estado = chamados['estado'].str.casefold()
    fechados = estado.isin(FECHADOS)
    fechamento = (chamados['fechado_em'] - chamados['criado_em']).dt.total_seconds().div(60)
    resposta = (chamados['primeira_resposta_em'] - chamados['criado_em']).dt.total_seconds().div(60)
    bloqueio = (chamados['primeiro_bloqueio_em'] - chamados['criado_em']).dt.total_seconds().div(60)
    chamados['tempo_fechamento_corrido_min'] = fechamento.where(fechados & fechamento.ge(0))
    chamados['tempo_primeira_resposta_corrido_min'] = resposta.where(resposta.ge(0))
    qualidade['fechamentos_anteriores_a_criacao'] = int(fechamento.lt(0).sum())
    qualidade['respostas_anteriores_a_criacao'] = int(resposta.lt(0).sum())
    qualidade['bloqueios_anteriores_a_criacao'] = int(bloqueio.lt(0).sum())
    comparaveis = informado_valido & fechamento.ge(0)
    qualidade['tempos_solucao_comparaveis'] = int(comparaveis.sum())
    qualidade['tempos_solucao_divergentes'] = int((comparaveis & informado.sub(fechamento).abs().gt(1)).sum())
    qualidade['abertos_com_data_de_fechamento'] = int(
        (estado.isin(ABERTOS) & chamados['fechado_em'].notna()).sum()
    )
    qualidade['fechados_sem_data_valida'] = int((fechados & chamados['fechado_em'].isna()).sum())
    qualidade['estados_desconhecidos'] = int((~estado.isin(ESTADOS)).sum())
    qualidade['sem_primeira_resposta_registrada'] = int(unicos['Primeira Resposta'].str.strip().eq('').sum())

    # None é o valor que a próxima etapa poderá enviar ao PostgreSQL como NULL.
    chamados = chamados.astype(object).where(chamados.notna(), None).reset_index(drop=True)
    return {'chamados': chamados, 'origens': origens, 'revisao': revisao, 'qualidade': qualidade}


def preparar_lote(pasta):
    dados, _ = carregar_csvs(pasta)
    return transformar(dados)


if __name__ == '__main__':
    lote = preparar_lote(Path(__file__).resolve().parent / 'datas')
    print(json.dumps(lote['qualidade'], ensure_ascii=False, indent=2))
