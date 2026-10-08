# Currículo Guard — versão 2.0

Aplicativo desktop Python 3.11+ com Tkinter. Código comentado em português. Extraia todos os arquivos do ZIP juntos: app.py depende de workflow.py e review_ui.py.

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
4. Em Revisão humana, clique Atualizar para listar relatórios da saída atual. Use filtro/busca, selecione um documento e consulte alertas, trechos e histórico. Ver página abre prévia rasterizada paginada, com retângulos vermelhos dos alertas que possuem coordenadas. Revisor e justificativa são obrigatórios. Liberar texto filtrado nunca restaura os trechos descartados. PDFs alterados desde a análise são bloqueados pela conferência SHA-256. Quarentena/duplicados exigem reprocessamento.
5. Exportar CSV gera inventário de todos os destinos sem texto do currículo e neutraliza células que poderiam virar fórmulas.
6. Inicie o lote. Interromper cancela o lote e interrompe downloads no próximo bloco; uma análise em curso termina ou atinge seu limite de tempo. Salve/carregue configurações JSON pelos botões.

Manifesto: lista JSON com URLs absolutas de PDFs, até 100 entradas. Não acessa automaticamente links de uma página, Google Drive ou diretórios autenticados. Redirecionamentos são bloqueados.

## Pastas

- aprovados: nenhum alerta nas verificações ativas; não é aprovação de candidatura.
- verificacao_humana: qualquer alerta sem bloqueio habilitado para sua regra.
- rejeitados: bloqueados da ingestão documental automática, sem apagar original.
- quarentena: erro, assinatura inválida ou limite excedido.
- duplicados: SHA-256 já encontrado na saída.
- originais: downloads preservados.
- relatorios: JSON com motivos, amostras, métricas e configuração; TXT só para documentos aprovados.

O texto filtrado de arquivos sinalizados pode aparecer no relatório JSON para auditoria. Nunca envie relatórios à IA como instruções. Reprocessar arquivo já presente gera duplicado por padrão. O checkbox Reanalisar duplicados cria uma avaliação nova e independente, sem sobrescrever a anterior. Ele não revoga automaticamente decisões anteriores: use a fila de revisão para bloqueá-las, ou uma saída nova se quiser comparar configurações isoladamente.

## Limites reais

px = tamanho em pontos × DPI referência / 72. O PDF não possui um DPI único para fontes vetoriais. DPI renderização controla somente o raster usado na estimativa visual.

Fundo estimado por anel externo, não reconstruído sob cada glifo. Gradientes, fotos, clipping, blend modes e fundos heterogêneos podem gerar falsos positivos/negativos. Objetos são comparados por retângulos, não por máscara exata. Sobreposição é suspeita, não prova. OCR legítimo invisível também é sinalizado. Anotações, campos de formulário, XML/metadados, camadas opcionais e ações ativas geram alertas. A inspeção de ações é conservadora, inclui possíveis objetos órfãos e não é antivírus. Controles Unicode podem ser legítimos, por exemplo em idiomas com escrita bidirecional. A heurística de comandos normaliza caracteres compatíveis, controles invisíveis e espaços. Texto fora da área visível é sinalizado por texttrace.

Não há OCR integrado nem garantia de detectar toda injeção de prompt. Extração em colunas pode perder ordem lógica.

Branco no branco e outros contrastes baixos são excluídos do texto filtrado e revisados por padrão. Para bloqueio automático documental, marque a regra de baixo contraste como rejeitados e habilite o checkbox global. Isso também afeta outros contrastes abaixo do limite, pois não há prova exata de igualdade com o fundo real.

O app não usa IA, não analisa mérito profissional e não executa comandos do PDF. Integrações futuras devem isolar conteúdo não confiável, sem acesso a ferramentas, segredos ou critérios mutáveis. A análise roda em subprocesso com tempo máximo configurável (5–180 segundos, padrão 45); a prévia tem limite de 15 segundos. Subprocesso não é sandbox de segurança e não estabelece limite rígido de memória para todas as etapas do parser. Teto de renderização: 20 milhões de pixels por página na análise e 2 milhões na prévia; 30 mil objetos e 1 milhão de caracteres. Máximo de páginas configurável (1–100, padrão 35).

Execute PDFs externos em ambiente isolado, com dependências atualizadas. Validação de IP não substitui firewall de saída: há janela de DNS rebinding.

## Validação

```sh
python -m unittest -v
```

32 testes automatizados: casos originais de filtragem; preservação de relatórios em duplicatas e reanálises; decisões com histórico; revogação do TXT; alteração/caminho do PDF; campos auxiliares; normalização Unicode; ações ativas; limites de páginas e tempo; geração real de PNG de prévia; CSV; arquivos corrompidos; downloads simulados e limpeza de temporários; texto fora da área visível; fundo heterogêneo; alteração entre análise/cópia e symlinks de fuga.

Interface Tkinter ainda sem validação visual neste ambiente. Downloads foram testados com respostas simuladas, não com servidor externo real. Os testes não comprovam detecção de todos os ataques.

## Arquivos

- app.py: análise, download, lote e configuração.
- workflow.py: gravação atômica, hashes, revisão e exportação.
- review_ui.py: fila de revisão e prévia.
- test_app.py e test_revision.py: testes.
- requirements.txt: dependências.

## Histórico de revisão e limites operacionais

Relatórios JSON têm identificadores únicos, SHA-256, configuração, versão e eventos de revisão. As gravações são atômicas individualmente; movimentação de PDF, JSON e TXT não é uma transação única. Interrupção do SO pode exigir conciliação manual. Trabalhe com uma instância do aplicativo por pasta de saída; não há bloqueio entre processos concorrentes. Histórico é registro local, não assinatura digital nem autenticação do nome do revisor. PDF original de entrada não é alterado; cópias organizadas são movidas na revisão.

Relatórios podem conter dados pessoais. CSV não contém texto integral nem amostras. Guarde a pasta de saída de acordo com as regras de acesso da sua organização.
