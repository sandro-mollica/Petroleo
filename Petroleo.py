"""
Script de Integração e Processamento de Preços de Petróleo e Combustíveis.

Este script realiza o pipeline ETL completo:
1. Extração: Baixa os preços diários de fechamento do barril de petróleo Brent (EIA),
   as taxas de câmbio comerciais diárias do Dólar para Real (Banco Central do Brasil),
   e a série histórica de preços nacionais de combustíveis (ANP) mensais/semanais.
2. Transformação: Normaliza os dados dos combustíveis de interesse, pivota as séries de
   preços por combustível, cria um grid diário de datas unificado, preenche lacunas
   temporais (forward fill) e calcula o preço diário do barril em Reais (BRL).
3. Carga: Salva o DataFrame consolidado em um arquivo CSV de saída delimitado por ';'
   e gera um arquivo correspondente no formato Tableau Extrato (.hyper) para fácil
   visualização no Tableau Workbook.
"""

import pandas as pd
import requests
import io
import os 

# Suppress InsecureRequestWarning
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from datetime import datetime
print('Iniciando o programa', flush=True)

def download_eia_brent():
    """
    Realiza o download dos dados diários do Brent Spot Price FOB da EIA (Energy Information Administration).
    
    Esta função baixa a planilha oficial RBRTEd.xls que contém o histórico diário de cotações
    do petróleo Brent. Converte a coluna de data para datetime e renomeia as colunas.
    
    Retorna:
        pd.DataFrame: DataFrame contendo as colunas ['DATA', 'Barril US$'].
    """
    print("Baixando dados do Brent diário (EIA)...")
    url = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls"
    try:
        print(f"Baixando dados do Brent diário (EIA): {url}")
        response = requests.get(url)
        response.raise_for_status()
        
        # Lê o arquivo Excel, aba "Data 1".
        # Pula as duas primeiras linhas pois o cabeçalho real ("Date" e o preço) está na linha 3 (índice 2).
        df = pd.read_excel(io.BytesIO(response.content), sheet_name="Data 1", header=2)
        
        # Renomeia as colunas para o padrão do projeto.
        df.columns = ["DATA", "Barril US$"]
        
        # Converte as datas para o formato datetime do Pandas.
        df["DATA"] = pd.to_datetime(df["DATA"])
        
        print(f"Dados do Brent diários carregados. Linhas: {len(df)}")
        return df
    except Exception as e:
        print(f"Erro ao baixar dados do Brent diários: {e}")
        return pd.DataFrame(columns=["DATA", "Barril US$"])

