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

### Windows sem instalar Python (executável)

A pasta [`EXE/`](EXE/LEIA-ME.md) traz o programa pronto para Windows 10/11 de 64 bits, sem precisar de Python:

- **Portátil:** `EXE/CurriculoGuard-Portatil/` — dê dois cliques em `CurriculoGuard.exe`. Pode ser copiada para um pendrive.
- **Instalador:** `EXE/CurriculoGuard-Setup.exe` — instala só para o seu usuário (sem administrador), cria atalhos e um desinstalador.

O passo a passo para quem nunca criou um executável, e como refazê-lo, está em **[EXE/LEIA-ME.md](EXE/LEIA-ME.md)**.

### Requisitos (para rodar pelo código)

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

**Mantenha a estrutura de pastas:** `app.py` na raiz e a pasta `curriculo_guard/` ao lado dele.

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
python -m unittest discover -s tests -t . -v   # ou, se preferir: python -m pytest
```

A versão 2.11 passou por **198 testes automatizados** (8 deles usam a interface real e são ignorados em ambientes sem tela), cobrindo filtragem, DPI, contraste contra o fundo real (incluindo texto sobre caixa do mesmo tom, réguas e selos), cobertura fragmentada, gradientes, páginas rotacionadas, frases de injeção (corpus com casos positivos e negativos), conteúdo auxiliar, Unicode, persistência, revisão, integridade, quarentena, limites de tempo, prévia PNG, CSV, downloads simulados, DNS rebinding e servidor que goteja bytes (com servidores locais reais), Unicode hostil e nomes de arquivo inválidos, ações e canais internos do PDF, travas entre instâncias e lote incremental. O motor de análise importa e roda sem Tkinter.

A interface ainda não foi validada visualmente no ambiente de desenvolvimento. Downloads foram testados com respostas simuladas, não com um servidor externo real.

## ⚠️ Limites que fazem parte do projeto

- A detecção é **heurística**: pode produzir falsos positivos e falsos negativos.
- A detecção de frases de injeção cobre formulações comuns em português e inglês; espanhol, francês, alemão e italiano só nos pedidos para ignorar as instruções e (em es, fr e de) para ditar a decisão. Em um conjunto de 30 frases novas, escritas depois dos padrões, a v2.8 detectou 22 (73%) e a v2.9 detecta 23; esse ponto a mais vem **só** do espanhol, acrescentado sabendo que havia uma frase em espanhol no conjunto, e portanto não é evidência de melhor generalização. Em 40 frases legítimas de currículo, nenhuma foi sinalizada. A v2.9 também enxerga hifenização de fim de linha, sílabas separadas, leetspeak, texto invertido, ROT13 e cargas base64/hexadecimais que decodificam para uma frase; essas evasões foram escritas depois de eu vê-las passar, então são testes de regressão e não uma medida independente. Paráfrases novas, outros idiomas e outras codificações continuam passando.
- Não há OCR integrado; PDFs escaneados precisam de outro fluxo de análise.
- O motor lê PDFs com o MuPDF, e leitores diferentes divergem em construções raras. Medido com pdfium (Chrome) e poppler: o MuPDF desenha o texto pintado com `Separation /None` (cor sem marca) e os outros dois não; o motor sinaliza o espaço de cor (`cor_sem_marca`) e, havendo a **segunda opinião opcional do pdfium** (`pip install pypdfium2`), compara a página nos dois renderizadores e tira do TXT o texto que só o MuPDF desenha (`renderizadores_divergem`). No modo `auto` (padrão) ela só roda em PDFs que usam cor `Separation`/`DeviceN`, padrões, sombreados, máscaras suaves, mesclagem ou fontes Type 3; `cross_render` em `analysis_options` aceita `always` e `off`. Sem o pdfium o aplicativo funciona, só não tem essa segunda opinião. Outros leitores (Acrobat, Preview) e outras divergências não foram testados.
- Texto cortado por máscara de recorte vazia, por `Form XObject` de `BBox` vazio ou fora da área visível é descartado pela extração do MuPDF, mas pypdf, pdfminer e pdftotext o leem no PDF original, que continua na pasta de aprovados. O motor sinaliza esses casos (`texto_recortado`) comparando o texto desenhado com o extraído; o PDF original não é alterado.
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

| Caminho | Responsabilidade |
| --- | --- |
| `app.py` | **Único arquivo Python da raiz.** Interface gráfica (Tkinter): coleta parâmetros, dispara o lote e mostra o andamento. |
| `curriculo_guard/engine.py` | Motor, sem interface: análise do PDF, downloads, roteamento e processamento em lote. |
| `curriculo_guard/workflow.py` | Persistência, hashes, travas, revisão humana e exportação. |
| `curriculo_guard/review_ui.py` | Fila de revisão e prévia rasterizada. |
| `tests/` | Testes automatizados (`test_security.py` cobre rede, Unicode, travas, lote incremental e canais internos; `test_visual.py`, texto recortado e segunda opinião do pdfium; `test_evasao.py`, evasões do detector; `test_exportacao.py`, CSV; `test_gui.py` roda a interface real). |
| `evaluation/` | Corpus de frases e scripts que reproduzem os números deste README. |
| `assets/` | Ícone do aplicativo: `icon.svg` (fonte), PNGs, `icon.ico` e `make_icons.py`, que os gera. |
| `EXE/` | Executável para Windows (portátil e instalador) e, em `EXE/construcao/`, o que os gera. Ver `EXE/LEIA-ME.md`. |
| `docs/` | `GUIA_DE_USO.md` (guia detalhado, limites e observações operacionais) e `img/` (capturas de tela). |
| `.github/workflows/tests.yml` | Integração contínua: testes e avaliação em Linux e Windows, e a montagem do portátil no Windows. |
| `requirements.txt` / `requirements-dev.txt` / `pytest.ini` | Dependências, dependências de desenvolvimento e configuração do pytest. |
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
python -m evaluation.run_renderers    # oráculo: pdfium, poppler, pypdf, pdfminer e pdftotext (os que estiverem instalados)
```

Resultado da versão 2.10 (os mesmos números da 2.9): frases do conjunto inédito, **23 de 30** detectadas (22 na 2.8; o ponto a mais é o espanhol, ver os limites acima) contra 4 de 30 da v2.0, com 0 falsos positivos em 40 linhas legítimas; 27 de 27 ataques escondidos, 12 de 12 sinalizações e 13 de 13 layouts legítimos nos PDFs sintéticos. O conjunto de desenvolvimento serve apenas como teste de regressão, porque os padrões foram ajustados olhando para ele; só o conjunto inédito mede generalização. Detalhes em `evaluation/README.md`. A integração contínua roda esses scripts com `--check` e falha se a qualidade piorar.

O código está comentado em português. Para contribuir, descreva o caso observado, use um PDF sintético sem dados pessoais e adicione um teste quando a mudança corrigir um comportamento relevante.
