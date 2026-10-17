# Versão 2.8

Segunda bateria, focada no que a 2.7 não tocou: canais de ataque, escala, concorrência e uso repetido. Como na 2.7, cada defeito foi reproduzido antes de corrigir e tem teste de regressão verificado por mutação (remover o mecanismo faz o teste falhar). Duas das correções não cabem em remendos pontuais e viraram funcionalidades.

Defeitos confirmados:

- **Ações ativas embutidas passavam sem alerta (segurança):** `structural_checks` só olhava as chaves de primeiro nível de cada objeto, então `/OpenAction << /S /JavaScript ... >>` embutido no catálogo ou numa página, `/A << /S /Launch ... >>` num link, `/SubmitForm` e a árvore de nomes de JavaScript (5 de 6 variantes) não geravam `acao_ativa`; só a forma com objeto próprio era vista. Agora a varredura lê o texto canônico de cada objeto (inclusive o trailer), onde `/Java#53cript` já chega resolvido.
- **Frases em canais internos sem cobertura:** títulos de marcadores, URIs de links, rótulos de página, nomes de anexos, destinos nomeados e chaves personalizadas de `/Info` não eram inspecionados. As strings internas do PDF (com decodificação de escapes e UTF-16, limite por objeto e orçamento total) e uma versão sem codificação de URL e sem separadores (`ignore+all_previous%20instructions`) passam pela mesma busca de frases. Custo no pior caso testado (29 mil objetos): de 0,25 s para 0,63 s.
- **Repetir o lote empilhava lixo:** cada nova execução sobre a mesma pasta acrescentava uma cópia do PDF e um relatório por arquivo em `duplicados` (4 execuções de 3 currículos: 9 cópias de lixo e 12 linhas na fila em vez de 3), um `originais/download_<uuid>.pdf` por rodada nas URLs repetidas, e uma nova cópia em quarentena a cada tentativa de um arquivo que falha.
- **Decisões simultâneas corrompiam o estado (30 de 30 tentativas):** dois revisores no mesmo documento deixavam o PDF em duas pastas, uma cópia órfã sem relatório e só uma das decisões no histórico.

Funcionalidades novas (um remendo não resolveria):

- **Lote incremental (`registro_origens.jsonl`):** a saída lembra de cada origem (caminho ou URL, tamanho, data, SHA-256, relatório). Origem inalterada e com relatório existente é ignorada (`ja_processados`); conteúdo alterado é reanalisado; o mesmo conteúdo com outro nome segue sendo `duplicados`; a quarentena continua sendo reanalisada a cada execução (como a ajuda da tela já dizia), e a tentativa anterior do mesmo conteúdo é substituída em vez de acumulada. Só se remove cópia em quarentena com SHA-256 igual, sem decisão humana e dentro da pasta de quarentena. Um arquivo corrigido (conteúdo novo) mantém a cópia antiga como evidência. **Reanalisar duplicados** força tudo.
- **Travas e decisão desatualizada:** `FileLock` (criação exclusiva, token de dono, recuperação de trava abandonada, sinal de vida) protege cada relatório em `decide()` e a pasta de saída em `run_batch` (o segundo lote é recusado com mensagem). A tela passa o status que o revisor viu (`expected_status`): se outra pessoa decidiu no meio, a decisão é recusada com aviso em vez de sobrescrever em silêncio.

Verificado e **sem problema** (para não repetir a busca): escala (10 mil currículos: 0,7 s para indexar e 0,5 s para listar; o custo é linear) e bomba gzip em `Content-Encoding` (401 KB que viram 400 MB são recusados em 0,0 s, porque o teto de 15 MB vale para o corpo já decodificado; o teste de regressão só passou a existir agora).

Limites conhecidos: a verificação rápida do lote incremental usa tamanho e data (um arquivo trocado por outro de mesmo tamanho e data passa); as travas dependem de criação exclusiva de arquivo no sistema de arquivos (não testado em pasta de rede); a retomada de trava abandonada tem uma janela de milissegundos se dois processos a virem vencer no mesmo instante.

Testes: 127 → 157 (7 de interface real). Verificado em Python 3.11, 3.12 e 3.13.

# Versão 2.7

Nova bateria (rede, Unicode, revisão, fuzz). Cada defeito abaixo foi **reproduzido antes de corrigir** e tem teste de regressão em `test_security.py`, verificado por mutação (reintroduzir o defeito faz o teste falhar). A detecção não mudou: as três avaliações têm saída idêntica à da 2.6.