def download_bcb_usd(start_year=2001):
    """
    Realiza o download das taxas de câmbio diárias do Dólar Comercial (venda) do Banco Central do Brasil.
    Série SGS: 10813.
    
    Como o servidor da API do Banco Central impõe limites de cotação e retorna erros 502/504 (Bad Gateway) 
    para intervalos muito longos, a busca histórica é segmentada em lotes (chunks) de 4 anos e conta
    com um mecanismo de repetição automática (retry) em caso de erro temporário.
    
    Parâmetros:
        start_year (int): Ano inicial para buscar as cotações (padrão 2001).
        
    Retorna:
        pd.DataFrame: DataFrame contendo as colunas ['DATA', 'US$'].
    """
    import time
    print(f"Baixando dados do Dólar diário (BCB) a partir de {start_year}...")
    start_year = start_year
    end_year = datetime.today().year
    
    all_data = []
    # Busca histórica dividida em intervalos de 4 anos para garantir estabilidade e evitar timeouts da API.
    for year in range(start_year, end_year + 1, 4):
        chunk_start = f"01/01/{year}"
        chunk_end = f"31/12/{min(year + 3, end_year)}"
        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados?formato=json&dataInicial={chunk_start}&dataFinal={chunk_end}"
        
        # Mecanismo de re-tentativa (até 3 tentativas por lote com 2 segundos de pausa em caso de falha).
        for attempt in range(1, 4):
            try:
                print(f"Baixando chunk do Dólar ({year} a {min(year+3, end_year)}) - Tentativa {attempt}: {url}")
                response = requests.get(url, timeout=30)
                response.raise_for_status()
                chunk_data = response.json()
                all_data.extend(chunk_data)
                break  # Sucesso, sai do loop de tentativas para este lote.
            except Exception as e:
                print(f"Erro na tentativa {attempt} para chunk {year}-{min(year+3, end_year)}: {e}")
                if attempt < 3:
                    time.sleep(2)
                else:
                    print(f"Falha definitiva no chunk {year}-{min(year+3, end_year)} após 3 tentativas.")
            
    if not all_data:
        return pd.DataFrame(columns=["DATA", "US$"])
        
    try:
        df = pd.DataFrame(all_data)
        
        # A API do BCB retorna datas como DD/MM/AAAA.
        df["DATA"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        df["US$"] = pd.to_numeric(df["valor"])
        df = df[["DATA", "US$"]]
        
        # Remove eventuais duplicados para manter integridade das datas.
        df = df.drop_duplicates(subset=["DATA"])
        
        print(f"Dados do Dólar diário carregados. Linhas: {len(df)}")
        return df
    except Exception as e:
        print(f"Erro ao processar dados do Dólar: {e}")
        return pd.DataFrame(columns=["DATA", "US$"])

def download_anp_file(url, label):
    """
    Faz o download de um arquivo Excel de preços médios da ANP e localiza o cabeçalho dinamicamente.
    
    Como as planilhas históricas da ANP variam em estrutura (com diferentes linhas de metadados e notas antes
    do cabeçalho real), esta função varre as primeiras linhas procurando os termos chaves 'PRODUTO' e
    ('MÊS' ou 'DATA INICIAL'). Uma vez encontrada a linha do cabeçalho, carrega a planilha a partir dali.
    
    Parâmetros:
        url (str): Link direto de download do arquivo Excel (.xlsx).
        label (str): Nome amigável do arquivo para logging (ex: "Semanal 2013-Presente").
        
    Retorna:
        pd.DataFrame: DataFrame bruto extraído do Excel.
    """
    print(f"Baixando dados da ANP ({label})...")
    try:
        print(f"URL: {url}")
        response = requests.get(url, verify=False)
        response.raise_for_status()
        
        # Lê a planilha bruta de forma inicial.
        df_raw = pd.read_excel(io.BytesIO(response.content))
        
        # Varre as linhas iniciais para encontrar onde o cabeçalho real se inicia.
        header_row_idx = None
        for i, row in df_raw.iterrows():
            row_str = [str(x).upper().strip() for x in row.tolist()]
            # Identifica a linha que contém "PRODUTO" e informações de data ("MÊS" ou "DATA INICIAL").
            if ("MÊS" in row_str or "DATA INICIAL" in row_str) and "PRODUTO" in row_str:
                header_row_idx = i
                break
                
        # Se encontrou, recarrega a planilha definindo a linha correta como cabeçalho.
        if header_row_idx is not None:
            df = pd.read_excel(io.BytesIO(response.content), header=header_row_idx+1)
        else:
            df = df_raw
            
        print(f"Dados ({label}) carregados. Linhas: {len(df)}")
        return df
    except Exception as e:
        print(f"Erro ao baixar dados da ANP ({label}): {e}")
        return pd.DataFrame()

def standardize_anp_df(df):
    """
    Padroniza o DataFrame da ANP para um formato comum com as colunas ['DATA', 'COMBUSTIVEL', 'PRECO'].
    
    Esta função:
    1. Padroniza os cabeçalhos para caixa alta e sem espaços em branco nas pontas.
    2. Traduz colunas de data ('MÊS' ou 'DATA INICIAL') para 'DATA'.
    3. Traduz colunas de preço ('PREÇO MÉDIO REVENDA' ou 'PRECO...') para 'PRECO'.
    4. Converte a coluna de data para datetime do Pandas.
    
    Parâmetros:
        df (pd.DataFrame): DataFrame bruto retornado do download.
        
    Retorna:
        pd.DataFrame: DataFrame padronizado com as colunas ['DATA', 'COMBUSTIVEL', 'PRECO'].
    """
    if df.empty:
        return df
    
    # Padroniza as colunas em maiúsculo e remove espaçamentos.
    df.columns = [str(c).upper().strip() for c in df.columns]
    
    # Renomeia a coluna temporal para DATA.
    if "MÊS" in df.columns:
        df = df.rename(columns={"MÊS": "DATA"})
    elif "DATA INICIAL" in df.columns:
        df = df.rename(columns={"DATA INICIAL": "DATA"})
        
    # Renomeia a coluna de preço médio para PRECO.
    if "PRECO MÉDIO REVENDA" in df.columns:
        df = df.rename(columns={"PRECO MÉDIO REVENDA": "PRECO"})
    elif "PREÇO MÉDIO REVENDA" in df.columns:
        df = df.rename(columns={"PREÇO MÉDIO REVENDA": "PRECO"})
        
    # Renomeia o produto para COMBUSTIVEL.
    df = df.rename(columns={"PRODUTO": "COMBUSTIVEL"})
    
    # Mantém apenas as colunas necessárias e converte a data para datetime.
    if "DATA" in df.columns and "COMBUSTIVEL" in df.columns and "PRECO" in df.columns:
        df = df[["DATA", "COMBUSTIVEL", "PRECO"]]
        df["DATA"] = pd.to_datetime(df["DATA"])
        return df
    return pd.DataFrame()

def csv_to_hyper(csv_path, hyper_path):
    """
    Lê o arquivo CSV consolidado e o converte para o formato .hyper do Tableau.
    
    Esta rotina lê o CSV respeitando o separador ';' e a vírgula para números decimais.
    Em seguida, converte a coluna DATA em datetime e salva o extrato no formato Hyper,
    utilizando o esquema 'Extract' e a tabela 'Extract' exigidos pelo Tableau Workbook.
    
    Parâmetros:
        csv_path (str): Caminho para o arquivo CSV de entrada.
        hyper_path (str): Caminho de saída onde o arquivo .hyper será criado.
    """
    print(f"Iniciando a conversão de {csv_path} para {hyper_path}...")
    try:
        import pantab
        from tableauhyperapi import TableName
        
        # Lê o CSV respeitando o delimitador de ponto e vírgula e a vírgula para decimais
        df = pd.read_csv(csv_path, sep=';', decimal=',')
        
        # Converte a coluna DATA para datetime
        df['DATA'] = pd.to_datetime(df['DATA'])
        
        # Define a tabela no esquema 'Extract' (padrão de extração do Tableau)
        table = TableName("Extract", "Extract")
        
        # Salva o DataFrame no formato .hyper
        pantab.frame_to_hyper(df, hyper_path, table=table)
        print(f"Arquivo .hyper gerado com sucesso em: {hyper_path}")
        
    except ImportError:
        print("Erro: As dependências 'pantab' ou 'tableauhyperapi' não estão instaladas.")
        print("Por favor, execute: pip install pantab tableauhyperapi")
    except Exception as e:
        print(f"Erro ao converter CSV para .hyper: {e}")

def download_and_process(full_load=False):
    """
    Função principal que coordena o fluxo ETL (Extração, Transformação e Carga) dos dados.
    Suporta execução incremental por padrão ou carga completa (full load).
    
    Parâmetros:
        full_load (bool): Se True, força a carga completa de todo o histórico desde 2001.
    """
    output_files = "historico_precos_combustiveis.csv"
    max_date_existing = None
    df_existing = None
    
    # Passo 1: Verificar se existe histórico local para carga incremental
    if not full_load and os.path.exists(output_files):
        try:
            print(f"Arquivo existente encontrado: {output_files}. Lendo histórico para carga incremental...")
            df_existing = pd.read_csv(output_files, sep=';', decimal=',')
            df_existing["DATA"] = pd.to_datetime(df_existing["DATA"])
            max_date_existing = df_existing["DATA"].max()
            print(f"Maior data encontrada no histórico: {max_date_existing.strftime('%Y-%m-%d')}")
        except Exception as e:
            print(f"Erro ao ler histórico existente ({e}). Executando carga completa por segurança.")
            max_date_existing = None
            df_existing = None
            
    if max_date_existing is None:
        print("Executando carga completa (full load) desde 2001...")
    else:
        print(f"Executando carga incremental a partir de: {max_date_existing.strftime('%Y-%m-%d')}")
        
    # Links de download da ANP (Série mensal para os anos iniciais e série semanal a partir de 2004).
    url_mensal_2001_2012 = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/2001-2012/mensal-brasil-2001-a-2012.xlsx"
    url_semanal_2004_2012 = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/2001-2012/semanal-brasil-2004-a-2012.xlsx"
    url_semanal_2013_present = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/semanal/semanal-brasil-desde-2013.xlsx"

    # Passo 2: Download inteligente dos arquivos de combustíveis da ANP
    df_mensal_std = pd.DataFrame()
    df_semanal_1_std = pd.DataFrame()
    df_semanal_2_std = pd.DataFrame()
    
    if max_date_existing is None or max_date_existing < pd.to_datetime("2004-05-09"):
        df_mensal = download_anp_file(url_mensal_2001_2012, "Mensal 2001-2012")
        df_mensal_std = standardize_anp_df(df_mensal)
        if not df_mensal_std.empty:
            df_mensal_std = df_mensal_std[df_mensal_std["DATA"] < pd.to_datetime("2004-05-09")]
            if max_date_existing is not None:
                df_mensal_std = df_mensal_std[df_mensal_std["DATA"] > max_date_existing]

    if max_date_existing is None or max_date_existing < pd.to_datetime("2013-01-01"):
        df_semanal_1 = download_anp_file(url_semanal_2004_2012, "Semanal 2004-2012")
        df_semanal_1_std = standardize_anp_df(df_semanal_1)
        if not df_semanal_1_std.empty and max_date_existing is not None:
            df_semanal_1_std = df_semanal_1_std[df_semanal_1_std["DATA"] > max_date_existing]

    if max_date_existing is None or max_date_existing < datetime.today():
        df_semanal_2 = download_anp_file(url_semanal_2013_present, "Semanal 2013-Presente")
        df_semanal_2_std = standardize_anp_df(df_semanal_2)
        if not df_semanal_2_std.empty and max_date_existing is not None:
            df_semanal_2_std = df_semanal_2_std[df_semanal_2_std["DATA"] > max_date_existing]

    # Combina os DataFrames da ANP em uma base única de novos combustíveis
    dataframes = [df_mensal_std, df_semanal_1_std, df_semanal_2_std]
    dataframes = [d for d in dataframes if not d.empty]
    
    final_df = pd.DataFrame()
    if dataframes:
        full_df = pd.concat(dataframes, ignore_index=True)
        
        # Normaliza a nomenclatura de alguns combustíveis para compatibilidade histórica.
        full_df['COMBUSTIVEL'] = full_df['COMBUSTIVEL'].replace({
            'OLEO DIESEL': 'ÓLEO DIESEL',
            'OLEO DIESEL S10': 'ÓLEO DIESEL S10'
        })
        
        # Filtra apenas os combustíveis de interesse no projeto.
        target_products = ["GASOLINA COMUM", "ETANOL HIDRATADO", "ÓLEO DIESEL", "GLP", "ÓLEO DIESEL S10"]
        full_df = full_df[full_df['COMBUSTIVEL'].isin(target_products)]
        
        if not full_df.empty:
            print("Processando e formatando novos dados da ANP...")
            final_df = full_df.pivot_table(index='DATA', columns='COMBUSTIVEL', values='PRECO', aggfunc='first')
            final_df.reset_index(inplace=True)
            final_df["DATA"] = pd.to_datetime(final_df["DATA"])

    # --- Integração de Fontes Externas Diárias ---
    
    # 1. Busca os dados diários do preço do barril de petróleo Brent (em USD)
    df_brent = download_eia_brent()
    if not df_brent.empty and max_date_existing is not None:
        df_brent = df_brent[df_brent["DATA"] > max_date_existing]
        
    # 2. Busca a taxa de câmbio diária do Dólar Comercial (compra)
    start_year_usd = 2001 if max_date_existing is None else max_date_existing.year
    df_usd = download_bcb_usd(start_year=start_year_usd)
    if not df_usd.empty and max_date_existing is not None:
        df_usd = df_usd[df_usd["DATA"] > max_date_existing]
        
    # Define a data limite da análise
    end_date = datetime.today()
    if not df_brent.empty:
        end_date = max(end_date, df_brent["DATA"].max())
    if not df_usd.empty:
        end_date = max(end_date, df_usd["DATA"].max())
        
    # Define o início do novo período de grid
    if max_date_existing is not None:
        start_date = max_date_existing + pd.Timedelta(days=1)
    else:
        start_date = final_df["DATA"].min() if not final_df.empty else pd.to_datetime("2001-07-01")

    # Verifica se há novas datas a processar
    if start_date <= end_date:
        print(f"Criando grid diário de {start_date.strftime('%Y-%m-%d')} até {end_date.strftime('%Y-%m-%d')}...")
        daily_df = pd.DataFrame({"DATA": pd.date_range(start=start_date, end=end_date, freq="D")})
        
        # Mescla o Brent diário no grid e preenche finais de semana e feriados (ffill).
        if not df_brent.empty:
            daily_df = pd.merge(daily_df, df_brent, on="DATA", how="left")
            daily_df["Barril US$"] = daily_df["Barril US$"].ffill()
            
        # Mescla o Dólar diário no grid e preenche lacunas como finais de semana e feriados (ffill).
        if not df_usd.empty:
            daily_df = pd.merge(daily_df, df_usd, on="DATA", how="left")
            daily_df["US$"] = daily_df["US$"].ffill()
            
        # Mescla os novos preços de combustíveis da ANP e aplica forward fill (ffill).
        if not final_df.empty:
            daily_df = pd.merge(daily_df, final_df, on="DATA", how="left")
            fuel_cols = [c for c in final_df.columns if c != "DATA"]
            daily_df[fuel_cols] = daily_df[fuel_cols].ffill()
            
        # Combina o histórico com os novos dados
        if df_existing is not None:
            print("Concatenando novos dados ao histórico existente...")
            daily_df = pd.concat([df_existing, daily_df], ignore_index=True)
            
        # Ordena a base cronologicamente.
        daily_df = daily_df.sort_values(by='DATA')
        
        # Reaplica forward fill (ffill) global para propagar os valores históricos sobre o novo grid
        columns_to_ffill = ["Barril US$", "US$", "ETANOL HIDRATADO", "GASOLINA COMUM", "GLP", "ÓLEO DIESEL", "ÓLEO DIESEL S10"]
        columns_to_ffill = [c for c in columns_to_ffill if c in daily_df.columns]
        daily_df[columns_to_ffill] = daily_df[columns_to_ffill].ffill()
        
        # Calcula o preço do barril de Brent em Reais (BRL) baseado nas cotações diárias.
        if "Barril US$" in daily_df.columns and "US$" in daily_df.columns:
            daily_df["Barril BRL"] = daily_df["Barril US$"] * daily_df["US$"]
            
        # Salva os dados consolidados diários em arquivo CSV.
        daily_df.to_csv(output_files, index=False, sep=';', decimal=',')
        print(f"Arquivo salvo com sucesso: {output_files}")
        
        # Gera o arquivo .hyper com base no CSV recém-salvo
        hyper_file = "historico_precos_combustiveis.hyper"
        csv_to_hyper(output_files, hyper_file)
    else:
        print("Nenhum dado novo para processar. A base local já está atualizada.")
        daily_df = df_existing
        
    if daily_df is not None and not daily_df.empty:
        print("Amostra dos dados (Início):")
        print(daily_df.head())
        print("Amostra dos dados (Fim):")
        print(daily_df.tail())

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Pipeline ETL de Preços de Petróleo e Combustíveis."
    )
    parser.add_argument(
        "--full", 
        action="store_true", 
        help="Força a execução de uma carga histórica completa (full load) ignorando o cache local."
    )
    
    args = parser.parse_args()
    download_and_process(full_load=args.full)
