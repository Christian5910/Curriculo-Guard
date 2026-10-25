# Currículo Guard para Windows: executável portátil e instalador

Este guia explica tudo sobre a pasta `EXE`, partindo do princípio de que você **nunca criou um executável**. Se você só quer usar o programa, leia as seções 1 a 4. As seções seguintes explicam como ele foi feito e como refazê-lo.

## 1. Resumo em um minuto

| Quero... | Faça isto |
| --- | --- |
| Usar o programa agora, sem instalar nada | Abra `CurriculoGuard-Portatil` e dê dois cliques em **`CurriculoGuard.exe`** |
| Levar para um pendrive ou outro computador | Copie a pasta **`CurriculoGuard-Portatil` inteira** |
| Instalar como um programa comum (atalhos, desinstalar) | Execute **`CurriculoGuard-Setup.exe`** |
| Refazer tudo depois de mudar o código | `python EXE\construcao\construir.py` (seção 6) |

Serve para **Windows 10 ou 11, 64 bits**. Não precisa ter Python instalado, nem ser administrador, nem ter internet (só o download opcional de PDFs por URL usa a internet).

## 2. O que existe nesta pasta

```
EXE/
├─ LEIA-ME.md                     este guia
├─ CurriculoGuard-Portatil/       o programa pronto, sem instalar (132 MB)
│   ├─ CurriculoGuard.exe         o que você abre com dois cliques
│   ├─ LEIA-ME.txt                versão curta deste guia
│   ├─ app/                       o código do Currículo Guard
│   └─ runtime/                   o Python e as bibliotecas que o programa usa
├─ CurriculoGuard-Setup.exe       o instalador (33 MB)
└─ construcao/                    tudo o que FEZ os dois arquivos acima
    ├─ construir.py               o script que monta tudo
    ├─ verificar_portatil.py      autoteste da pasta portátil
    ├─ lancador/                  código do CurriculoGuard.exe (C) e o .exe já compilado
    ├─ instalador/instalador.nsi  receita do instalador
    ├─ LEIA-ME-portatil.txt       o texto que vai dentro da pasta portátil
    └─ versoes_empacotadas.txt    lista exata do que foi empacotado (com SHA-256)
```

> **Importante:** o `CurriculoGuard.exe` **sozinho não funciona**. Ele é só o "botão de ligar": precisa das pastas `app` e `runtime` ao lado dele. Se você o mover para outro lugar, aparece uma mensagem explicando isso.

## 3. Versão portátil

**Como usar:** dois cliques em `CurriculoGuard-Portatil\CurriculoGuard.exe`. Na primeira vez pode levar alguns segundos a mais (o Windows verifica os arquivos).

**Onde ficam os resultados:** na pasta `dados`, criada ao lado do `CurriculoGuard.exe` (a pasta `triagem` fica dentro dela). Você pode trocar a pasta de saída dentro do programa, como sempre.

**Como remover:** apague a pasta. Nada é gravado fora dela, nem no registro do Windows.

**Quando escolher esta:** pendrive, computador de outra pessoa, ambiente onde você não pode instalar programas, ou quando quer ter várias versões lado a lado.

## 4. Instalador

**Como usar:** dois cliques em `CurriculoGuard-Setup.exe` e siga as telas (em português). Você escolhe a pasta e se quer o atalho na Área de Trabalho.

O que ele faz, e o que **não** faz:

| Faz | Não faz |
| --- | --- |
| Instala para o seu usuário em `%LOCALAPPDATA%\Programs\Curriculo Guard` | Não pede senha de administrador |
| Cria atalho no Menu Iniciar (e, se você marcar, na Área de Trabalho) | Não altera o sistema nem outros usuários |
| Aparece em *Configurações > Aplicativos* para desinstalar | Não instala Python nem outros programas |
| Atualiza uma instalação anterior por cima | Não apaga os seus resultados ao atualizar ou desinstalar |

**Onde ficam os resultados (instalado):** em *Documentos\Curriculo Guard* (a pasta `triagem` fica dentro). É diferente do portátil de propósito: assim os seus dados não ficam dentro da pasta do programa e **sobrevivem** a uma atualização ou desinstalação.

**Como desinstalar:** *Configurações > Aplicativos > Currículo Guard > Desinstalar*, ou o `Desinstalar.exe` na pasta do programa. Os resultados em Documentos continuam lá (apague à mão se quiser).

## 5. Avisos do Windows e do antivírus

**"O Windows protegeu o seu computador" (SmartScreen).** Aparece porque o programa **não tem assinatura digital**. Clique em **Mais informações** e depois em **Executar assim mesmo**. Esse aviso não significa que há algo errado: ele surge para qualquer programa novo e sem assinatura. A única forma de eliminá-lo é assinar o executável com um certificado de assinatura de código, que é pago e que este projeto não tem.

