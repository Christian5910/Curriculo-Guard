# Versão 2.4

- **Verificação de tinta visível:** como o motor já renderiza a página com e sem texto, cada trecho agora precisa deixar diferença visível entre as duas imagens. Antes, texto com cor declarada legível mas invisível na prática (modo de mesclagem `Screen`/`Lighten`/`Difference` sobre um fundo desenhado, ou preenchimento por padrão branco) passava sem alerta e entrava no TXT. Em 539 trechos legítimos medidos (LibreOffice, wkhtmltopdf, reportlab e layouts sintéticos), o de menor tinta marcou 89 de 255, contra o limite de 16. Limite conhecido: se outro texto visível ocupa o mesmo lugar, a tinta é atribuída a ele.
- **Desempenho em PDFs com imagens grandes:** a renderização sem texto passou a usar um segundo documento aberto uma única vez, com a redação feita no lugar, em vez de copiar a página (com fontes e imagens) para um documento novo a cada página. Em um PDF de 13,6 MB com 35 páginas, a análise caiu de 17,5 s para 2,4 s, com resultado idêntico.
- 4 cenários novos em `evaluation/run_pdfs.py` (24 de 24 ataques escondidos) e 4 testes novos; teste de que a análise preserva todas as páginas e nunca altera o arquivo. 73 testes passaram.
- Verificado em Python 3.11 com as versões mínimas declaradas (PyMuPDF 1.26.6, numpy 1.26.4, requests 2.32.3) e em Python 3.13 com as mais recentes.

# Versão 2.3

Sem mudança no comportamento da detecção; mudanças de estrutura e de verificação.

- **Motor separado da interface:** a análise, o roteamento, os downloads e o lote agora vivem em `engine.py`, que não importa Tkinter. `app.py` ficou só com a interface. A orquestração do lote (`run_batch`) e a validação de limites (`validate_params`) saíram da classe da interface e podem ser usadas em scripts.
- Migração de `import fitz` para `import pymupdf` (a API `fitz` está sendo descontinuada).
- Nova pasta `evaluation/` com o corpus de frases (separando o conjunto ajustado do conjunto inédito), a linha de base da v2.0 e três scripts que reproduzem as medições do README. A v2.0 gerava 7 falsos positivos em 46 frases legítimas do conjunto de desenvolvimento; a atual gera 0.
- Integração contínua (GitHub Actions) com testes e avaliação em Ubuntu e Windows, Python 3.11 a 3.13; `requirements-dev.txt`.
- Teste de PDFs gerados por reportlab; testes de `run_batch`, `validate_params` e do isolamento do Tkinter; teste de symlink ignorado quando o sistema não permite criá-los.
- 69 testes passaram.

# Versão 2.2

- **Fundo real em vez de anel:** o contraste passa a ser medido contra uma renderização da página sem texto, pixel a pixel dentro do retângulo de cada trecho. Isso corrige dois problemas do método do anel: (1) texto preto sobre caixa preta do tamanho exato do texto, ou sobre imagem escura, passava sem alerta; (2) réguas sob títulos, selos e bordas de tabela geravam `fundo_indeterminado` e retiravam conteúdo legítimo do texto filtrado. Em currículos gerados por LibreOffice, wkhtmltopdf e reportlab, os alertas indevidos desapareceram. O anel segue como plano B se a renderização falhar.
- Letras separadas por ponto ou hífen (`I.g.n.o.r.e`) agora são recompostas; antes a regra aceitava esses separadores mas só removia espaços.
- A busca "achatada" (sem pontuação) só roda quando há letras separadas; antes casava frases legítimas como "I never forget. Everything I learn...".
- Relatórios malformados (JSON profundamente aninhado, campos de tipo errado) são contabilizados como inválidos em vez de derrubar a listagem de revisão.
- O manifesto de URLs ignora proxies de ambiente, como o download já fazia.
- `ReviewStore` e `hashlib` sem uso removidos de `app.py`; a assinatura `%PDF-` é lida sem carregar o arquivo inteiro.
- Texto de ajuda da interface sobre o fundo atualizado. Configurações salvas na 2.0 mantêm o contraste 1,2:1 até serem ajustadas.
- 63 testes passaram.

# Versão 2.1

- Contraste mínimo padrão elevado de 1,2:1 para 2,0:1: texto cinza muito claro (#E0, #E6) passava sem alerta e entrava no TXT.
- Cobertura por objetos posteriores agora usa a **união** dos retângulos; vários retângulos pequenos sobre o texto deixam de escapar do limite.
- Fundo medido por janelas horizontais quando o anel único é heterogêneo, evitando alerta em cabeçalhos com gradiente suave.
- Detecção de instruções reescrita: limites de palavra, mais formulações em PT/EN, letras separadas por espaços ou pontos e homóglifos cirílicos/gregos. Padrões ancorados em verbo + objeto para reduzir falsos positivos (ex.: "send data ... via email", "system prompt design").
- Quarentena não conta mais como duplicado: arquivos que falharam por timeout ou erro transitório são reanalisados.
- `app.py` e `review_ui.py` importam sem Tkinter; o motor roda em servidor/CI. Execução direta sem Tk mostra mensagem clara.
- Versão centralizada em `APP_VERSION`. Interface inalterada, exceto o valor padrão do contraste.
- 52 testes passaram. Interface ainda sem validação visual; sem OCR integrado.

# Versão 2.0

- Corrigida sobrescrita de relatório/TXT quando havia duplicata ou reanálise.
- Cópias e relatórios únicos; gravação atômica e hash em blocos.
- Fila humana com busca, filtro, justificativa, histórico, liberação e revogação.
- Prévia rasterizada paginada com alertas destacados; exportação CSV.
- Downloads em temporários, limpeza em erros/cancelamento e prazo total.
- Análise em processo separado com limite de tempo configurável.
- Inspeção de anotações, formulários, metadados XML, controles Unicode, camadas e ações ativas.
- Normalização para detectar instruções disfarçadas por controles/espaços.
- Texto fora da página e fundos heterogêneos geram revisão.
- Limites de páginas, objetos, caracteres e renderização; conferência de integridade na revisão e cópia.
- 32 testes passaram. Interface ainda sem validação visual; sem OCR integrado.
