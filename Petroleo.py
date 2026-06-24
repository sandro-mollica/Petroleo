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
    Downloads Europe Brent Spot Price FOB (Monthly) from EIA.
    Returns a DataFrame with columns ['DATA', 'Barril US$'].
    """
    print("Baixando dados do Brent (EIA)...")
    url = "https://www.eia.gov/dnav/pet/hist_xls/RBRTEm.xls"
    try:
        print(f"Baixando dados do Brent (EIA): {url}")
        response = requests.get(url)
        response.raise_for_status()
        
        # Read Excel, Sheet "Data 1", Skip first 2 rows to get header at row 3 (index 2)
        # The file usually has header at row 3 (index 2) for "Date" and "Europe Brent Spot Price FOB (Dollars per Barrel)"
        df = pd.read_excel(io.BytesIO(response.content), sheet_name="Data 1", header=2)
        
        # Rename columns. 
        # Typically columns are like "Date", "Europe Brent Spot Price FOB (Dollars per Barrel)"
        df.columns = ["DATA", "Barril US$"]
        
        # Convert DATA to datetime
        df["DATA"] = pd.to_datetime(df["DATA"])
        
        # Normalize to first day of the month
        df["DATA"] = df["DATA"].apply(lambda x: x.replace(day=1))
        
        print(f"Dados do Brent carregados. Linhas: {len(df)}")
        return df
    except Exception as e:
        print(f"Erro ao baixar dados do Brent: {e}")
        return pd.DataFrame(columns=["DATA", "Barril US$"])

def download_bcb_usd():
    """
    Downloads USD/BRL Exchange Rate (Monthly End of Period) from BCB.
    Series 3696.
    Returns a DataFrame with columns ['DATA', 'US$'].
    Série 10813 mostra os valores diários, com limite de 10 anos.
    https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados?formato=json&dataInicial=22/06/2017&dataFinal=22/06/2026
    """
    print("Baixando dados do Dólar (BCB)...")   
    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.3696/dados?formato=json"
    try:
        print(f"Baixando dados do Dólar (BCB): {url}")
        response = requests.get(url)
        response.raise_for_status()
        
        data = response.json()
        df = pd.DataFrame(data)
        
        # BCB date format is usually DD/MM/YYYY
        df["data"] = pd.to_datetime(df["data"], format="%d/%m/%Y")
        
        # Normalize to first day of month
        df["DATA"] = df["data"].apply(lambda x: x.replace(day=1))
        
        df["US$"] = pd.to_numeric(df["valor"])
        
        df = df[["DATA", "US$"]]
        
        print(f"Dados do Dólar carregados. Linhas: {len(df)}")
        return df
    except Exception as e:
        print(f"Erro ao baixar dados do Dólar: {e}")
        return pd.DataFrame(columns=["DATA", "US$"])

def download_and_process():
    print("Iniciando download e processamento dos dados da ANP...")
    
    # URLs for the data
    url_2001_2012 = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/2001-2012/mensal-brasil-2001-a-2012.xlsx"
    url_2013_present = "https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/mensal/mensal-brasil-desde-jan2013.xlsx"

    dataframes = []

    # Process 2001-2012
    try:
        print(f"Baixando dados de 2001-2012: {url_2001_2012}")
        response = requests.get(url_2001_2012, verify=False)
        response.raise_for_status()
        
        df1 = pd.read_excel(io.BytesIO(response.content))
        
        # Locate the header row containing "MÊS" or "PRODUTO"
        header_row_idx = None
        for i, row in df1.iterrows():
            row_str = row.astype(str).str.upper().tolist()
            if "MÊS" in row_str and "PRODUTO" in row_str:
                header_row_idx = i
                break
        
        if header_row_idx is not None:
             df1 = pd.read_excel(io.BytesIO(response.content), header=header_row_idx+1)
        
        print(f"Dados 2001-2012 carregados. Linhas: {len(df1)}")
        dataframes.append(df1)

    except Exception as e:
        print(f"Erro ao baixar 2001-2012: {e}")

    # Process 2013-Present
    try:
        print(f"Baixando dados de 2013-Presente: {url_2013_present}")
        response = requests.get(url_2013_present, verify=False)
        response.raise_for_status()
        
        df2 = pd.read_excel(io.BytesIO(response.content))

        # Locate header row
        header_row_idx = None
        for i, row in df2.iterrows():
            row_str = row.astype(str).str.upper().tolist()
            if "MÊS" in row_str and "PRODUTO" in row_str:
                header_row_idx = i
                break
        
        if header_row_idx is not None:
             df2 = pd.read_excel(io.BytesIO(response.content), header=header_row_idx+1)

        print(f"Dados 2013-Presente carregados. Linhas: {len(df2)}")
        dataframes.append(df2)
        
    except Exception as e:
        print(f"Erro ao baixar 2013-Presente: {e}")

    # Combine dataframes
    if not dataframes:
        print("Nenhum dado foi carregado.")
        return

    # Normalize columns and clean data
    full_df = pd.DataFrame()
    for df in dataframes:
        # Standardize columns per DF
        df.columns = [c.upper().strip() for c in df.columns]
        
        # Rename price column
        if "PRECO MÉDIO REVENDA" in df.columns:
            df = df.rename(columns={"PRECO MÉDIO REVENDA": "PRECO"})
        elif "PREÇO MÉDIO REVENDA" in df.columns:
            df = df.rename(columns={"PREÇO MÉDIO REVENDA": "PRECO"})
            
        # Rename others
        df = df.rename(columns={
            "MÊS": "DATA",
            "PRODUTO": "COMBUSTIVEL"
        })
        
        # Keep only needed columns to ensure clean concat
        if "PRECO" in df.columns and "DATA" in df.columns and "COMBUSTIVEL" in df.columns:
            full_df = pd.concat([full_df, df[["DATA", "COMBUSTIVEL", "PRECO"]]], ignore_index=True)
    
    # Normalize Product Names
    full_df['COMBUSTIVEL'] = full_df['COMBUSTIVEL'].replace({
        'OLEO DIESEL': 'ÓLEO DIESEL',
        'OLEO DIESEL S10': 'ÓLEO DIESEL S10'
    })
    
    # Target products
    target_products = ["GASOLINA COMUM", "ETANOL HIDRATADO", "ÓLEO DIESEL", "GLP", "ÓLEO DIESEL S10"]
    
    full_df = full_df[full_df['COMBUSTIVEL'].isin(target_products)]
    
    print("Processando e formatando dados...")
    
    # Pivot table
    final_df = full_df.pivot_table(index='DATA', columns='COMBUSTIVEL', values='PRECO', aggfunc='first')
    
    # Reset index to make DATA a column again
    final_df.reset_index(inplace=True)
    
    # Ensure DATA is datetime for merging
    final_df["DATA"] = pd.to_datetime(final_df["DATA"])
    
    # --- Integration of External Data ---
    
    # 1. Brent Oil Price
    df_brent = download_eia_brent()
    if not df_brent.empty:
        final_df = pd.merge(final_df, df_brent, on="DATA", how="left")
        
    # 2. USD Exchange Rate
    df_usd = download_bcb_usd()
    if not df_usd.empty:
        final_df = pd.merge(final_df, df_usd, on="DATA", how="left")
        
    # Calcular preço do barril em BRL
    if "Barril US$" in final_df.columns and "US$" in final_df.columns:
        final_df["Barril BRL"] = final_df["Barril US$"] * final_df["US$"]
        
    # --- End Integration ---
    
    # Sort by Date
    final_df = final_df.sort_values(by='DATA')
    
    # Save to CSV
    output_files = "historico_precos_combustiveis.csv"
    final_df.to_csv(output_files, index=False, sep=';', decimal=',')
    print(f"Arquivo salvo com sucesso: {output_files}")
    print("Amostra dos dados (Início):")
    print(final_df.head())
    print("Amostra dos dados (Fim):")
    print(final_df.tail())

if __name__ == "__main__":
    download_and_process()