**Antivírus.** Programas pequenos, novos e sem assinatura, como o `CurriculoGuard.exe`, às vezes são marcados por engano. Se isso acontecer, restaure o arquivo da quarentena e adicione a pasta às exceções. Se tiver dúvida, você pode conferir que nada foi alterado: `versoes_empacotadas.txt` lista o SHA-256 de tudo o que vem de fora, e o código do lançador (`lancador/lancador.c`, 88 linhas) mostra exatamente o que ele faz: abre o Python da pasta `runtime` com o `app.py`. Ele não acessa a internet nem grava nada além da pasta de dados.

**Computadores de empresa.** Políticas como AppLocker podem bloquear programas que rodam fora de `Program Files`. Nesse caso peça ao suporte para liberar a pasta.

## 6. Como foi feito (explicação para quem nunca fez um executável)

### O problema

O Currículo Guard é escrito em **Python**, que não gera um `.exe` sozinho: um programa Python é um conjunto de arquivos de texto que precisa de um **interpretador Python** instalado para rodar. Quem não tem Python não consegue abrir o programa.

### As três saídas comuns

1. **"Congelar"** o programa com ferramentas como PyInstaller ou Nuitka, que juntam tudo num `.exe` só.
2. **Embutir o Python** numa pasta junto do programa e criar um pequeno `.exe` que o abre. *(o que fizemos)*
3. **Um instalador que instala o Python** no computador do usuário.

Escolhemos a segunda porque é a mais simples de entender e de consertar: não existe mágica, é só uma pasta com o Python dentro. Também começa mais rápido que um `.exe` único (que precisa se descompactar a cada abertura), e permite abrir qualquer arquivo e ver o que está ali. O custo é entregar uma pasta em vez de um arquivo só, e foi por isso que também fizemos o instalador (que entrega a pasta de forma limpa).

### Como o duplo clique funciona

```
você dá dois cliques em CurriculoGuard.exe
        │
        ▼  (o lançador, 40 KB, escrito em C)
   1. descobre em que pasta está
   2. escolhe a pasta de dados (portátil: ./dados  |  instalado: Documentos)
   3. abre  runtime\pythonw.exe  app\app.py      ← o Python embutido
        │
        ▼
   o Currículo Guard abre como sempre
```

### As peças

| Peça | O que é | De onde vem |
| --- | --- | --- |
| `runtime/` | Python 3.12 para Windows, **com o Tk** (a interface gráfica) | Projeto *python-build-standalone*, baixado do GitHub com SHA-256 conferido |
| `runtime/Lib/site-packages/` | PyMuPDF, NumPy, requests, pdfium... as versões **para Windows** | Baixadas do PyPI com `pip download --platform win_amd64` (não são executadas durante o build) |
| `app/` | O programa: `app.py`, a pasta `curriculo_guard/` e os ícones | Copiados do projeto |
| `CurriculoGuard.exe` | O lançador, que abre o Python com o `app.py` | `construcao/lancador/`, compilado com MinGW-w64 |
| `CurriculoGuard-Setup.exe` | O instalador | `construcao/instalador/instalador.nsi`, compilado com NSIS |

Um detalhe importante: nada disso precisa ser **executado** no Windows para ser montado. Os arquivos do Python e das bibliotecas só são copiados. Por isso foi possível montar tudo a partir do Linux, e por isso o `construir.py` roda igualmente em Windows, Linux ou macOS.

### Uma armadilha que foi encontrada

Os testes feitos fora do Windows (veja a seção 8) passavam, mas uma **análise das DLLs** mostrou que o PyMuPDF depende da `msvcp140.dll`, do Visual C++, e não a traz. Num Windows limpo, sem o Visual C++ instalado, o programa falharia ao abrir PDFs. O `construir.py` agora lê as dependências de todos os arquivos do pacote, completa essa DLL a partir da cópia que o NumPy já traz (a Microsoft permite distribuí-la junto do programa) e **interrompe o build** se faltar qualquer outra DLL que não seja do próprio Windows.

## 7. Como refazer o executável

Faça isto sempre que **mudar o código** do programa, para o executável refletir a mudança.

**O que precisa ter:** Python 3.9 ou mais novo (qualquer um, no seu computador) e internet na primeira vez. O NSIS é opcional e só serve para gerar o instalador: baixe em <https://nsis.sourceforge.io>, instale com as opções padrão, e o script o encontra sozinho.

No PowerShell, na raiz do projeto:

```powershell
python EXE\construcao\construir.py              # pasta portátil + instalador (se o NSIS estiver instalado)
python EXE\construcao\construir.py --zip        # também cria CurriculoGuard-Portatil.zip
python EXE\construcao\construir.py --sem-instalador
python EXE\construcao\construir.py --atualizar  # baixa o Python e as bibliotecas de novo
```

Na primeira vez baixa uns 120 MB (guardados em `construcao/cache/`), então o tempo depende da sua internet; nas seguintes leva poucos segundos para a pasta portátil e algumas dezenas de segundos a mais para o instalador (a compressão é a parte lenta). Ao final, ele confere os arquivos essenciais e as DLLs, e mostra onde estão os resultados.

**Para conferir que o resultado funciona**, rode o autoteste, que usa o Python **embutido** (o mesmo que o usuário final executará):

