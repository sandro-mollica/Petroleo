# Fontes de Dados do Projeto

Este documento detalha as fontes de dados utilizadas pelo script de integração de preços de petróleo e combustíveis.

---

## 1. Preços Médios de Combustíveis (ANP)
Os preços médios de combustíveis no Brasil são obtidos do **Sistema de Levantamento de Preços da ANP** (Agência Nacional do Petróleo, Gás Natural e Biocombustíveis).

*   **Combustíveis Monitorados**: 
    *   Gasolina Comum (R$/l)
    *   Etanol Hidratado (R$/l)
    *   Óleo Diesel (R$/l)
    *   Óleo Diesel S10 (R$/l)
    *   GLP - Gás de Cozinha (R$/13kg)
*   **Frequência e Abrangência**:
    *   **Julho/2001 a Abril/2004**: Dados consolidados em frequência **mensal** (médias nacionais).
    *   **Maio/2004 ao Presente**: Dados consolidados em frequência **semanal** (médias nacionais coletadas semanalmente de domingo a sábado).
*   **Links Oficiais de Download**:
    *   [Mensal Brasil (2001-2012)](https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/2001-2012/mensal-brasil-2001-a-2012.xlsx)
    *   [Semanal Brasil (2004-2012)](https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/2001-2012/semanal-brasil-2004-a-2012.xlsx)
    *   [Semanal Brasil (2013-Presente)](https://www.gov.br/anp/pt-br/assuntos/precos-e-defesa-da-concorrencia/precos/precos-revenda-e-de-distribuicao-combustiveis/shlp/semanal/semanal-brasil-desde-2013.xlsx)
*   **Estratégia de Integração**: A série mensal é filtrada para conter apenas os registros anteriores a 09/05/2004. A partir desta data, a série semanal é priorizada. No grid diário, os preços são propagados dia a dia usando *forward fill* (`ffill`) até a divulgação do novo período.

---

## 2. Preço Spot do Petróleo Brent (EIA)
O preço spot do barril de petróleo cru tipo Europe Brent (FOB) em Dólares americanos é coletado diretamente da **EIA** (U.S. Energy Information Administration).

*   **Frequência**: Diária (dias úteis de negociação internacional).
*   **Link Oficial de Download**:
    *   [EIA Europe Brent Spot Price FOB (Daily)](https://www.eia.gov/dnav/pet/hist_xls/RBRTEd.xls) (Planilha Excel, aba `Data 1`).
*   **Estratégia de Integração**: Como o mercado não funciona aos sábados, domingos e feriados internacionais, as lacunas são preenchidas com o valor da última cotação útil disponível (*forward fill*).

---

## 3. Taxa de Câmbio Dólar Comercial (Banco Central do Brasil)
A taxa de conversão diária de venda de Dólar Americano (USD) para Real Brasileiro (BRL) é consultada a partir da API oficial do **SGS** (Sistema Gerenciador de Séries Temporais) do Banco Central do Brasil.

*   **Código da Série (SGS)**: `10813` (Taxa de câmbio - Livre - Dólar americano - Compra).
*   **Frequência**: Diária (dias úteis bancários no Brasil).
*   **Endpoint da API**:
    *   `https://api.bcb.gov.br/dados/serie/bcdata.sgs.10813/dados?formato=json`
*   **Estratégia de Integração**: A consulta é segmentada em lotes de 4 anos e utiliza tentativas automáticas em caso de falha de conexão. Os finais de semana e feriados nacionais são preenchidos repetindo o último câmbio útil registrado (*forward fill*).
