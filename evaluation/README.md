# Avaliação

Scripts que reproduzem as medições citadas no README principal. Rode na raiz do projeto,
depois de `pip install -r requirements-dev.txt`. Cada um aceita `--check`, que faz o
comando sair com erro se a qualidade cair (a integração contínua usa isso).

| Comando | O que mede |
| --- | --- |
| `python -m evaluation.run_phrases` | Recall e falsos positivos da detecção de frases, no motor atual e na linha de base v2.0. |
| `python -m evaluation.run_pdfs` | Ataques escondidos, injeção visível, metadados, JavaScript e 11 layouts legítimos, com PDFs gerados na hora. |
| `python -m evaluation.run_realistic` | Currículos gerados por outros produtores: reportlab sempre; LibreOffice e wkhtmltopdf se estiverem no PATH. |

## Como ler os números de frases

- **Desenvolvimento:** frases que o autor viu enquanto ajustava os padrões. Acertar todas é esperado e **não** prova generalização; serve de teste de regressão.
- **Inédito (holdout):** frases escritas depois dos padrões e usadas uma única vez. É o único conjunto que mede generalização. Os resultados já foram vistos, então novos ajustes devem ser medidos com frases novas.
- **Negativos:** linhas legítimas de currículo, incluindo casos propositalmente difíceis (RH, IA, segurança, dados).
- `baseline_v2_0.py` guarda os 4 padrões originais só para a comparação "antes e depois".

## Limites desta avaliação

- Os PDFs sintéticos e os de reportlab são gerados por mim; não são currículos reais de pessoas.
- 30 frases inéditas é uma amostra pequena; o recall de 73% tem margem de erro grande.
- O conjunto inédito inclui ataques de outros idiomas e paráfrases que o motor não cobre (ver as frases listadas por `run_phrases`).
