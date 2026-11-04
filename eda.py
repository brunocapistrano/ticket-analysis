"""EDA dos CSVs do Znuny. Imprime diagnósticos, sem alterar ou exportar dados."""

import csv
from pathlib import Path
import re

import pandas as pd


CHAVE = 'Número do Chamado'
ORIGEM = '__arquivo_origem'
DATAS = ['Criado', 'Fechado', 'Primeiro Bloqueio', 'Primeira Resposta']
NUMEROS = [
    'Tempo contabilizado', 'Tempo de solução em minutos',
    'Delta de tempo de solução em minutos', 'Primeira Resposta em Minutos',
    'Diferença de Tempo da Primeira Resposta em Minutos',
]
CATEGORIAS = ['Estado', 'Prioridade', 'Fila', 'Bloquear']
FECHADOS = {'fechado com êxito', 'fechado sem êxito'}
ABERTOS = {'aberto', 'novo', 'lembrete de pendente'}
ESTADOS = FECHADOS | ABERTOS | {'agrupado'}
OBRIGATORIAS = {CHAVE, 'Idade', *DATAS, 'Estado', 'Prioridade', 'Fila',
                'Tempo contabilizado', 'Tempo de solução em minutos'}
PRIVADOS = {'Proprietário', 'PrimeiroNome', 'ÚltimoNome', 'ID do Cliente',
            'Nome do Cliente', 'De', 'Assunto'}


def carregar_csvs(pasta):
    """Retorna linhas como texto com origem e uma tabela de cobertura por arquivo."""
    arquivos = sorted(Path(pasta).glob('*.csv'))
    if not arquivos:
        raise FileNotFoundError('Nenhum CSV encontrado na pasta de entrada.')
    bases, cobertura = [], []
    colunas = None
    for numero, arquivo in enumerate(arquivos, 1):
        # Validar a largura evita que uma linha deslocada vire um índice silencioso.
        with arquivo.open(encoding='utf-8-sig', newline='') as entrada:
            leitor = csv.reader(entrada, delimiter=';', strict=True)
            cabecalho = next(leitor, [])
            if not cabecalho or len(cabecalho) != len(set(cabecalho)):
                raise ValueError(f'CSV {numero}: cabeçalho vazio ou com colunas repetidas.')
            if ORIGEM in cabecalho:
                raise ValueError(f'CSV {numero}: nome reservado de coluna de origem.')
            if OBRIGATORIAS - set(cabecalho):
                raise ValueError(f'CSV {numero}: faltam colunas necessárias à análise.')
            if colunas is not None and cabecalho != colunas:
                raise ValueError(f'CSV {numero}: nomes ou ordem das colunas divergentes.')
            colunas = cabecalho
            for linha in leitor:
                if len(linha) != len(cabecalho):
                    raise ValueError(f'CSV {numero}: largura inválida perto da linha {leitor.line_num}.')
        base = pd.read_csv(arquivo, sep=';', dtype=str, encoding='utf-8-sig',
                           keep_default_na=False, skip_blank_lines=False)
        criados = pd.to_datetime(base['Criado'], format='%Y-%m-%d %H:%M:%S', errors='coerce')
        extracao = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{2})-(\d{2})', arquivo.name)
        cobertura.append({
            'arquivo': f'CSV {numero}', 'linhas': len(base),
            'criação mínima': criados.min(), 'criação máxima': criados.max(),
            'extração no nome': ' '.join([extracao[1], f'{extracao[2]}:{extracao[3]}'])
            if extracao else 'não identificada',
        })
        base[ORIGEM] = arquivo.name
        bases.append(base)
    dados = pd.concat(bases, ignore_index=True)
    if dados.empty:
        raise ValueError('Os CSVs possuem cabeçalhos, mas não possuem registros.')
    return dados, pd.DataFrame(cobertura)


