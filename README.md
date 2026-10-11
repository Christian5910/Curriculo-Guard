# 🛡️ Currículo Guard

**Uma camada de inspeção entre o currículo em PDF e a avaliação automatizada.**

O Currículo Guard é um aplicativo desktop em Python que examina currículos antes de liberar seu texto para outros sistemas. Ele reúne filtragem visual, sinais de possíveis instruções dirigidas à IA e uma fila de revisão humana, com critérios configuráveis e decisões documentadas.

O objetivo é tornar a triagem documental mais transparente: mostrar **o que foi sinalizado, por qual motivo e quem revisou**, preservando o arquivo original.

> “Aprovado” significa aprovação documental nas verificações habilitadas. O aplicativo não avalia a qualificação profissional, não decide contratações e não garante a detecção de toda injeção de prompt.

## ✨ O que ele faz

- **Filtra conteúdo suspeito:** fontes pequenas, contraste baixo, texto invisível ou semitransparente e possíveis sobreposições.
- **Considera o DPI corretamente:** converte tamanho da fonte em pontos para pixels usando um DPI de referência configurável.
- **Procura instruções dirigidas à IA:** padrões de manipulação de avaliação, troca de papel e possível exfiltração, inclusive em metadados, anotações e formulários.
- **Inspeciona estrutura do PDF:** sinaliza ações ativas, anexos, camadas opcionais, controles Unicode e texto fora da área visível.
- **Organiza arquivos:** separa documentos por destino sem apagar os originais de entrada.
- **Inclui revisão humana:** busca, filtros, prévia paginada, justificativa obrigatória e histórico de decisões.
- **Confere integridade:** verifica o SHA-256 antes da revisão e ao copiar o documento.
- **Exporta um inventário CSV:** sem incluir o texto integral dos currículos.

## 🚀 Começar

### Requisitos

- Python **3.11 ou superior**.
- Tkinter para a interface gráfica.
- Dependências indicadas em `requirements.txt`.

Baixe e extraia o projeto ou clone o repositório. No terminal, entre na pasta que contém `app.py`.

### Windows — PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe app.py
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Tkinter costuma acompanhar a instalação oficial do Python no Windows. No Linux, pode ser necessário instalar o pacote de Tkinter da distribuição, como `python3-tk` no Ubuntu/Debian.

**Mantenha `app.py`, `engine.py`, `workflow.py` e `review_ui.py` na mesma pasta.**

## 🧭 Uma interface, cinco abas

| Aba | Controles disponíveis |
| --- | --- |
| **Entrada** | Pasta local, URL, saída, subpastas, reanálise, páginas e tempo máximo. |
| **Verificações** | Ativar filtros; ajustar DPI, fonte mínima, contraste, opacidade e cobertura. |
| **Destinos** | Definir revisão ou bloqueio por regra; habilitar bloqueio automático; criar pastas extras. |
| **Revisão humana** | Buscar, ver alertas e páginas, registrar decisão, liberar ou revogar texto e exportar CSV. |
| **Como funciona** | Consultar o significado das classificações e os limites da análise. |

As configurações podem ser salvas e carregadas em JSON. O lote mostra progresso, permite interrupção e processa cada PDF em subprocesso com limite de tempo.

## 📂 Como os arquivos são organizados

| Pasta | Significado |
| --- | --- |
| `aprovados` | Nenhum alerta nas verificações ativas, ou liberação documental por um revisor. |
| `verificacao_humana` | Documento sinalizado que precisa de conferência. |
| `rejeitados` | Documento bloqueado da ingestão automática conforme as regras ou uma revisão. |
| `quarentena` | Falha de processamento, arquivo inválido ou limite excedido. É reanalisado na próxima execução. |
| `duplicados` | Conteúdo com SHA-256 já analisado (aprovados, verificação humana ou rejeitados). |
| `originais` | Downloads preservados. |
| `relatorios` | Evidências e histórico em JSON; TXT somente para documentos liberados. |

Pastas adicionais servem para organização manual. Reanálises geram avaliações independentes, sem sobrescrever nem revogar automaticamente decisões anteriores.

## 🌐 Entrada pela internet

Informe uma URL HTTPS direta de PDF ou uma URL terminada em `.json` com um manifesto:

```json
[
  "https://exemplo.com/curriculos/documento-01.pdf",
  "https://exemplo.com/curriculos/documento-02.pdf"
]
```

O manifesto aceita até 100 URLs. O app não raspa páginas nem acessa pastas autenticadas. Destinos privados e redirecionamentos são bloqueados. Downloads são gravados em temporários e só publicados após a validação inicial.

## 🔎 DPI e critérios visuais

A fonte vetorial de um PDF é medida em pontos; ela não tem um DPI único. A conversão usada é:

```text
tamanho_px = tamanho_em_pontos × DPI_referencia / 72
```

A 96 DPI, uma fonte de 6 pontos corresponde a 8 pixels. O **DPI de renderização** controla a imagem usada na estimativa de contraste; ele não altera o limite definido pelo DPI de referência. O contraste mínimo padrão é **2,0:1** (a versão 2.0 usava 1,2:1, permissivo demais para texto quase invisível).