```powershell
EXE\CurriculoGuard-Portatil\runtime\python.exe EXE\construcao\verificar_portatil.py
```

Ele importa todas as bibliotecas, analisa três PDFs de teste e termina com `TUDO CERTO` (código 0) ou lista o que falhou.

**Atualizar as versões embutidas.** O Python embutido e o seu SHA-256 estão fixos no topo do `construir.py` (`PYTHON_URL` e `PYTHON_SHA256`). Para usar outro Python, troque os dois. As bibliotecas seguem o `requirements.txt` (mais o `pypdfium2`). A lista exata do que foi empacotado fica em `versoes_empacotadas.txt`.

**Mudar o lançador (raro).** Só é preciso se você quiser alterar o `lancador.c`. Ele já vem compilado em `lancador/CurriculoGuard.exe`. Para recompilar, use o script `compilar_lancador.sh` num Linux (ou no WSL do Windows) com o pacote `gcc-mingw-w64-x86-64`.

## 8. O que foi testado, e o que não foi

O ambiente onde isto foi montado **não tinha Windows**. Por isso a verificação foi feita com o **Wine** (uma camada que roda programas de Windows no Linux), que é um bom indicador, mas **não substitui** um Windows de verdade.

| Verificado no Wine 11 | Resultado |
| --- | --- |
| Python embutido abre e importa tkinter, NumPy, PyMuPDF, requests, pdfium e o programa | ok |
| Análise completa de PDFs (currículo limpo, texto escondido, injeção), com os processos filhos do Windows | resultado correto |
| `CurriculoGuard.exe` abre a interface e cria a pasta `dados` | ok |
| Instalador: instala, atualiza por cima, cria atalhos e entrada de desinstalação | ok |
| Programa instalado: usa *Documentos*; desinstalar remove tudo **e preserva os dados** | ok |
| Todas as DLLs não pertencentes ao Windows estão no pacote (análise estática dos 69 binários) | ok, depois da correção da seção 6 |

**Não foi testado e vale testar você mesmo:**

- Um Windows 10/11 de verdade, principalmente um computador "limpo". O job `portatil-windows` da integração contínua (`.github/workflows/tests.yml`) monta o portátil num Windows real, roda o autoteste e abre o `CurriculoGuard.exe` a cada alteração enviada ao GitHub. Isso cobre a montagem, mas não o duplo clique de uma pessoa.
- O aviso do SmartScreen e o comportamento de antivírus específicos.
- Telas de alta resolução com escala de 125% a 200%: a interface pode ficar levemente borrada.
- Instalar em pasta com acento no nome ou em conta sem permissão de gravação em `%LOCALAPPDATA%`.

Se algo falhar, execute `runtime\python.exe app\app.py` pelo PowerShell (a janela preta mostra a mensagem de erro, que o `CurriculoGuard.exe` esconde) e envie o texto.

## 9. Perguntas frequentes

**Dei dois cliques e nada aconteceu.** Espere até 10 segundos na primeira vez. Se continuar, veja se o antivírus bloqueou o arquivo e tente o comando da seção 8 para ler o erro.

**Apareceu "Os arquivos do programa não foram encontrados".** O `CurriculoGuard.exe` foi separado das pastas `app` e `runtime`. Mantenha os três juntos.

**O instalador pediu senha de administrador.** Não deveria. Ele instala só para o seu usuário. Se pediu, algo na sua máquina intercepta o instalador; use a versão portátil.

**Posso colocar a pasta portátil em um pendrive?** Sim. Os resultados ficam no próprio pendrive, na pasta `dados`.

**Posso ter o portátil e o instalado ao mesmo tempo?** Sim, não interferem: o instalado guarda os dados em *Documentos* e o portátil em `dados`.

**Como atualizo?** Instalado: execute o novo `CurriculoGuard-Setup.exe` por cima. Portátil: substitua a pasta (copie antes a pasta `dados` se quiser manter os resultados).

**O programa envia dados para algum lugar?** Não. A única conexão de rede é o download opcional de PDFs por URL, que você mesmo informa, com as proteções descritas no `README.md`.

**Por que tem 132 MB?** O Python, o Tk, o PyMuPDF, o NumPy e o pdfium vêm junto, para o programa não depender de nada instalado no computador. O instalador é menor (33 MB) porque comprime tudo.

## 10. O que entra no Git e o que não entra

Os arquivos **gerados** (a pasta portátil, o instalador e o `cache`) pesam centenas de MB e podem ser refeitos a qualquer momento, então ficam **fora do Git** (`.gitignore`). O GitHub, aliás, recusa arquivos maiores que 100 MB. Entram no Git os arquivos que **geram** tudo: `construir.py`, o lançador (código e `.exe`), a receita do instalador e este guia.

Para distribuir o programa a outras pessoas, use a aba **Releases** do GitHub: gere o `--zip`, crie uma *release* e anexe o `CurriculoGuard-Setup.exe` e o `CurriculoGuard-Portatil.zip`.