Defeitos confirmados e corrigidos:

- **DNS rebinding (segurança):** `is_public_https` validava o DNS e o `requests` resolvia o nome de novo ao conectar; um DNS que responde com IP público na validação e `127.0.0.1` na conexão fazia o app conectar à máquina local (comprovado com um servidor em `127.0.0.1:443`). Agora `strict_egress()` confere todos os IPs no momento da conexão e conecta direto ao IP validado, sem segunda resolução. Vale para PDFs e manifesto, por thread, e um teste sentinela falha se uma versão futura do urllib3 deixar de passar pelo ponto de conexão.
- **Manifesto de URLs sem prazo:** a mesma falha do download corrigida na 2.6 ficou no manifesto (`iter_content` bloqueava com 1 byte por segundo; o Interromper não funcionava, 14 s depois do clique ainda travado). Agora usa `read1`, prazo de 30 s, cancelamento e a mesma rotina do download.
- **Unicode hostil e nomes de arquivo:** um PDF cujo `ToUnicode` mapeia um glifo para meio par UTF-16, ou um currículo com nome em Latin-1 em Linux/macOS (`Currículo.pdf` gravado por um sistema antigo), gerava `UnicodeEncodeError` ao gravar o relatório: o arquivo **sumia do lote** (sem relatório, sem quarentena, só uma linha de log). Agora os textos são limpos na origem, o caso gera o alerta `unicode_indeterminado` (revisão humana), o nome é analisado por uma cópia segura e, como segunda camada, um resultado que não possa ser gravado vai para a quarentena.
- **`decide()` apagava o TXT liberado antes de validar:** se a decisão falhasse (destino já existente, cópia ou gravação com erro), o relatório continuava "aprovados" sem o texto. Agora valida antes de revogar e restaura o TXT em qualquer falha. Também passou a conferir o SHA-256 da cópia (o README já prometia) e a não desfazer uma decisão concluída se a remoção do arquivo antigo falhar (Windows).
- **NAT64:** `64:ff9b::/96` (que embute `127.0.0.1` ou o endereço de metadados de nuvem) passava no filtro de IP. Endereços IPv6 que embrulham um IPv4 (mapeado, NAT64, 6to4) são julgados pelo IPv4 embutido; Teredo é recusado.

Endurecimento preventivo (sem defeito reproduzido):

- A prévia da revisão humana, que abre o PDF suspeito, passou a ter o mesmo teto de memória da análise. Com as bombas de imagem e de glifos testadas, a prévia já usava pouca memória (64 e 190 MB); o teto vale para vetores ainda desconhecidos. O limitador foi movido para `workflow.py` para o processo da prévia não importar numpy.

Verificado e **sem problema** (para não repetir a busca): coordenadas NaN/infinito em PDFs (o MuPDF as limita); a interface Tk aceita texto com meio par UTF-16 sem derrubar o laço de atualização; fuzz de 370 PDFs corrompidos (bytes trocados, truncados, duplicados) sem exceção, travamento ou arquivo perdido.

Testes: 104 → 127. Também foi corrigido um `ResourceWarning` num teste de CSV.

# Versão 2.6

Resultado de uma bateria nova (segurança, robustez, alfabetos, escala, documentação executável, comparação com um segundo renderizador). Defeitos confirmados e corrigidos:

