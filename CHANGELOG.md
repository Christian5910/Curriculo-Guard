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