O fundo é medido pixel a pixel numa renderização da própria página sem texto, dentro do retângulo de cada trecho; se essa renderização falhar, usa-se uma estimativa pela região ao redor. A mesma comparação (página com e sem texto) verifica se cada trecho deixou tinta visível, o que pega texto invisível por cor igual ao fundo, modo de mesclagem ou padrão de preenchimento, mesmo quando a cor declarada parece legível. Trechos cujo fundo torna o texto ilegível em boa parte da área são excluídos e revisados; fundos parcialmente problemáticos (por exemplo, texto claro sobre foto) seguem para revisão. Sobreposição é calculada por retângulos e indica suspeita, não uma prova de ocultação.

## 🧪 Testes

Com as dependências instaladas:

```bash
python -m unittest discover -v
```

A versão 2.4 passou por **73 testes automatizados**, cobrindo filtragem, DPI, contraste contra o fundo real (incluindo texto sobre caixa do mesmo tom, réguas e selos), cobertura fragmentada, gradientes, páginas rotacionadas, frases de injeção (corpus com casos positivos e negativos), conteúdo auxiliar, Unicode, persistência, revisão, integridade, quarentena, limites de tempo, prévia PNG, CSV e downloads simulados. O motor de análise importa e roda sem Tkinter.

A interface ainda não foi validada visualmente no ambiente de desenvolvimento. Downloads foram testados com respostas simuladas, não com um servidor externo real.

## ⚠️ Limites que fazem parte do projeto

- A detecção é **heurística**: pode produzir falsos positivos e falsos negativos.
- A detecção de frases de injeção cobre formulações comuns em português e inglês. Em um conjunto de 30 frases novas, escritas depois dos padrões, detectou 22 (73%); em 40 frases legítimas de currículo, nenhuma foi sinalizada. Variações criativas, outros idiomas e paráfrases passam.
- Não há OCR integrado; PDFs escaneados precisam de outro fluxo de análise.
- Camadas OCR invisíveis e recursos legítimos de acessibilidade podem gerar alertas.
- Imagens, gradientes, recortes e efeitos de composição podem confundir a inspeção visual.
- A inspeção de ações não substitui um antivírus; subprocessos não são uma sandbox do sistema operacional.
- A extração pode perder a ordem lógica de documentos com várias colunas.
- Texto e relatórios permanecem dados não confiáveis. Uma integração com IA deve manter esses dados separados de instruções e permissões de ferramentas.

Use uma instância por pasta de saída. O histórico é um registro local, sem assinatura digital ou autenticação do nome do revisor.

## 🧩 Organização do código

| Arquivo | Responsabilidade |
| --- | --- |
| `app.py` | Interface gráfica (Tkinter): coleta parâmetros, dispara o lote e mostra o andamento. |
| `engine.py` | Motor, sem interface: análise do PDF, downloads, roteamento e processamento em lote. |
| `workflow.py` | Persistência, hashes, revisão humana e exportação. |
| `review_ui.py` | Fila de revisão e prévia rasterizada. |
| `evaluation/` | Corpus de frases e scripts que reproduzem os números deste README. |
| `test_app.py` / `test_revision.py` | Testes automatizados. |
| `.github/workflows/tests.yml` | Integração contínua: testes e avaliação em Linux e Windows. |
| `requirements-dev.txt` | Dependências para desenvolver e testar. |
| `docs/GUIA_DE_USO.md` | Guia detalhado, limites e observações operacionais. |
| `CHANGELOG.md` | Histórico das melhorias. |

### Usar o motor sem a interface

O motor não depende de Tkinter e pode ser usado em scripts ou servidores:

```python
from engine import run_batch

resultado = run_batch({'root': 'triagem'}, local='curriculos/')
print(dict(resultado))   # ex.: {'aprovados': 12, 'verificacao_humana': 3}
```

## 📊 Avaliação reproduzível

Os números deste README podem ser reproduzidos (na raiz do projeto, com `pip install -r requirements-dev.txt`):

```bash
python -m evaluation.run_phrases      # recall e falsos positivos de frases; compara com a v2.0
python -m evaluation.run_pdfs         # ataques escondidos, injeção visível e currículos legítimos
python -m evaluation.run_realistic    # PDFs de reportlab (e LibreOffice/wkhtmltopdf, se instalados)
```

Resultado da versão 2.4: frases do conjunto inédito, **22 de 30** detectadas contra 4 de 30 da v2.0, com 0 falsos positivos em 40 linhas legítimas; 24 de 24 ataques escondidos, 11 de 11 sinalizações e 11 de 11 layouts legítimos nos PDFs sintéticos. O conjunto de desenvolvimento serve apenas como teste de regressão, porque os padrões foram ajustados olhando para ele; só o conjunto inédito mede generalização. Detalhes em `evaluation/README.md`. A integração contínua roda esses scripts com `--check` e falha se a qualidade piorar.

O código está comentado em português. Para contribuir, descreva o caso observado, use um PDF sintético sem dados pessoais e adicione um teste quando a mudança corrigir um comportamento relevante.