def analisar(dados, cobertura):
    """Cria tabelas agregadas e propostas de tratamento; preserva dados recebidos."""
    problemas = []
    tabelas = {'Cobertura dos arquivos': cobertura.copy()}
    colunas = dados.columns.drop(ORIGEM)
    total = len(dados)

    def registrar(codigo, problema, quantidade, denominador, unidade, escopo, regra):
        problemas.append({'código': codigo, 'problema': problema,
                          'quantidade': int(quantidade), 'denominador': int(denominador),
                          'unidade': unidade, 'escopo': escopo, 'regra proposta': regra})

    # 1. As contagens da extração usam linhas, inclusive repetições entre arquivos.
    registrar('arquivos', 'Diferença para os oito CSVs esperados',
              abs(len(cobertura) - 8), 8, 'arquivos', 'extração',
              'Conferir o conjunto esperado; não aceitar apenas porque os cabeçalhos coincidem.')
    registrar('limite', 'Arquivos com exatamente 2.000 linhas',
              cobertura['linhas'].eq(2000).sum(), len(cobertura), 'arquivos', 'extração',
              'Verificar limite ou paginação na origem. A contagem não comprova truncamento.')
    registrar('arquivo_vazio', 'Arquivos sem registros', cobertura['linhas'].eq(0).sum(),
              len(cobertura), 'arquivos', 'extração', 'Confirmar filtros e resultado esperado da exportação.')

    # 2. Uma base temporária de chamados evita contar o mesmo chamado várias vezes.
    chave = dados[CHAVE].str.strip()
    identificados = dados.loc[chave.ne('')].copy()
    identificados[CHAVE] = chave.loc[chave.ne('')]
    por_chamado = identificados.groupby(CHAVE, sort=False)
    campos = [c for c in colunas if c not in {CHAVE, 'Idade'}]
    divergencias = por_chamado[campos].nunique(dropna=False).gt(1)
    ids_conflitantes = divergencias.index[divergencias.any(axis=1)]
    elegiveis = identificados.loc[~identificados[CHAVE].isin(ids_conflitantes)]
    chamados = elegiveis.drop_duplicates(CHAVE).copy()
    n = len(chamados)
    repeticoes = len(identificados) - identificados[CHAVE].nunique()
    resumo = {
        'linhas exportadas': total, 'linhas sem identificador': int(chave.eq('').sum()),
        'identificadores distintos não vazios': identificados[CHAVE].nunique(),
        'repetições excedentes por identificador': repeticoes,
        'cópias excedentes inteiramente iguais': int(dados.duplicated(subset=colunas).sum()),
        'chamados em mais de um arquivo': int(por_chamado[ORIGEM].nunique().gt(1).sum()),
        'chamados com conflito além de Idade': len(ids_conflitantes),
        'linhas excluídas das métricas por conflito': int(identificados[CHAVE].isin(ids_conflitantes).sum()),
        'repetições excedentes dentro do mesmo arquivo': int(identificados.duplicated([ORIGEM, CHAVE]).sum()),
        'chamados elegíveis às métricas': n,
    }
    tabelas['Reconciliação das contagens'] = pd.Series(resumo)
    tabelas['Campos divergentes, sem exibir identificadores'] = divergencias.sum().rename('chamados')
    registrar('id_vazio', 'Identificador vazio', chave.eq('').sum(), total, 'linhas', 'dados brutos',
              'Separar para revisão; não agrupar todos os vazios como um chamado.')
    registrar('id_formato', 'Identificador preenchido fora do padrão numérico',
              (chave.ne('') & ~chave.str.fullmatch(r'\d+')).sum(), total, 'linhas', 'dados brutos',
              'Confirmar formato na origem; preservar como texto e manter zeros iniciais.')
    registrar('duplicatas', 'Repetições excedentes por identificador', repeticoes,
              len(identificados), 'linhas', 'identificadores preenchidos',
              'Deduplicar após analisar conflitos; preservar relação chamado–arquivo de origem.')
    registrar('conflitos', 'Chamados com campos divergentes além de Idade', len(ids_conflitantes),
              identificados[CHAVE].nunique(), 'chamados', 'identificadores distintos',
              'Revisar as versões antes de escolher uma. Estes chamados não entram nas métricas desta EDA.')
    registrar('idade_diverge', 'Chamados cuja Idade varia entre exportações',
              por_chamado['Idade'].nunique().gt(1).sum(), identificados[CHAVE].nunique(),
              'chamados', 'identificadores distintos',
              'Tratar Idade como dependente do instante da extração; não usar a primeira versão como verdade.')

    # 3. Perfil bruto mede problemas sem esconder repetições ou perdas de conversão.
    perfil = []
    for coluna in colunas:
        original = dados[coluna]
        texto = original.str.strip()
        presente = texto.ne('')
        distintos = texto.loc[presente].nunique()
        tipo = ('data e hora' if coluna in DATAS else 'numérico' if coluna in NUMEROS
                else 'categoria' if coluna in CATEGORIAS else 'texto')
        perfil.append({'coluna': coluna, 'tipo proposto': tipo, 'ausentes': int((~presente).sum()),
                       'ausentes (%)': round((~presente).mean() * 100, 2),
                       'distintos sem espaços externos': distintos,
                       'espaços nas extremidades': int(original.ne(texto).sum())})
        registrar(f'ausente:{coluna}', f'Ausências em {coluna}', (~presente).sum(), total,
                  'linhas', 'dados brutos', 'Manter ausência; avaliar obrigatoriedade e relação com o estado antes de preencher.')
        registrar(f'espacos:{coluna}', f'Espaços nas extremidades em {coluna}', original.ne(texto).sum(),
                  total, 'linhas', 'dados brutos', 'Padronizar espaços em campos estruturados; preservar texto livre original.')
        if distintos <= 1:
            registrar(f'sem_variacao:{coluna}', f'Campo sem variação utilizável: {coluna}',
                      presente.sum(), total, 'linhas preenchidas', 'dados brutos',
                      'Registrar limitação; não usar para comparação. Preservar o campo na origem.')
        if coluna in CATEGORIAS:
            variantes = texto.loc[presente].nunique() - texto.loc[presente].str.casefold().nunique()
            registrar(f'variantes:{coluna}', f'Variantes de maiúsculas/minúsculas em {coluna}',
                      variantes, distintos, 'categorias excedentes', 'dados brutos',
                      'Validar um mapa de categorias antes de normalizar.')
    tabelas['Qualidade por coluna, denominador = linhas exportadas'] = pd.DataFrame(perfil)
    registrar('privacidade', 'Linhas com identificadores pessoais ou texto livre',
              dados[[c for c in PRIVADOS if c in dados]].apply(lambda s: s.str.strip().ne('')).any(axis=1).sum(),
              total, 'linhas', 'dados brutos',
              'Restringir acesso ao bruto e selecionar apenas campos necessários na futura base analítica.')

    # 4. Conversões acontecem em cópias, apenas para medir validade e coerência.
    datas = pd.DataFrame(index=chamados.index)
    for coluna in DATAS:
        texto = chamados[coluna].str.strip()
        formato = texto.str.fullmatch(r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}')
        datas[coluna] = pd.to_datetime(texto.where(formato), format='%Y-%m-%d %H:%M:%S', errors='coerce')
        registrar(f'data_invalida:{coluna}', f'Data preenchida inválida em {coluna}',
                  (texto.ne('') & datas[coluna].isna()).sum(), n, 'chamados', 'elegíveis',
                  'Preservar valor original e sinalizar falha de conversão; não confundir com ausência.')
    numeros = {}
    for coluna in NUMEROS:
        if coluna not in chamados:
            continue
        texto = chamados[coluna].str.strip()
        numero = pd.to_numeric(texto, errors='coerce')
        finito = numero.notna() & ~numero.isin([float('inf'), -float('inf')])
        numeros[coluna] = numero.where(finito)
        registrar(f'numero_invalido:{coluna}', f'Número preenchido inválido em {coluna}',
                  (texto.ne('') & ~finito).sum(), n, 'chamados', 'elegíveis',
                  'Confirmar unidade e formato decimal antes de converter; preservar valor original.')
        if coluna in {'Tempo contabilizado', 'Tempo de solução em minutos', 'Primeira Resposta em Minutos'}:
            registrar(f'numero_negativo:{coluna}', f'Tempo negativo em {coluna}', numero.lt(0).sum(),
                      n, 'chamados', 'elegíveis', 'Sinalizar para revisão; não substituir por zero.')
    estado = chamados['Estado'].str.strip().str.casefold()
    fechados = estado.isin(FECHADOS)
    abertos = estado.isin(ABERTOS)
    registrar('estado_desconhecido', 'Estado fora do mapa conhecido', (~estado.isin(ESTADOS)).sum(),
              n, 'chamados', 'elegíveis', 'Confirmar o significado do estado; não assumir que seja aberto.')
    registrar('fechado_sem_data', 'Estado fechado sem data válida de fechamento',
              (fechados & datas['Fechado'].isna()).sum(), n, 'chamados', 'elegíveis',
              'Investigar ausência ou data inválida; não inventar data de fechamento.')
    registrar('aberto_com_data', 'Estado aberto com data válida de fechamento',
              (abertos & datas['Fechado'].notna()).sum(), n, 'chamados', 'elegíveis',
              'Investigar reabertura ou histórico. Não apagar a data automaticamente.')
    registrar('sem_resposta', 'Sem primeira resposta registrada', chamados['Primeira Resposta'].str.strip().eq('').sum(),
              n, 'chamados', 'elegíveis', 'Manter ausência e medir cobertura; ausência do registro não comprova ausência de atendimento.')

    # 5. Durações corridas não representam horas úteis nem cumprimento de SLA.
    tempos, resumo_tempos, extremos = {}, [], []
    for coluna in ['Fechado', 'Primeira Resposta', 'Primeiro Bloqueio']:
        minutos = (datas[coluna] - datas['Criado']).dt.total_seconds().div(60)
        registrar(f'ordem:{coluna}', f'{coluna} anterior à criação', minutos.lt(0).sum(),
                  n, 'chamados', 'elegíveis', 'Sinalizar e excluir somente dos cálculos afetados até revisão.')
        validos = minutos.ge(0)
        if coluna == 'Fechado':
            validos &= fechados
        tempos[coluna] = minutos.where(validos)
        valores = minutos.loc[validos]
        q1, q3 = valores.quantile(.25), valores.quantile(.75)
        limite = q3 + 1.5 * (q3 - q1)
        extremos.append({'intervalo': coluna, 'limite superior IQR (min)': limite,
                         'acima do limite': int(valores.gt(limite).sum()),
                         'amostra válida': len(valores)})
        registrar(f'extremos:{coluna}', f'Intervalos acima de Q3 + 1,5 IQR em {coluna}',
                  valores.gt(limite).sum(), len(valores), 'chamados', 'intervalos válidos',
                  'Investigar cauda longa. Critério estatístico não comprova erro e não autoriza remoção automática.')
        resumo_tempos.append({'intervalo desde criação': coluna, 'elegíveis': n,
                              'com ambas as datas válidas': int(minutos.notna().sum()),
                              'usados na métrica': len(valores),
                              'cobertura (%)': round(len(valores) / n * 100, 2) if n else None,
                              'média (min)': valores.mean(), 'mediana (min)': valores.median(),
                              'p90 (min)': valores.quantile(.90), 'p95 (min)': valores.quantile(.95),
                              'p99 (min)': valores.quantile(.99), 'máximo (min)': valores.max()})
    tabelas['Tempos corridos, fechamento somente para estados fechados'] = pd.DataFrame(resumo_tempos).round(2)
    tabelas['Extremos estatísticos, sem remoção automática'] = pd.DataFrame(extremos).round(2)
    informado = numeros['Tempo de solução em minutos']
    corrido = (datas['Fechado'] - datas['Criado']).dt.total_seconds().div(60)
    comparaveis = informado.ge(0) & corrido.ge(0)
    registrar('duracao_diferente', 'Tempo de solução difere do corrido por mais de um minuto',
              (comparaveis & informado.sub(corrido).abs().gt(1)).sum(), comparaveis.sum(),
              'chamados', 'durações não negativas comparáveis',
              'Confirmar regra do Znuny, pausas e calendário; diferença não comprova erro e não autoriza sobrescrita.')

    # 6. Volumes contam uma vez cada chamado elegível, sem criar ranking de pessoas.
    mes = datas['Criado'].dt.to_period('M')
    mensal = mes.value_counts().sort_index()
    if not mensal.empty:
        mensal = mensal.reindex(pd.period_range(mensal.index.min(), mensal.index.max(), freq='M'), fill_value=0)
    tabelas['Criações por mês, meses extremos podem ser parciais'] = mensal.rename('chamados')
    for coluna in ['Estado', 'Fila', 'Prioridade']:
        contagem = chamados[coluna].str.strip().replace('', '(ausente)').value_counts()
        tabelas[f'Volume por {coluna}'] = pd.DataFrame({'chamados': contagem,
            '% dos elegíveis': contagem.div(n).mul(100).round(2) if n else contagem.astype(float)})
    por_fila = pd.DataFrame({'fila': chamados['Fila'].str.strip().replace('', '(ausente)'),
                            'minutos': tempos['Fechado']})
    tabelas['Fechamento por fila, amostra com intervalo válido'] = por_fila.groupby('fila')['minutos'].agg(
        ['count', 'median', 'mean']).rename(columns={'count': 'amostra', 'median': 'mediana (min)', 'mean': 'média (min)'}).round(2)
    tabelas['Problemas e regras propostas, contagens podem se sobrepor'] = pd.DataFrame(problemas)
    return tabelas


