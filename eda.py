from pathlib import Path

import pandas as pd


pd.set_option('display.max_columns', None)
pd.set_option('display.width', 160)


# 1. Encontrar todos os CSVs
pasta_dados = Path(__file__).resolve().parent / 'datas'

arquivos = sorted(pasta_dados.glob('*.csv'))

if not arquivos:
    raise FileNotFoundError(f'Nenhum CSV encontrado em {pasta_dados}')
else:
    for arquivo in arquivos:
        print(arquivo.name)


# 2. Comparar as colunas dos CSVs
bases = []
for arquivo in arquivos:
    base = pd.read_csv(arquivo, sep=';', dtype=str, encoding='utf-8-sig')

    if bases and not base.columns.equals(bases[0].columns):
        raise ValueError(f'Colunas diferentes no arquivo {arquivo.name} em comparação com {arquivos[0].name}')
    bases.append(base)

print('Todos os arquivos possuem as mesmas colunas.')

