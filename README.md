# Pipeline ETL - Preços de Petróleo e Combustíveis

Este projeto implementa um pipeline de dados **ETL** (Extração, Transformação e Carga) em Python que unifica os dados de preços médios de combustíveis no Brasil (ANP), a cotação do Dólar Comercial (Banco Central do Brasil) e a cotação internacional do barril de petróleo Brent (EIA) em uma série temporal diária consolidada. 

Os dados resultantes são exportados tanto para um arquivo CSV formatado para o padrão brasileiro quanto para um arquivo de extrato Tableau (`.hyper`).

---

## 📋 Modos de Funcionamento

O script foi projetado para ser eficiente e resiliente a limites de requisição de APIs externas. Existem dois modos de execução:

### 1. Modo Incremental (Padrão)
É a execução padrão do script. Caso o arquivo consolidado `historico_precos_combustiveis.csv` já exista localmente, o pipeline irá trabalhar de forma inteligente:
* **Detecção**: Lê o arquivo local existente e extrai a data mais recente gravada (`max_date_existing`).
* **Download Seletivo**: 
  - Ignora as planilhas históricas antigas da ANP (como as de 2001-2012 e 2004-2012) caso a última data de atualização seja posterior a esses intervalos.
  - Filtra e importa apenas os novos dados da ANP e Brent que sejam posteriores a essa data.
  - Otimiza a busca na API do Banco Central (BCB), requisitando apenas a série do Dólar a partir do ano correspondente à última atualização, reduzindo o tempo de consulta de minutos para segundos.
* **Mesclagem**: Cria um grid diário das datas novas até a data atual, faz a fusão com o histórico antigo e realiza um preenchimento contínuo (`ffill`) global para propagar os preços corretos sobre fins de semana e feriados.
* **Como acionar**:
  ```bash
  python Petroleo.py
  ```

### 2. Modo de Carga Completa (Full Load)
Este modo ignora completamente qualquer dado ou arquivo local preexistente e reconstrói toda a base histórica desde **01/07/2001** até o dia de hoje. É útil se você precisar regerar toda a base de dados por mudanças de colunas ou se os dados locais estiverem corrompidos.
* **Processamento**: Baixa as 3 planilhas da ANP desde 2001, realiza downloads completos do Brent e faz a API do Dólar buscar chunks de 4 anos de 2001 até o ano atual.
* **Como acionar**:
  ```bash
  python Petroleo.py --full
  ```

---

## 🛠️ Arquitetura do Script (`Petroleo.py`)

O código está modularizado nas seguintes funções principais:

* **`download_eia_brent()`**: Baixa a planilha oficial RBRTEd.xls da EIA (U.S. Energy Information Administration) com os preços spot diários de petróleo Brent em Dólares.
* **`download_bcb_usd(start_year)`**: Consulta a API de Séries Temporais do Banco Central do Brasil para obter a taxa comercial do dólar. Faz a paginação histórica em chunks e possui mecanismos automáticos de retry em caso de instabilidade.
* **`download_anp_file(url, label)`**: Baixa as planilhas Excel da ANP e localiza dinamicamente o cabeçalho correto, tratando discrepâncias estruturais comuns entre arquivos históricos antigos e novos.
* **`standardize_anp_df(df)`**: Padroniza os cabeçalhos das colunas da ANP para um formato consolidado (`DATA`, `COMBUSTIVEL`, `PRECO`).
* **`csv_to_hyper(csv_path, hyper_path)`**: Utiliza a biblioteca `pantab` e a API do Tableau Hyper para converter o CSV gerado em um extrato de alta performance `.hyper`, utilizando o esquema `[Extract].[Extract]`.
* **`download_and_process(full_load)`**: Orquestra todo o fluxo, aplicando a estratégia incremental ou carga completa.

---

## 🚀 Requisitos e Execução

### Pré-requisitos
Certifique-se de ter o Python 3.11+ e o ambiente virtual configurados. Instale todas as dependências requeridas utilizando o arquivo `requirements.txt`:

```bash
# Ative o seu ambiente virtual
source venv/bin/activate

# Instale os pacotes necessários
pip install -r requirements.txt
```

### Arquivos de Saída
Após a execução bem-sucedida, os seguintes arquivos serão criados ou atualizados na raiz do projeto:
* `historico_precos_combustiveis.csv`: Arquivo CSV separado por ponto e vírgula (`;`) e com vírgula (`,`) como separador decimal, ideal para ser lido em ferramentas de análise ou Excel.
* `historico_precos_combustiveis.hyper`: Extrato nativo do Tableau pronto para consumo pelo workbook `Combustiveis.twb`.
