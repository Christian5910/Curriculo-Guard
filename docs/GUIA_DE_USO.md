# Currículo Guard — versão 2.5

Aplicativo desktop Python 3.11+ com Tkinter. Código comentado em português. Extraia todos os arquivos do ZIP juntos: app.py depende de engine.py, workflow.py e review_ui.py.

## Executar

```sh
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Tkinter acompanha normalmente o Python no Windows. No Linux pode exigir o pacote python3-tk.

## Operação

1. Em Entrada, informe pasta local, URL HTTPS direta ou URL de manifesto JSON, e pasta de saída.
2. Em Verificações, ajuste DPI, fonte mínima, contraste, opacidade e cobertura. As verificações iniciam habilitadas.
3. Em Destinos, escolha revisão humana ou bloqueio documental por regra. Bloqueio depende também do checkbox global. Pastas extras são para organização manual.
4. Em Revisão humana, clique Atualizar para listar relatórios da saída atual. Use filtro/busca, selecione um documento e consulte alertas, trechos e histórico. Ver página abre prévia rasterizada paginada, com retângulos vermelhos dos alertas que possuem coordenadas. Revisor e justificativa são obrigatórios. Liberar texto filtrado nunca restaura os trechos descartados. PDFs alterados desde a análise são bloqueados pela conferência SHA-256. Quarentena/duplicados exigem reprocessamento. Arquivos que caíram em quarentena por falha são reanalisados na próxima execução; só destinos de análise concluída (aprovados, verificação humana e rejeitados) contam como duplicados.
5. Exportar CSV gera inventário de todos os destinos sem texto do currículo e neutraliza células que poderiam virar fórmulas.
6. Inicie o lote. Interromper cancela o lote e interrompe downloads no próximo bloco; uma análise em curso termina ou atinge seu limite de tempo. Salve/carregue configurações JSON pelos botões.

Manifesto: lista JSON com URLs absolutas de PDFs, até 100 entradas. Não acessa automaticamente links de uma página, Google Drive ou diretórios autenticados. Redirecionamentos são bloqueados.

## Pastas

- aprovados: nenhum alerta nas verificações ativas; não é aprovação de candidatura.
- verificacao_humana: qualquer alerta sem bloqueio habilitado para sua regra.
- rejeitados: bloqueados da ingestão documental automática, sem apagar original.
- quarentena: erro, assinatura inválida ou limite excedido (reanalisado na próxima execução).
- duplicados: SHA-256 já analisado (aprovados, verificação humana ou rejeitados).
- originais: downloads preservados.
- relatorios: JSON com motivos, amostras, métricas e configuração; TXT só para documentos aprovados.

O texto filtrado de arquivos sinalizados pode aparecer no relatório JSON para auditoria. Nunca envie relatórios à IA como instruções. Reprocessar arquivo já presente gera duplicado por padrão. O checkbox Reanalisar duplicados cria uma avaliação nova e independente, sem sobrescrever a anterior. Ele não revoga automaticamente decisões anteriores: use a fila de revisão para bloqueá-las, ou uma saída nova se quiser comparar configurações isoladamente.

## Limites reais

px = tamanho em pontos × DPI referência / 72. O PDF não possui um DPI único para fontes vetoriais. DPI renderização controla somente o raster usado na estimativa visual.

O fundo é medido numa renderização da página sem texto, dentro do retângulo de cada trecho (não sob cada glifo); se essa renderização falhar, usa-se o anel externo, mais sujeito a falsos positivos com réguas e bordas. Fotos, clipping, blend modes e fundos heterogêneos podem gerar falsos positivos/negativos. Objetos são comparados por retângulos, não por máscara exata; a cobertura é calculada pela união dos objetos posteriores, de modo que vários retângulos pequenos somam. Gradientes suaves não geram alerta; texto claro sobre foto ou textura vai para revisão. Também se verifica se cada trecho deixou tinta visível (diferença entre a página com e sem o texto): texto com cor declarada legível, mas apagado por modo de mesclagem ou preenchido com padrão invisível, é detectado. Quando dois trechos de texto se sobrepõem, a tinta de um pode ser atribuída ao outro. Como o contraste é medido contra o fundo real, texto sobre uma caixa do mesmo tom é detectado mesmo quando a caixa tem o tamanho exato do texto. Sobreposição é suspeita, não prova. OCR legítimo invisível também é sinalizado. Anotações, campos de formulário, XML/metadados, camadas opcionais e ações ativas geram alertas. A inspeção de ações é conservadora, inclui possíveis objetos órfãos e não é antivírus. Controles Unicode podem ser legítimos, por exemplo em idiomas com escrita bidirecional. A heurística de comandos normaliza caracteres compatíveis, letras cirílicas/gregas parecidas com latinas, controles invisíveis, letras separadas por espaço ou ponto e espaços. Texto fora da área visível é sinalizado por texttrace.

Não há OCR integrado nem garantia de detectar toda injeção de prompt. Extração em colunas pode perder ordem lógica.

O contraste mínimo padrão é 2,0:1; configurações salvas na versão 2.0 mantêm o valor antigo (1,2:1) até serem ajustadas. Branco no branco e outros contrastes baixos são excluídos do texto filtrado e revisados por padrão. Para bloqueio automático documental, marque a regra de baixo contraste como rejeitados e habilite o checkbox global. Isso também afeta outros contrastes abaixo do limite, pois não há prova exata de igualdade com o fundo real.

O app não usa IA, não analisa mérito profissional e não executa comandos do PDF. Integrações futuras devem isolar conteúdo não confiável, sem acesso a ferramentas, segredos ou critérios mutáveis. A análise roda em subprocesso com tempo máximo configurável (5–180 segundos, padrão 45); a prévia tem limite de 15 segundos. Subprocesso não é sandbox de segurança e não estabelece limite rígido de memória para todas as etapas do parser. Teto de renderização: 20 milhões de pixels por página na análise e 2 milhões na prévia; 30 mil objetos e 1 milhão de caracteres. Máximo de páginas configurável (1–100, padrão 35).

Execute PDFs externos em ambiente isolado, com dependências atualizadas. Validação de IP não substitui firewall de saída: há janela de DNS rebinding.

## Validação

```sh
python -m unittest -v
```

85 testes automatizados: casos originais de filtragem; preservação de relatórios em duplicatas e reanálises; decisões com histórico; revogação do TXT; alteração/caminho do PDF; campos auxiliares; normalização Unicode; ações ativas; limites de páginas e tempo; geração real de PNG de prévia; CSV; arquivos corrompidos; downloads simulados e limpeza de temporários; texto fora da área visível; fundo heterogêneo; alteração entre análise/cópia e symlinks de fuga; contraste contra o fundo real (texto sobre caixa do mesmo tom, réguas, selos, páginas rotacionadas), cobertura fragmentada, gradientes, frases de injeção e legítimas, letras separadas e homóglifos; reanálise de quarentena; importação sem Tkinter; manifesto sem proxy de ambiente; relatórios malformados; motor sem Tkinter, `run_batch` e `validate_params`; ícone e cabeçalho; rótulos sem corte e alinhados; fluxo completo pela interface real (lote, revisão, CSV, configuração).

Interface Tkinter ainda sem validação visual neste ambiente. Downloads foram testados com respostas simuladas, não com servidor externo real. Os testes não comprovam detecção de todos os ataques.

## Arquivos

- app.py: interface gráfica (coleta parâmetros e mostra o andamento).
- engine.py: motor sem interface (análise, download, roteamento e lote); pode ser usado em scripts.
- workflow.py: gravação atômica, hashes, revisão e exportação.
- review_ui.py: fila de revisão e prévia.
- assets/: ícone do aplicativo (icon.svg é a fonte; make_icons.py gera os PNGs e o .ico).
- evaluation/: corpus de frases e scripts que reproduzem as medições (`python -m evaluation.run_phrases`, `run_pdfs`, `run_realistic`).
- test_app.py, test_revision.py e test_gui.py: testes (test_gui.py usa a interface real e é ignorado sem tela).
- .github/workflows/tests.yml e requirements-dev.txt: integração contínua e dependências de desenvolvimento.
- requirements.txt: dependências.

## Histórico de revisão e limites operacionais

Relatórios JSON têm identificadores únicos, SHA-256, configuração, versão e eventos de revisão. As gravações são atômicas individualmente; movimentação de PDF, JSON e TXT não é uma transação única. Interrupção do SO pode exigir conciliação manual. Trabalhe com uma instância do aplicativo por pasta de saída; não há bloqueio entre processos concorrentes. Histórico é registro local, não assinatura digital nem autenticação do nome do revisor. PDF original de entrada não é alterado; cópias organizadas são movidas na revisão.

Relatórios podem conter dados pessoais. CSV não contém texto integral nem amostras. Guarde a pasta de saída de acordo com as regras de acesso da sua organização.