def mostrar_relatorio(tabelas):
    """Mostra somente agregados. Valores pessoais e identificadores não são exibidos."""
    with pd.option_context('display.max_rows', None, 'display.max_columns', None,
                           'display.width', 180, 'display.max_colwidth', None):
        for titulo, tabela in tabelas.items():
            print(f'\n=== {titulo} ===')
            if titulo.startswith('Problemas'):
                tabela = tabela.loc[tabela['quantidade'].gt(0)].reset_index(drop=True)
            print(tabela.to_string(index=not isinstance(tabela.index, pd.RangeIndex)))
    print('\nOs CSVs e os valores originais não foram alterados. Não foi exportada uma base limpa.')
    print('Zeros, ausências e valores inválidos são situações diferentes. Problemas podem se sobrepor.')
    print('As métricas usam somente identificadores preenchidos sem conflitos além de Idade.')
    print('Dados temporários para análise não são regras de limpeza aprovadas.')
    print('Extremos devem ser investigados, não eliminados automaticamente. Os tempos são corridos, não SLA.')
    print('A presença no arquivo de uma pessoa não demonstra autoria, esforço ou responsabilidade exclusiva.')
    print('O recorte reflete o momento das exportações, não o estado atual dos chamados.')
    print('CSV 1, CSV 2 e demais rótulos seguem a ordem alfabética dos arquivos de entrada.')
    print('Pendências: confirmar filtros, período pretendido, limite de exportação, mapa de estados, fuso e definição dos tempos.')


def main(pasta=None):
    pasta = Path(pasta) if pasta is not None else Path(__file__).resolve().parent / 'datas'
    dados, cobertura = carregar_csvs(pasta)
    tabelas = analisar(dados, cobertura)
    mostrar_relatorio(tabelas)
    return tabelas


if __name__ == '__main__':
    main()
