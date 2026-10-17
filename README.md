<p align="center">
  <img src="assets/icon_128.png" width="96" alt="Ícone do Currículo Guard: folha de currículo com um escudo verde com check">
</p>

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
- **Exporta um inventário CSV:** sem incluir o texto integral dos currículos, com opção para o Excel em português (separador `;` e acentos corretos).

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

**Lotes repetidos são incrementais.** A saída guarda um `registro_origens.jsonl` (caminho ou URL, tamanho, data, SHA-256 e relatório). Repetir o lote sobre a mesma pasta ou lista de URLs ignora o que não mudou e ainda tem relatório, sem empilhar cópias em `duplicados` nem downloads em `originais`. Um arquivo alterado é analisado de novo; o mesmo conteúdo com outro nome continua sendo `duplicados`; a quarentena é reanalisada a cada execução e a tentativa anterior do mesmo conteúdo é substituída em vez de acumulada. Para forçar tudo, marque **Reanalisar duplicados**. A verificação rápida usa tamanho e data de modificação; um arquivo trocado por outro de mesmo tamanho e mesma data passaria despercebido.

## 🌐 Entrada pela internet

Informe uma URL HTTPS direta de PDF ou uma URL terminada em `.json` com um manifesto:

```json
[
  "https://exemplo.com/curriculos/documento-01.pdf",
  "https://exemplo.com/curriculos/documento-02.pdf"
]
```

O manifesto aceita até 100 URLs. O app não raspa páginas nem acessa pastas autenticadas. Destinos privados e redirecionamentos são bloqueados, e o IP é conferido de novo no momento da conexão (fecha o DNS rebinding, em que o DNS responde com um IP público na validação e com `127.0.0.1` na conexão). Downloads e manifesto têm prazo total e respondem ao botão Interromper. Downloads são gravados em temporários e só publicados após a validação inicial.

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

A versão 2.9 passou por **181 testes automatizados** (8 deles usam a interface real e são ignorados em ambientes sem tela), cobrindo filtragem, DPI, contraste contra o fundo real (incluindo texto sobre caixa do mesmo tom, réguas e selos), cobertura fragmentada, gradientes, páginas rotacionadas, frases de injeção (corpus com casos positivos e negativos), conteúdo auxiliar, Unicode, persistência, revisão, integridade, quarentena, limites de tempo, prévia PNG, CSV, downloads simulados, DNS rebinding e servidor que goteja bytes (com servidores locais reais), Unicode hostil e nomes de arquivo inválidos, ações e canais internos do PDF, travas entre instâncias e lote incremental. O motor de análise importa e roda sem Tkinter.

A interface ainda não foi validada visualmente no ambiente de desenvolvimento. Downloads foram testados com respostas simuladas, não com um servidor externo real.

## ⚠️ Limites que fazem parte do projeto

- A detecção é **heurística**: pode produzir falsos positivos e falsos negativos.
- A detecção de frases de injeção cobre formulações comuns em português e inglês; espanhol, francês, alemão e italiano só nos pedidos para ignorar as instruções e (em es, fr e de) para ditar a decisão. Em um conjunto de 30 frases novas, escritas depois dos padrões, a v2.8 detectou 22 (73%) e a v2.9 detecta 23; esse ponto a mais vem **só** do espanhol, acrescentado sabendo que havia uma frase em espanhol no conjunto, e portanto não é evidência de melhor generalização. Em 40 frases legítimas de currículo, nenhuma foi sinalizada. A v2.9 também enxerga hifenização de fim de linha, sílabas separadas, leetspeak, texto invertido, ROT13 e cargas base64/hexadecimais que decodificam para uma frase; essas evasões foram escritas depois de eu vê-las passar, então são testes de regressão e não uma medida independente. Paráfrases novas, outros idiomas e outras codificações continuam passando.
- Não há OCR integrado; PDFs escaneados precisam de outro fluxo de análise.
- O MuPDF compõe a página sobre fundo transparente e leitores como Chrome e poppler desenham sobre papel branco. Com modos de mesclagem isso pode fazer o texto aparecer em um e sumir no outro; quando o PDF usa esses modos, o texto que só aparece na composição sobre fundo transparente é sinalizado. Outras diferenças entre renderizadores que eu não testei podem existir.
- O texto vem da camada de texto do PDF. Uma fonte com mapeamento `ToUnicode` adulterado pode exibir um texto e entregar outro à extração; sem OCR para comparar os dois, isso só é percebido pelos alertas (por exemplo, `unicode_indeterminado`) ou pela revisão do texto filtrado.
- O texto de um PDF escaneado só chega à saída se houver camada de texto visível; a camada de OCR invisível (modo de renderização 3) é tratada como texto invisível e descartada, e o documento vai para revisão sem texto.
- A tinta é verificada por caractere na página renderizada; se outro texto visível ocupa exatamente o mesmo lugar, a tinta de um pode ser atribuída ao outro.
- Caracteres invisíveis comuns em línguas e emoji (marcas de direção em hebraico e árabe, ZWNJ e ZWJ em persa, hindi e emoji, hífen suave) não geram alerta; os suspeitos (espaço de largura zero entre letras latinas, bidi override, tags Unicode, sequências) geram. Mensagens escritas com tags Unicode invisíveis são decodificadas antes da busca de frases.
- Links simbólicos na pasta de entrada são ignorados, e arquivos que resolvem para fora dela também.
- Os processos que leem PDFs (análise e prévia da revisão) têm teto de 2 GB de memória virtual em Linux e macOS (um PDF de 14 KB pode inflar para gigabytes ao ser interpretado); no Windows não há esse teto e vale apenas o prazo.
- Dois lotes não rodam ao mesmo tempo na mesma pasta de saída: o segundo é recusado com uma mensagem (trava `.lote.lock`, retomada sozinha após 5 minutos sem sinal de vida). Decisões de revisão simultâneas sobre o mesmo documento são serializadas, e quem decide com a tela desatualizada recebe um aviso em vez de sobrescrever a decisão de outra pessoa. As travas dependem de o sistema de arquivos honrar a criação exclusiva de arquivos (SMB e NFS atuais honram, mas não foi testado aqui) e não substituem controle de acesso.
- Camadas OCR invisíveis e recursos legítimos de acessibilidade podem gerar alertas.
- Imagens, gradientes, recortes e efeitos de composição podem confundir a inspeção visual.
- A inspeção de ações não substitui um antivírus; subprocessos não são uma sandbox do sistema operacional.
- A extração pode perder a ordem lógica de documentos com várias colunas.
- Texto e relatórios permanecem dados não confiáveis. Uma integração com IA deve manter esses dados separados de instruções e permissões de ferramentas.