- **Download:** um servidor que "gotejava" 1 byte por segundo bloqueava o laço de leitura por horas, ignorando o prazo de 90 s e o botão Interromper (45 s depois do clique o download seguia travado). A leitura agora usa `read1` e confere prazo e cancelamento a cada chegada de bytes: o cancelamento responde em ~3 s e o prazo vale. Exige `urllib3>=2.2`. O cancelamento durante um fluxo normal caiu de 6,4 s para 1,5 s.
- **Memória:** um PDF de 14 KB (uma string de 14,5 MB comprime a quase nada) fazia o sistema matar o processo de análise por falta de memória. O processo filho agora tem teto de 2 GB de memória virtual (Linux e macOS; documentos normais usam menos de 450 MB), uma thread numérica e mensagem de erro clara. A bomba de imagem de 30000x30000 caiu de 1,8 GB para 966 MB.
- **Links simbólicos na pasta de entrada** copiavam arquivos de fora (por exemplo, um segredo ou um PDF privado) para a pasta de saída e o texto do PDF privado ia para os relatórios. Agora são ignorados, e `Pipeline.process` os recusa.
- **PDF sem relatório** (queda entre a cópia e a gravação) virava "duplicado" de um arquivo nunca avaliado, e o currículo ficava sem análise. Agora só conta como já visto o PDF que tem relatório.
- **PDF com BOM ou linhas em branco antes de `%PDF-`** (o erro clássico de PHP) ia para a quarentena sem motivo, embora Acrobat e MuPDF o abram. O cabeçalho é aceito nos primeiros 1024 bytes, também no download.
- **Verificação de tinta por caractere:** cobrir 74% de uma linha deixava o payload coberto entrar no texto, porque a cauda visível "salvava" o trecho inteiro. Agora cada caractere sem tinta visível é removido do texto e sinalizado (custo de ~35% no caso mais denso: 3,4 s para 4,6 s em 35 páginas).
- **Destaque semitransparente** desenhado depois do texto gerava `possivel_sobreposicao` (falso positivo): texto que continua legível na página renderizada não é mais tratado como escondido; coberturas de 80% ou mais de opacidade continuam sendo.
- **Unicode:** qualquer caractere invisível gerava `controles_unicode`, o que mandaria para a revisão currículos em persa, hindi, hebraico, árabe e os com emoji (👩‍💻). Agora só os suspeitos geram alerta. Mensagens escritas com tags Unicode invisíveis ("ASCII smuggling") são decodificadas antes da busca de frases.
- **URLs:** multicast (`224.0.0.1`) passava na validação, e espaços e caracteres de controle não eram rejeitados.
- **CSV:** células começando com TAB ou CR não eram neutralizadas.
- **Pastas extras:** a validação aceitava nomes que quebram no Windows (`CON`, `NUL`, só espaço ou hífen, espaço no fim) e nomes iguais aos das pastas fixas.
- **Interface:** o painel de detalhes não mostrava o motivo da quarentena (`assinatura inválida`, erro da análise, duplicado de).
- Verificado sem problema: fontes Type 3, 9 alfabetos, texto rotacionado, marca d'água, PDFs malformados (laços, aninhamento, 300 mil objetos), `kill -9` no meio do lote, determinismo entre sementes de hash, regex sem backtracking catastrófico, invariância ao DPI de renderização, acordo com o pdfium em todos os cenários escondidos.
- 3 cenários escondidos, 1 de sinalização e 2 legítimos novos na avaliação (27/27, 12/12, 13/13). 104 testes passaram (98 sem tela).

# Versão 2.5

- **Ícone do aplicativo:** nova pasta `assets/` com `icon.svg` (fonte), PNGs de 16 a 512 px, `icon.ico` e `make_icons.py`, que os gera só com PyMuPDF. Uma folha de currículo com um escudo verde com check. O cabeçalho da janela agora mostra o ícone e o nome no canto superior esquerdo, e o ícone também vai para a janela e a barra de tarefas. Se a pasta `assets/` faltar, o app abre normalmente, sem ícone.
- **Primeira execução da interface com Tk real** (Xvfb; Tk 8.6 e 9.0). Nenhuma exceção em callbacks; lote, revisão, prévia, CSV e configuração funcionaram. Defeitos encontrados e corrigidos:
  - o rótulo "Tempo máximo por análise em segundos (5–180)" aparecia cortado em "(5-": os rótulos dos campos compactos tinham largura fixa de 35 caracteres e este tem 45; agora todos usam 46 e as caixas ficam alinhadas;
  - as mensagens de erro do motor diziam "Opacidade máxima", "Cobertura máxima" e "Tempo limite por arquivo", enquanto a interface diz "Opacidade mínima", "Cobertura suspeita" e "Tempo máximo por análise"; agora são idênticas, com teste que compara os dois;
  - textos desatualizados: a caixa "Estimar contraste com fundo local" passou a "Medir contraste e tinta visível contra o fundo real", e a ajuda agora cita a reanálise da quarentena, a definição de duplicado e a verificação de tinta.
- Novo `test_gui.py`: roda a interface real (lote completo, revisão, exportação, configuração, validação, cabeçalho, rótulos e alinhamento). É ignorado sem Tkinter ou tela; com `REQUIRE_GUI_TESTS=1` (usado na CI Linux) a ausência vira falha. Testes de assets: PNGs, `.ico` e em dia com o SVG.
- CI: instala o Xvfb no Linux e exige os testes de interface; o pyflakes passa a cobrir todos os arquivos.
- Capturas de tela da interface em `docs/img/` (Linux, tema padrão do Tk).
- 85 testes passaram (79 sem tela).

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