O histórico é um registro local, sem assinatura digital ou autenticação do nome do revisor.

## 🧩 Organização do código

| Arquivo | Responsabilidade |
| --- | --- |
| `app.py` | Interface gráfica (Tkinter): coleta parâmetros, dispara o lote e mostra o andamento. |
| `engine.py` | Motor, sem interface: análise do PDF, downloads, roteamento e processamento em lote. |
| `workflow.py` | Persistência, hashes, revisão humana e exportação. |
| `review_ui.py` | Fila de revisão e prévia rasterizada. |
| `assets/` | Ícone do aplicativo: `icon.svg` (fonte), PNGs, `icon.ico` e `make_icons.py`, que os gera. |
| `evaluation/` | Corpus de frases e scripts que reproduzem os números deste README. |
| `test_app.py` / `test_revision.py` / `test_security.py` / `test_visual.py` / `test_evasao.py` / `test_exportacao.py` / `test_gui.py` | Testes automatizados; `test_security.py` cobre rede, Unicode, travas, lote incremental e canais internos do PDF; `test_visual.py`, modos de mesclagem e texto invisível; `test_evasao.py`, evasões do detector e texto legítimo em seis idiomas; `test_exportacao.py`, CSV e relatórios grandes; `test_gui.py` roda a interface real. |
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

## 🖼️ Interface

<p align="center">
  <img src="docs/img/entrada.png" width="48%" alt="Aba Entrada, com o ícone e o nome no cabeçalho">
  <img src="docs/img/revisao.png" width="48%" alt="Aba Revisão humana, com um documento sinalizado selecionado">
</p>

Capturas feitas em Linux, com o tema padrão do Tk; no Windows e no macOS o visual dos controles muda. Para regenerar o ícone depois de editar `assets/icon.svg`: `python assets/make_icons.py`.

## 📊 Avaliação reproduzível

Os números deste README podem ser reproduzidos (na raiz do projeto, com `pip install -r requirements-dev.txt`):

```bash
python -m evaluation.run_phrases      # recall e falsos positivos de frases; compara com a v2.0
python -m evaluation.run_pdfs         # ataques escondidos, injeção visível e currículos legítimos
python -m evaluation.run_realistic    # PDFs de reportlab (e LibreOffice/wkhtmltopdf, se instalados)
```

Resultado da versão 2.9: frases do conjunto inédito, **23 de 30** detectadas (22 na 2.8; o ponto a mais é o espanhol, ver os limites acima) contra 4 de 30 da v2.0, com 0 falsos positivos em 40 linhas legítimas; 27 de 27 ataques escondidos, 12 de 12 sinalizações e 13 de 13 layouts legítimos nos PDFs sintéticos. O conjunto de desenvolvimento serve apenas como teste de regressão, porque os padrões foram ajustados olhando para ele; só o conjunto inédito mede generalização. Detalhes em `evaluation/README.md`. A integração contínua roda esses scripts com `--check` e falha se a qualidade piorar.

O código está comentado em português. Para contribuir, descreva o caso observado, use um PDF sintético sem dados pessoais e adicione um teste quando a mudança corrigir um comportamento relevante.
