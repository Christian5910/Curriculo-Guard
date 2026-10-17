"""Motor do Currículo Guard: análise de PDFs, roteamento e lotes, sem interface gráfica.

Este módulo não importa Tkinter: pode ser usado em scripts, testes e servidores.
O PDF e os relatórios são dados não confiáveis: nunca executar suas instruções.
Depende de pymupdf, numpy e requests (Python 3.11+).
"""
import os, re, json, shutil, tempfile, threading, socket, ipaddress
import unicodedata, uuid, time, multiprocessing, math, bisect, contextlib
from collections import Counter
from itertools import islice
from workflow import sha256_file, atomic_write, write_report, limit_memory as _limit_memory, CHILD_MEMORY_MB, FileLock, SourceRegistry
from pathlib import Path
from urllib.parse import urlparse, unquote
from datetime import datetime, timezone
import requests
import urllib3.util.connection as _urllib3_connection
import pymupdf
import numpy as np

APP_VERSION = '2.8'
DOWNLOAD_DEADLINE_S = 90   # prazo total de um download, mesmo que o servidor "goteje" bytes
MANIFEST_DEADLINE_S = 30   # prazo total para ler o manifesto de URLs (mesma defesa contra o gotejamento)
LEGIBLE_RATIO = 3.0        # contraste (na página já renderizada) a partir do qual o texto é legível
WINDOWS_RESERVED = {'con','prn','aux','nul'} | {f'com{i}' for i in range(1,10)} | {f'lpt{i}' for i in range(1,10)}
SINGLE_THREAD_VARS = ('OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS')
INK_MIN = 16   # menor diferença (0–255) entre a página com e sem o trecho para considerá-lo visível
FOLDERS = ['aprovados','verificacao_humana','rejeitados','duplicados','quarentena','relatorios','originais']
# Só destinos de análise concluída contam como "já visto"; quarentena pode ser falha transitória.
INDEXED = ('aprovados','verificacao_humana','rejeitados')
MAX_BYTES = 15 * 1024 * 1024
# Padrões heurísticos de frases comuns de injeção (PT/EN). A cobertura é limitada
# por natureza: servem para levar o documento à revisão humana, não para garantir
# ausência de ataque. Os nomes dos grupos alimentam as regras da aba "Destinos".
_IGN = r'(?:ignore|disregard|forget|override|bypass|discard)'
_DET = r'(?:(?:all|any|every|your|my|these|those|the|of)\s+)*'
_PREV = r'(?:(?:previous|prior|above|earlier|preceding|former|original|system|safety)\s+){1,2}'
_NOUN = r'(?:instructions?|prompts?|rules|directions|guidelines|commands|programming|context|messages?)'
_VERB_AVALIA = r'(?:approve|hire|shortlist|recommend|rank|rate|score|grade|classify|prioritize|endorse|give|assign|award|grant)'
_OBJ_AVALIA = (r"(?:(?:this|the|my|our|its|that)\s+(?:candidate|resume|r[eé]sum[eé]|cv|applicant|profile|person)|(?:every|each)\s+(?:candidate|resume|r[eé]sum[eé]|cv|applicant))\b"
               r"(?!\s+(?:pool|pipeline|funnel|database|list|data|experience|screening|tracking|sourcing))")
_NOTA_EN = r'(?:(?:highest|maximum|perfect|max|top)\s+(?:possible\s+)?(?:score|rating|rank|ranking|grade|marks?|points))'
_ALVO_IA = (r"(?:ai|a\.i\.|llm|chatgpt|gpt|chatbot|language\s+model|assistant|model|ats|bots?|algorithm|"
            r"screening\s+\w+|automated\s+\w+)")
PATTERNS = [
    # --- instrucao_ia: pedido para ignorar ou trocar as instruções do avaliador ---
    ('instrucao_ia', r'(?i)\b' + _IGN + r'\s+' + _DET + _PREV + _NOUN + r'\b'),
    ('instrucao_ia', r'(?i)\b' + _IGN + r'\s+' + _DET + r'(?:instructions|directions|guidelines)\b'),
    ('instrucao_ia', r'(?i)\b(?:ignore|disregard|forget)\s+(?:the\s+|all\s+of\s+the\s+|everything\s+)above\b'
                     r'|\b(?:ignore|disregard|forget)\s+everything\b'
                     r'|\b(?:forget|disregard)\s+(?:what|anything)\s+(?:you|that)\s+(?:were|was|have\s+been|know|learned)\b'),
    ('instrucao_ia', r"(?i)\byou\s+are\s+now\b"
                     r"|\bfrom\s+now\s+on\b(?:\s+[\w'-]+){0,4}?\s+(?:you|your|act|respond|answer|rate|always)\b"
                     r"|\b(?:act|behave|respond|pretend)\s+(?:as|like)\s+(?:an?|the)\s+(?:\w+\s+){0,2}?(?:ai|assistant|recruiter|evaluator|reviewer|screener|hr|hiring)\b"
                     r"|\bpretend\s+(?:you\s+are|to\s+be)\b"),
    ('instrucao_ia', r"(?i)\b(?:note|message|memo|attention|hey|hello|dear)\s+(?:to|for)\s+(?:the\s+)?" + _ALVO_IA + r"\s*[:,!–-]"
                     r"|\bas\s+an?\s+(?:ai|llm|language\s+model|assistant)\b(?:\s+[\w'-]+){0,6}?\s+(?:must|should|need\s+to|have\s+to|shall)\b"
                     r"|\bif\s+you\s+are\s+(?:an?\s+)?(?:ai|llm|language\s+model|assistant|chatbot)\b"),
    ('instrucao_ia', r'(?i)\bnew\s+(?:instructions?|task|objective|directives?)\s*:'),
    ('instrucao_ia', r'(?i)\b' + _IGN + r'\s+' + _DET + r'(?:job\s+description|requirements|criteria|rubric|screening\s+\w+|evaluation\s+\w+)\b'),
    ('instrucao_ia', r"(?i)\b(?:do\s+not|don'?t|never)\s+(?:mention|reveal|disclose|tell|say|cite)\b(?:\s+[\w'-]+){0,6}?\s+(?:this|these|hidden|text|instructions?|message)\b"),
    ('instrucao_ia', r'(?i)\b(?:ignor(?:e|ar)|desconsider(?:e|ar)|esque[cç]a|esquecer|descart(?:e|ar)|desobede[cç]a|desrespeite)\s+(?:(?:todas?|quaisquer|as|os|suas?|seus?|aquelas?)\s+)*'
                     r'(?:instru[cç][oõ]es|regras|orienta[cç][oõ]es|diretrizes|comandos|ordens)\b'),
    ('instrucao_ia', r"(?i)\besque[cç]a\s+tudo\b|\bvoc[eê]\s+agora\s+[eé]\b"
                     r"|\ba\s+partir\s+de\s+agora\b(?:\s+[\w-]+){0,4}?\s+(?:voc[eê]|aja|responda|avalie)\b"
                     r"|\bse\s+voc[eê]\s+(?:[eé]|for)\s+(?:uma?\s+)?(?:ia|intelig[eê]ncia\s+artificial|modelo\s+de\s+linguagem|assistente|chatbot)\b"
                     r"|\b(?:nota|mensagem|aviso|recado|aten[cç][aã]o|ol[aá])\s+(?:(?:para|à)\s+)?(?:a\s+)?(?:ia|i\.a\.|intelig[eê]ncia\s+artificial|modelo|assistente|chatbot|ats|rob[oô])\s*[:,!–-]"),
    ('instrucao_ia', r"(?i)\bn[aã]o\s+(?:mencione|revele|divulgue|diga|cite)\b(?:\s+[\w-]+){0,6}?\s+(?:est[ea]|ess[ea]|texto|instru[cç][oõ]es|mensagem|oculto)\b"),
    # --- papel_sistema: marcadores de papel/sistema e pedidos para revelar o prompt ---
    ('papel_sistema', r'(?i)\[\s*/?\s*(?:system|developer|assistant|inst|sys)\s*\]|<<\s*/?\s*sys\s*>>'
                      r'|<\|\s*(?:im_start|im_end|system|assistant|user|endoftext|eot_id|start_header_id|end_header_id)\s*\|>'),
    ('papel_sistema', r'(?i)<\s*(?:system|developer|assistant)\s*>[^<]{0,200}?\b(?:you|your|must|ignore|always|never|rate|rank|approve)\b'),
    ('papel_sistema', r'(?i)#{2,}\s*(?:system|developer|instructions?|task)\s*(?:prompt|message|instructions?)?\s*:|\b(?:system|developer)\s*:\s*you\b|\bnew\s+system\s+prompt\b'),
    ('papel_sistema', r"(?i)\b(?:reveal|show|print|repeat|output|display|leak|disclose|share)\b(?:\s+[\w'-]+){0,3}?\s+"
                      r"(?:system\s+prompt|developer\s+message|hidden\s+prompt|initial\s+prompt|your\s+(?:instructions|prompt))\b"
                      r"|\b(?:revele|mostre|imprima|repita|vaze)\b(?:\s+[\w-]+){0,3}?\s+(?:prompt\s+do\s+sistema|mensagem\s+do\s+sistema|suas\s+instru[cç][oõ]es)\b"),
    # --- comando_avaliacao: tentativa de ditar a nota ou a decisão sobre o candidato ---
    ('comando_avaliacao', r"(?i)\b" + _VERB_AVALIA + r"\b(?:\s+[\w'-]+){0,4}?\s+" + _OBJ_AVALIA),
    ('comando_avaliacao', r"(?i)\b(?:give|assign|award|grant|rate|score|grade|rank)\b(?:\s+[\w'/%-]+){0,5}?\s+" + _NOTA_EN + r"\b"),
    ('comando_avaliacao', r"(?i)\b(?:this|the)\s+(?:following\s+)?(?:candidate|resume|r[eé]sum[eé]|cv|applicant)\s+(?:is|should\s+be|must\s+be|deserves?)\s+(?:\w+\s+){0,2}?"
                          r"(?:best|ideal|perfect|exceptional|outstanding|top|highly\s+qualified|hired|shortlisted|approved|ranked\s+first|first|chosen|selected)\b"),
    ('comando_avaliacao', r"(?i)\b(?:treat|consider|mark|label|flag|regard|classify)\s+(?:this|my)\s+(?:candidate|resume|r[eé]sum[eé]|cv|applicant|profile)\s+as\b"
                          r"|\b(?:state|say|write|report|output|respond|answer|conclude)\s+that\s+(?:this|the)\s+(?:candidate|applicant)\b"
                          r"|\b(?:be\s+sure\s+to|make\s+sure\s+to|remember\s+to)\s+(?:mention|say|state|write|report)\b(?:\s+[\w'-]+){0,6}?\s+(?:ideal|best|perfect|exceptional|top)\s+(?:candidate|fit|match)\b"),
    ('comando_avaliacao', r"(?i)\b(?:aprove|contrate|recomende|selecione|classifique|priorize|pontue|avalie|atribua)\b(?:\s+[\w'-]+){0,4}?\s+"
                          r"(?:est[ea]|ess[ea]|o|a|meu|minha)\s+(?:candidat[oa]|curr[ií]culo|perfil)\b"),
    ('comando_avaliacao', r"(?i)\b(?:atribua|dê|conceda|pontue|avalie|classifique)\b(?:\s+[\w'/%-]+){0,5}?\s+"
                          r"(?:nota\s+m[aá]xima|pontua[cç][aã]o\s+m[aá]xima|maior\s+nota|maior\s+pontua[cç][aã]o|nota\s+(?:10|dez))\b"),
    ('comando_avaliacao', r"(?i)\b(?:este|esse|o)\s+(?:candidato|curr[ií]culo|perfil)\s+(?:[eé]|deve\s+ser|precisa\s+ser|merece)\s+(?:\w+\s+){0,2}?"
                          r"(?:o\s+melhor|o\s+primeiro|primeiro|ideal|perfeito|excepcional|excelente|altamente\s+qualificado|contratado|aprovado|selecionado|escolhido)\b"),
    # --- exfiltracao: pedido para enviar dados/currículos/segredos a um destino externo ---
    ('exfiltracao', r"(?i)\b(?:send|forward|email|e-mail|post|upload|transmit|leak|exfiltrate|share|copy|export)\b(?:\s+[\w'-]+){0,4}?\s+"
                    r"(?:this|these|all|every|the|your|my|its|any)\s+(?:\w+\s+){0,3}?"
                    r"(?:resumes?|r[eé]sum[eé]s?|cvs?|candidates?|applicants?|conversations?|chat\s+history|prompts?|system\s+prompt|credentials?|api\s+keys?|secrets?|passwords?|tokens?|data|files?|documents?|information|details)\b"
                    r"[^.]{0,100}?(?:https?://\S+|[\w.+-]+@[\w-]+\.[\w.-]+|\bto\s+(?:an?\s+|the\s+)?(?:external|remote)\s+(?:server|url|address|email|endpoint))"),
    ('exfiltracao', r"(?i)\b(?:envie|encaminhe|transmita|compartilhe|vaze|publique|exporte|copie)\b(?:\s+[\w'-]+){0,4}?\s+"
                    r"(?:est[ea]s?|ess[ea]s?|tod[oa]s?(?:\s+(?:os|as))?|os|as|seus?|suas?|meus?|minhas?)\s+(?:\w+\s+){0,3}?"
                    r"(?:curr[ií]culos?|candidat[oa]s?|conversas?|hist[oó]rico|prompts?|credenciais|chaves?|segredos?|senhas?|tokens?|dados|arquivos?|documentos?|informa[cç][oõ]es)\b"
                    r"[^.]{0,100}?(?:https?://\S+|[\w.+-]+@[\w-]+\.[\w.-]+)"),
]

# Frases de injeção que sobrevivem à normalização apenas quando as letras estão
# separadas por espaços/pontuação; comparadas sobre o texto "achatado".
SQUASHED_PHRASES = (
    'ignorepreviousinstructions', 'ignoreallpreviousinstructions', 'ignorethepreviousinstructions',
    'ignorepriorinstructions', 'ignoreallpriorinstructions', 'disregardpreviousinstructions',
    'disregardtheabove', 'ignoretheabove', 'forgeteverything', 'ignoretodasasinstrucoes',
    'ignoreasinstrucoesanteriores', 'desconsidereasinstrucoesanteriores', 'esquecatudo',
)

_NAT64 = ipaddress.ip_network('64:ff9b::/96')   # tradução IPv6→IPv4 (RFC 6052): o IPv4 de destino vai nos últimos 32 bits


def _is_public_ip(text):
    """IP roteável na internet pública (multicast, privado, local e reservado ficam de fora).

    Endereços IPv6 que apenas embrulham um IPv4 (mapeado `::ffff:`, NAT64 `64:ff9b::/96`, 6to4) são
    julgados pelo IPv4 embutido: `64:ff9b::7f00:1` aponta para 127.0.0.1 e `is_global` sozinho o deixa passar
    (e o tratamento varia entre versões do Python). Teredo nunca é aceito.
    """
    ip = ipaddress.ip_address(text.split('%')[0])
    if ip.version == 6:
        if ip.teredo is not None: return False
        embedded = ip.ipv4_mapped or ip.sixtofour or (ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF) if ip in _NAT64 else None)
        if embedded is not None: return _is_public_ip(str(embedded))
    return ip.is_global and not ip.is_multicast


def has_pdf_header(path):
    """Aceita '%PDF-' nos primeiros 1024 bytes, como Acrobat e MuPDF (servidores às vezes antepõem BOM ou linhas em branco)."""
    with Path(path).open('rb') as stream: return b'%PDF-' in stream.read(1024)


def valid_folder_name(name, reserved=()):
    """Nome de pasta aceito em Windows, macOS e Linux: sem separadores, sem ser só espaço/hífen,
    sem espaço nas pontas, sem nome reservado do Windows e sem colidir com pastas fixas."""
    return bool(isinstance(name, str) and re.fullmatch(r'[\w -]{1,40}', name) and re.search(r'\w', name)
                and name == name.strip() and name.casefold() not in WINDOWS_RESERVED
                and name.casefold() not in {r.casefold() for r in reserved})


def is_public_https(url):
    """Valida protocolo e IPs públicos (falha rápida, com mensagem clara).

    Não basta sozinha: o IP é conferido de novo, no momento da conexão, por `strict_egress()`, que fecha a
    janela de DNS rebinding. Um firewall de saída continua sendo uma boa defesa adicional.
    """
    if any(ord(ch) <= 32 or ord(ch) == 127 for ch in url): raise ValueError('URL com espaços ou caracteres de controle.')
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Somente HTTPS público na porta 443 é permitido.')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not _is_public_ip(a[4][0]) for a in addresses):
        raise ValueError('Destino privado, local ou não público bloqueado.')
    return url


_egress = threading.local()
_original_create_connection = _urllib3_connection.create_connection


def _guarded_create_connection(address, *args, **kwargs):
    """Conecta só a IPs públicos quando `strict_egress()` está ativo nesta thread.

    `is_public_https` valida o DNS e o `requests` resolve o nome DE NOVO ao conectar; um DNS hostil
    responde com IP público na primeira consulta e com 127.0.0.1 na segunda (DNS rebinding). Aqui a
    resolução acontece uma única vez, no momento da conexão: todos os IPs são conferidos e a conexão
    é feita direto no IP já validado, sem nova consulta. Fora de `strict_egress()` nada muda.
    """
    if not getattr(_egress, 'strict', False): return _original_create_connection(address, *args, **kwargs)
    host, port = address
    infos = socket.getaddrinfo(host.strip('[]'), port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(info[4][0] for info in infos))
    if not addresses or any(not _is_public_ip(a) for a in addresses):
        raise ValueError('Destino privado, local ou não público bloqueado.')
    last = None
    for ip in addresses:
        try: return _original_create_connection((ip, port), *args, **kwargs)
        except OSError as exc: last = exc
    raise last


_urllib3_connection.create_connection = _guarded_create_connection


@contextlib.contextmanager
def strict_egress():
    """Dentro deste bloco, as conexões da thread atual só alcançam IPs públicos (ver `_guarded_create_connection`)."""
    previous = getattr(_egress, 'strict', False)
    _egress.strict = True
    try: yield
    finally: _egress.strict = previous


def _copy_body(response, write, limit, too_big, deadline, timed_out, cancel=None):
    """Copia o corpo da resposta com teto de bytes, prazo total e cancelamento conferidos a cada chegada de bytes."""
    total = 0
    while True:
        if cancel is not None and cancel.is_set(): raise ValueError('Download cancelado.')
        if time.monotonic() > deadline: raise TimeoutError(timed_out)
        chunk = _read_arrived(response)
        if not chunk: return total
        total += len(chunk)
        if total > limit: raise ValueError(too_big)
        write(chunk)


def _read_arrived(response):
    """Lê o que já chegou do servidor, sem esperar completar um bloco.

    `iter_content(65536)` bloqueia até juntar 64 KB: um servidor que "goteja" 1 byte por
    segundo seguraria o laço por horas, ignorando o prazo e o botão Interromper.
    `read1` (urllib3 2.2+) devolve assim que chega algo, então o laço confere o prazo a cada chegada.
    """
    return response.raw.read1(65536, decode_content=True)


def download_pdf(url, dest, cancel=None):
    """Baixa em temporário e só publica PDF completo; pode cancelar por bloco."""
    is_public_https(url)
    dest = Path(dest)
    partial = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.part')
    deadline = time.monotonic() + DOWNLOAD_DEADLINE_S
    try:
        # Desabilitar proxies de ambiente reduz destinos inesperados; strict_egress confere o IP na conexão.
        with strict_egress(), requests.Session() as session:
            session.trust_env = False
            with session.get(url, stream=True, timeout=(8, 10), allow_redirects=False,
                             headers={'User-Agent':f'CurriculoGuard/{APP_VERSION}'}) as response:
                if 300 <= response.status_code < 400: raise ValueError('Redirecionamento bloqueado.')
                response.raise_for_status()
                with partial.open('wb') as stream:
                    _copy_body(response, stream.write, MAX_BYTES, 'PDF excede 15 MB.', deadline,
                               f'Download excedeu {DOWNLOAD_DEADLINE_S} segundos.', cancel)
        if not has_pdf_header(partial): raise ValueError('Arquivo não tem assinatura PDF.')
        os.replace(partial, dest)
    finally:
        partial.unlink(missing_ok=True)


_LETTER_SEPARATORS = ' \t.\\-_*|·'
_SPACED_LETTERS = re.compile(r'(?<!\S)(?:\w[' + _LETTER_SEPARATORS + r']){3,}\w(?!\S)')
# Letras cirílicas/gregas visualmente idênticas às latinas (só para inspeção).
_CONFUSABLES = str.maketrans({
    'а':'a','е':'e','о':'o','р':'p','с':'c','у':'y','х':'x','і':'i','ј':'j','ѕ':'s','ԁ':'d','һ':'h','ԛ':'q','ԝ':'w',
    'А':'A','В':'B','Е':'E','К':'K','М':'M','Н':'H','О':'O','Р':'P','С':'C','Т':'T','Х':'X','І':'I','Ј':'J','Ѕ':'S',
    'ο':'o','Ο':'O','α':'a','ν':'v','ι':'i','ρ':'p','τ':'t','Α':'A','Β':'B','Ε':'E','Ι':'I','Κ':'K','Μ':'M','Ν':'N','Ρ':'P','Τ':'T','Χ':'X','Υ':'Y','Ζ':'Z',
})


_SURROGATES = re.compile('[\ud800-\udfff]')   # metade solta de par UTF-16: str válida em Python, mas não codificável em UTF-8
_BAD_UNICODE = re.compile('[\ud800-\udfff\ufffd]')


def scrub(value):
    """Troca substitutos Unicode soltos por U+FFFD, recursivamente (str, listas, tuplas e dicionários).

    Um PDF pode mapear glifos para meio par UTF-16 (ToUnicode) e, em Linux/macOS, um nome de arquivo em
    Latin-1 vira substitutos ao ser lido. Tais textos não codificam em UTF-8: sem esta limpeza o relatório
    não é gravado e o arquivo some do lote sem relatório nem quarentena.
    """
    if isinstance(value, str): return _SURROGATES.sub('\ufffd', value) if _SURROGATES.search(value) else value
    if isinstance(value, dict): return {scrub(k): scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [scrub(v) for v in value]
    return value


_TAG_RUN = re.compile('[\U000E0020-\U000E007E]+')
_FLAG_TAGS = re.compile('\U0001F3F4[\U000E0020-\U000E007E]+\U000E007F')   # bandeiras de subdivisão (🏴) usam tags legitimamente
# Controles invisíveis de uso comum em línguas e emoji; só valem alerta em contexto suspeito.
_COMMON_FORMAT = set('\u200b\u200c\u200d\u200e\u200f\u061c\u2060\ufeff\u00ad')


def suspicious_format_characters(text):
    """Caracteres invisíveis (categoria Cf) que merecem revisão.

    Ignora usos comuns: LRM/RLM em hebraico e árabe, ZWNJ/ZWJ em persa, hindi e emoji, hífen suave, BOM.
    São suspeitos: bidi override/isolate, tags Unicode, operadores invisíveis, qualquer Cf incomum,
    sequências de 3 ou mais, e invisíveis entre duas letras/dígitos ASCII (comum em ofuscação).
    """
    text = _FLAG_TAGS.sub('', text)
    found, i, size = [], 0, len(text)
    while i < size:
        if unicodedata.category(text[i]) != 'Cf': i += 1; continue
        j = i
        while j < size and unicodedata.category(text[j]) == 'Cf': j += 1
        run, before, after = text[i:j], text[i-1] if i else '', text[j] if j < size else ''
        uncommon = [c for c in run if c not in _COMMON_FORMAT]
        between_ascii = before.isascii() and before.isalnum() and after.isascii() and after.isalnum()
        if uncommon or len(run) >= 3 or (between_ascii and any(c != '\u00ad' for c in run)):
            found.extend(f'U+{ord(c):04X}' for c in (uncommon or run))
        i = j
    return sorted(set(found))


def _prepare_instruction_text(text):
    """Tags Unicode decodificadas, NFKC, confusáveis cirílicos/gregos e remoção de controles invisíveis."""
    # "ASCII smuggling": mensagem escrita com tags invisíveis (U+E0020–U+E007E) vira texto legível para a busca.
    text = _TAG_RUN.sub(lambda m: ' ' + ''.join(chr(ord(c) - 0xE0000) for c in m.group()) + ' ', text)
    text = unicodedata.normalize('NFKC', text).translate(_CONFUSABLES)
    return ''.join(c for c in text if unicodedata.category(c) != 'Cf')


def normalized_instruction_text(text):
    """Texto preparado, letras separadas recompostas e espaços uniformes."""
    text = _prepare_instruction_text(text)
    # "i g n o r e" / "i.g.n.o.r.e" -> "ignore" (só para inspeção).
    text = _SPACED_LETTERS.sub(lambda m: re.sub('[' + _LETTER_SEPARATORS + ']', '', m.group()), text)
    return re.sub(r'\s+', ' ', text)


def squashed_instruction_text(text):
    """Texto só com letras minúsculas sem acento, para achar frases com letras separadas."""
    text = unicodedata.normalize('NFKD', unicodedata.normalize('NFKC', text).translate(_CONFUSABLES))
    return ''.join(c for c in text.lower() if c.isalpha() and not unicodedata.combining(c))


def instruction_alerts(raw_text):
    """Alertas de possível instrução dirigida à IA para um texto de inspeção."""
    prepared = _prepare_instruction_text(raw_text)
    text = normalized_instruction_text(prepared)
    found = []
    for name, pattern in PATTERNS:
        for m in islice(re.finditer(pattern, text), 8):
            found.append({'type':name,'severity':'review','detail':'Possível instrução dirigida ao avaliador automatizado','sample':text[max(0,m.start()-40):m.end()+40]})
    # Texto achatado ignora pontuação; só é consultado quando há letras separadas
    # (ofuscação), para não casar frases legítimas como "never forget. Everything...".
    if (not any(a['type'] == 'instrucao_ia' for a in found) and _SPACED_LETTERS.search(prepared)
            and any(f in squashed_instruction_text(prepared) for f in SQUASHED_PHRASES)):
        found.append({'type':'instrucao_ia','severity':'review','detail':'Possível instrução dirigida ao avaliador (letras separadas)'})
    return found


def rgb(value):
    """Converte cor inteira 0xRRGGBB em canais RGB."""
    return np.array([(value >> 16) & 255, (value >> 8) & 255, value & 255], dtype=float)

def luminance(v):
    """Calcula luminância relativa sRGB para a estimativa de contraste."""
    v = np.asarray(v, dtype=float) / 255
    v = np.where(v <= .04045, v / 12.92, ((v + .055) / 1.055) ** 2.4)
    return float(np.dot(v, [.2126, .7152, .0722]))

def contrast(a, b):
    """Compara luminâncias: 1 significa cores iguais."""
    l1, l2 = luminance(a), luminance(b)
    return (max(l1, l2) + .05) / (min(l1, l2) + .05)

def _reliable_median(samples):
    """Mediana das amostras de fundo, ou None quando a região é heterogênea."""
    if len(samples) < 10: return None
    # Uma região heterogênea não fornece evidência confiável de fundo local.
    median = np.median(samples, axis=0)
    if np.percentile(np.max(np.abs(samples - median), axis=1), 90) > 35:
        return None
    return median

def local_background(image, rect, scale):
    """Estima fundo pela mediana de um anel externo; não prova cor sob cada glifo."""
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(round(x * scale)) for x in rect]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    m = 5
    a, b, c, d = max(0,x0-m), max(0,y0-m), min(w,x1+m), min(h,y1+m)
    patch = image[b:d, a:c]
    if patch.size == 0: return None
    mask = np.ones(patch.shape[:2], dtype=bool)
    mask[max(0,y0-b):max(0,y1-b), max(0,x0-a):max(0,x1-a)] = False
    return _reliable_median(patch[mask])

def local_backgrounds(image, rect, scale, window=40):
    """Plano B do anel: fundo em janelas horizontais ao longo do trecho (uma por janela).

    Trechos largos sobre gradientes têm fundo diferente em cada ponta; medir por
    janela evita tratar um gradiente suave como fundo indeterminado. Cada janela
    usa só as faixas acima e abaixo do texto (e as laterais nas pontas). Valor
    None indica janela heterogênea (foto, textura): não há estimativa confiável.
    """
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(round(x * scale)) for x in rect]
    x0, x1 = max(0, x0), min(w, x1)
    y0, y1 = max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0: return [None]
    m = 5
    count = max(1, math.ceil((x1 - x0) / window))
    edges = np.linspace(x0, x1, count + 1).astype(int)
    result = []
    for k in range(count):
        a, b = int(edges[k]), int(edges[k + 1])
        ca, cb = max(0, a - (m if k == 0 else 0)), min(w, b + (m if k == count - 1 else 0))
        parts = [image[max(0,y0-m):y0, ca:cb].reshape(-1,3), image[y1:min(h,y1+m), ca:cb].reshape(-1,3)]
        if k == 0: parts.append(image[y0:y1, max(0,a-m):a].reshape(-1,3))
        if k == count - 1: parts.append(image[y0:y1, b:min(w,b+m)].reshape(-1,3))
        result.append(_reliable_median(np.concatenate(parts)))
    return result

_LINEAR = np.array([((v/255)/12.92 if v/255 <= .04045 else (((v/255)+.055)/1.055)**2.4) for v in range(256)])

def text_free_image(scratch, index, dpi):
    """Renderiza a página `index` SEM nenhum texto: o fundo real sob cada trecho.

    `scratch` é uma cópia descartável do documento (aberta uma única vez, nunca
    salva): o texto da página é removido no lugar, sem copiar fontes e imagens a
    cada página (em PDFs com fotos grandes isso era 20 vezes mais lento).
    Imagens e desenhos são preservados. Cada página só deve ser processada uma vez.
    Medir o fundo dentro do próprio retângulo do texto evita o anel externo, que
    confundia réguas e bordas com fundo heterogêneo e deixava passar texto sobre
    um retângulo do mesmo tamanho. Devolve None se falhar (usa-se o anel).
    """
    try:
        page = scratch[index]; page.set_rotation(0)
        page.add_redact_annot(page.rect, fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
        return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3).copy()
    except Exception:
        return None

def ink_difference(image, clean, rect, scale):
    """Diferença (0–255) pixel a pixel entre a página com e sem texto, no retângulo do trecho.

    Devolve (diferença, x0, y0) com a origem do recorte, ou None se o retângulo estiver fora da página.
    Calculada uma vez por trecho e reaproveitada pelas verificações de tinta do trecho e dos caracteres.
    """
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(round(v * scale)) for v in rect]
    x0, x1, y0, y1 = max(0, x0), min(w, x1), max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0: return None
    d = np.abs(image[y0:y1, x0:x1].astype(np.int16) - clean[y0:y1, x0:x1].astype(np.int16))
    return np.maximum(np.maximum(d[..., 0], d[..., 1]), d[..., 2]), x0, y0

def ink_strength(image, clean, rect, scale):
    """Maior diferença (0–255) entre a página com e sem texto dentro do retângulo do trecho.

    Mede a tinta que o trecho realmente deixou na página, independentemente da cor
    declarada: texto de cor igual ao fundo, em modo de mesclagem que o apaga, com
    padrão de preenchimento invisível ou coberto não deixa diferença alguma.
    """
    result = ink_difference(image, clean, rect, scale)
    return None if result is None else int(result[0].max())

def background_contrast(clean, rect, scale, fg):
    """Razão de contraste entre a cor do texto e cada pixel do fundo real do trecho."""
    h, w = clean.shape[:2]
    x0, y0, x1, y1 = [int(round(v * scale)) for v in rect]
    x0, x1, y0, y1 = max(0, x0), min(w, x1), max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0: return None
    lum = _LINEAR[clean[y0:y1, x0:x1].reshape(-1, 3)] @ np.array([.2126, .7152, .0722])
    lf = luminance(fg)
    return (np.maximum(lf, lum) + .05) / (np.minimum(lf, lum) + .05)

def overlap(a, b):
    """Retorna fração da área de A coberta pelo retângulo B."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    area = max(0,x1-x0) * max(0,y1-y0)
    base = max(.00001, (a[2]-a[0]) * (a[3]-a[1]))
    return area / base

def legible_columns(image, clean, rect, scale, ratio_min=LEGIBLE_RATIO):
    """Fração das colunas do trecho em que o texto aparece legível na página já renderizada.

    Compara o contraste entre a página com e sem o texto; um destaque translúcido por cima
    mantém o texto legível, enquanto uma cobertura opaca (ou quase) o apaga.
    """
    h, w = image.shape[:2]
    x0, y0, x1, y1 = [int(round(v * scale)) for v in rect]
    x0, x1, y0, y1 = max(0, x0), min(w, x1), max(0, y0), min(h, y1)
    if x1 <= x0 or y1 <= y0: return 0.0
    weights = np.array([.2126, .7152, .0722])
    shown, bare = _LINEAR[image[y0:y1, x0:x1]] @ weights, _LINEAR[clean[y0:y1, x0:x1]] @ weights
    ratio = (np.maximum(shown, bare) + .05) / (np.minimum(shown, bare) + .05)
    return float((ratio.max(axis=0) >= ratio_min).mean())


def hidden_characters(difference, chars, scale):
    """Índices dos caracteres de um trecho que não deixaram tinta visível na página renderizada.

    A verificação por trecho inteiro perde a cobertura parcial (uma cauda visível "salva" o trecho
    todo). Aqui a diferença entre a página com e sem texto (`ink_difference`) vira uma máscara de
    tinta, e uma tabela de soma acumulada responde, para todos os caracteres de uma vez, se a faixa
    de cada um tem tinta. Espaços, controles e marcas combinantes não deixam tinta e são ignorados.
    """
    if difference is None or not chars: return []
    diff, x0, y0 = difference; height, width = diff.shape
    table = np.zeros((height + 1, width + 1), dtype=np.int32)
    table[1:, 1:] = (diff >= INK_MIN).cumsum(axis=0, dtype=np.int32).cumsum(axis=1, dtype=np.int32)
    boxes = np.rint(np.array([ch['bbox'] for ch in chars], dtype=float) * scale).astype(int)
    bx0, bx1 = np.clip(boxes[:, 0] - x0, 0, width), np.clip(boxes[:, 2] - x0, 0, width)
    by0, by1 = np.clip(boxes[:, 1] - y0, 0, height), np.clip(boxes[:, 3] - y0, 0, height)
    eligible = np.array([not (c['c'].isspace() or unicodedata.category(c['c']) in ('Cf', 'Mn', 'Me', 'Cc')) for c in chars])
    inked = table[by1, bx1] - table[by0, bx1] - table[by1, bx0] + table[by0, bx0]
    return np.flatnonzero(eligible & (bx1 > bx0) & (by1 > by0) & (inked == 0)).tolist()


def covered_fraction(box, others, cell=.5):
    """Fração da área de `box` coberta pela UNIÃO dos retângulos `others`.

    Cobrir o texto com vários retângulos pequenos não deve escapar do limite:
    por isso a união é rasterizada numa grade fina em vez de testar cada objeto.
    """
    x0, y0, x1, y1 = box
    width, height = x1 - x0, y1 - y0
    if width <= 0 or height <= 0: return 0.0
    nx = max(1, min(400, math.ceil(width / cell)))
    ny = max(1, min(80, math.ceil(height / cell)))
    mask = np.zeros((ny, nx), dtype=bool)
    for o in others:
        ox0, oy0, ox1, oy1 = max(x0,o[0]), max(y0,o[1]), min(x1,o[2]), min(y1,o[3])
        if ox1 <= ox0 or oy1 <= oy0: continue
        i0, i1 = round((ox0-x0)/width*nx), round((ox1-x0)/width*nx)
        j0, j1 = round((oy0-y0)/height*ny), round((oy1-y0)/height*ny)
        mask[j0:j1, i0:i1] = True
    return float(mask.mean())

def analyze_pdf(path, reference_dpi=96, analysis_dpi=150, min_px=8,
                contrast_limit=2.0, opacity_limit=.95, overlap_limit=.75,
                enabled=None, max_pages=35):
    """Extrai texto elegível e evidências; contraste/oclusão são estimativas.

    PDF mede fontes em pontos. DPI referência define o limite de leitura;
    DPI análise define somente a resolução da imagem usada para contraste.
    O contraste é medido contra o fundo real (página renderizada sem texto);
    se isso falhar, recai na estimativa pelo anel ao redor do trecho.
    """
    enabled = set(enabled) if enabled is not None else {'size','contrast','opacity','overlap','commands'}
    alerts, texts, metrics = [], [], {'pages':0, 'characters':0, 'small':0, 'low_contrast':0, 'transparent':0, 'overlap':0}
    with pymupdf.open(path) as doc, contextlib.ExitStack() as stack:
        if doc.needs_pass:
            return {'alerts':[{'type':'senha', 'severity':'review', 'detail':'PDF protegido por senha'}], 'text':'', 'metrics':metrics}
        if doc.page_count > max_pages:
            return {'alerts':[{'type':'paginas_excessivas','severity':'review','detail':f'{doc.page_count} páginas; análise interrompida'}], 'text':'', 'metrics':metrics}
        metrics['pages'] = doc.page_count
        scratch = None   # cópia descartável para renderizar as páginas sem texto
        if 'contrast' in enabled:
            try: scratch = stack.enter_context(pymupdf.open(path))
            except Exception: scratch = None
        inspection_parts = [str(v) for v in doc.metadata.values() if v] + [doc.get_xml_metadata()]
        inspection_parts.extend(structural_checks(doc, alerts))
        for pn, page in enumerate(doc, 1):
            # Inspecionar também anotações e campos, ausentes da extração comum.
            for annot in page.annots() or ():
                inspection_parts.extend(str(v) for v in annot.info.values() if v)
                alerts.append({'type':'anotacoes','severity':'review','page':pn,'detail':'Página contém anotações; não incluídas no TXT.'})
            for widget in page.widgets() or ():
                inspection_parts.append(str(widget.field_value or ''))
                alerts.append({'type':'formularios','severity':'review','page':pn,'detail':'Página contém campo interativo; não incluído no TXT.'})
            inspection_parts.append(page.get_text())
            if sum(len(part) for part in inspection_parts) > 1_000_000:
                raise ValueError('Conteúdo textual excede 1 milhão de caracteres.')
            # Coordenadas da extração são desrotacionadas: renderizar igual.
            page.set_rotation(0)
            if page.rect.width * page.rect.height * (analysis_dpi / 72)**2 > 20_000_000:
                raise ValueError('Página excede o limite de 20 milhões de pixels.')
            pix = page.get_pixmap(dpi=analysis_dpi, colorspace=pymupdf.csRGB, alpha=False, annots=True)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width,3)
            scale = analysis_dpi / 72
            clean = text_free_image(scratch, pn - 1, analysis_dpi) if scratch is not None else None
            if clean is not None and clean.shape != image.shape: clean = None
            bboxlog = page.get_bboxlog()
            # Só objetos de preenchimento podem ocultar texto; índice por ordem de desenho.
            fills = [(i, b) for i, (t, b) in enumerate(bboxlog) if t in ('fill-image','fill-path','fill-shade')]
            fill_order = [i for i, _ in fills]
            # Interseção de retângulos sugere oclusão; não comprova invisibilidade.
            traces = page.get_texttrace()  # Falha deve ir para quarentena.
            blocked_boxes = []
            for tr in traces:
                # Texttrace também expõe caracteres não retornados pela extração comum.
                inspection_parts.append(''.join(chr(c[0]) for c in tr.get('chars',()) if 0 <= c[0] <= 0x10ffff))
                if tr.get('bbox') and overlap(tr['bbox'],tuple(page.rect)) < .98:
                    blocked_boxes.append(tr['bbox'])
                    alerts.append({'type':'fora_da_pagina','severity':'review','page':pn,'bbox':list(tr['bbox']),'detail':'Texto total ou parcialmente fora da área visível.'})
                if 'opacity' in enabled and (tr.get('opacity',1) < opacity_limit or tr.get('type',0) > 1):
                    blocked_boxes.append(tr['bbox'])
                    metrics['transparent'] += 1
                    alerts.append({'type':'texto_invisivel','severity':'review','page':pn,'detail':f"Opacidade {tr.get('opacity',1):.2f}; modo {tr.get('type',0)}",'bbox':list(tr['bbox'])})
                seq = tr.get('seqno',-1)
                box = tr.get('bbox')
                if 'overlap' in enabled and box and seq >= 0:
                    later = [b for _, b in fills[bisect.bisect_right(fill_order, seq):] if overlap(box, b) > 0]
                    if later and covered_fraction(box, later) > overlap_limit and not (clean is not None and legible_columns(image, clean, box, scale) >= .5):
                        blocked_boxes.append(box)
                        metrics['overlap'] += 1
                        alerts.append({'type':'possivel_sobreposicao','severity':'review','page':pn,'detail':'Objetos posteriores sobre região textual','bbox':list(box)})
            if sum(len(part) for part in inspection_parts) > 1_000_000:
                raise ValueError('Conteúdo textual excede 1 milhão de caracteres.')
            raw = page.get_text('rawdict', sort=True)
            page_lines = []
            for block in raw['blocks']:
                if block.get('type') != 0: continue
                for line in block.get('lines',[]):
                    fragments = []
                    for span in line.get('spans',[]):
                        chars = span.get('chars', [])
                        t = ''.join(c['c'] for c in chars)
                        if not t.strip():
                            fragments.append(t); continue
                        metrics['characters'] += len(t)
                        if overlap(span['bbox'], tuple(page.rect)) < .98:
                            alerts.append({'type':'fora_da_pagina','severity':'review','page':pn,'sample':t[:100],'bbox':list(span['bbox'])})
                            continue
                        if _BAD_UNICODE.search(t):
                            alerts.append({'type':'unicode_indeterminado','severity':'review','page':pn,'detail':'Caractere sem mapeamento Unicode confiável.'})
                        size_px = float(span['size']) * reference_dpi / 72
                        if any(overlap(span['bbox'], b) > .01 for b in blocked_boxes):
                            continue  # Conteúdo excluído permanece apenas no PDF original.
                        if 'size' in enabled and size_px < min_px:
                            metrics['small'] += len(t)
                            alerts.append({'type':'fonte_pequena','severity':'review','page':pn,'detail':f'{size_px:.1f}px @ {reference_dpi}DPI','sample':t[:100],'bbox':list(span['bbox'])})
                            continue
                        if 'contrast' in enabled:
                            fg = rgb(span['color'])
                            difference = ink_difference(image, clean, span['bbox'], scale) if clean is not None else None
                            strength = int(difference[0].max()) if difference is not None else None
                            if strength is not None and strength < INK_MIN:
                                metrics['low_contrast'] += len(t)
                                alerts.append({'type':'baixo_contraste','severity':'review','page':pn,'detail':'Sem tinta visível na renderização (cor igual ao fundo, modo de mesclagem, padrão ou cobertura)','sample':t[:100],'bbox':list(span['bbox'])})
                                continue
                            hidden = hidden_characters(difference, chars, scale)
                            if hidden:
                                gone = set(hidden); metrics['low_contrast'] += len(hidden)
                                alerts.append({'type':'baixo_contraste','severity':'review','page':pn,'detail':f'{len(hidden)} caractere(s) sem tinta visível (cobertos, mesclados ou da cor do fundo)','sample':''.join(chars[k]['c'] for k in hidden)[:100],'bbox':list(span['bbox'])})
                                t = ''.join(c['c'] for k, c in enumerate(chars) if k not in gone)
                                if not t.strip(): continue
                            # Plano B (renderização sem texto indisponível): anel único e, se for
                            # heterogêneo, janelas, o que acomoda gradientes suaves.
                            ratios = background_contrast(clean, span['bbox'], scale, fg) if clean is not None else None
                            if ratios is not None:
                                low = float((ratios < contrast_limit).mean())  # fração do fundo onde o texto não é legível
                                if low >= .5:
                                    metrics['low_contrast'] += len(t)
                                    alerts.append({'type':'baixo_contraste','severity':'review','page':pn,'detail':f'Contraste estimado {float(np.median(ratios)):.2f}:1','sample':t[:100],'bbox':list(span['bbox'])})
                                    continue
                                if low >= .2:
                                    alerts.append({'type':'fundo_indeterminado','severity':'review','page':pn,'sample':t[:100],'bbox':list(span['bbox'])})
                                    continue
                                fragments.append(t); continue
                            single = local_background(image, span['bbox'], scale)
                            backgrounds = [single] if single is not None else local_backgrounds(image, span['bbox'], scale)
                            known = [b for b in backgrounds if b is not None]
                            worst = min((contrast(fg,b) for b in known), default=None)
                            if worst is not None and worst < contrast_limit:
                                metrics['low_contrast'] += len(t)
                                alerts.append({'type':'baixo_contraste','severity':'review','page':pn,'detail':f'Contraste estimado {worst:.2f}:1','sample':t[:100],'bbox':list(span['bbox'])})
                                continue
                            if len(known) < len(backgrounds):
                                alerts.append({'type':'fundo_indeterminado','severity':'review','page':pn,'sample':t[:100],'bbox':list(span['bbox'])})
                                continue
                        fragments.append(t)
                    line_text = ''.join(fragments).strip()
                    if line_text: page_lines.append(line_text)
            texts.append('\n'.join(page_lines))
        text = '\n\n'.join(texts)
        if not text.strip():
            alerts.append({'type':'sem_texto','severity':'review','detail':'OCR ou análise humana necessária'})
        # Examinar também texto descartado e metadados; não entregá-los à IA.
        inspection = '\n'.join(inspection_parts)
        invisible = suspicious_format_characters(inspection)
        if invisible:
            alerts.append({'type':'controles_unicode','severity':'review','detail':'Caracteres invisíveis suspeitos: ' + ', '.join(invisible[:8]) + '. Usos comuns em línguas e emoji são ignorados.'})
        if 'commands' in enabled: alerts.extend(instruction_alerts(inspection))
        if doc.embfile_count() > 0:
            alerts.append({'type':'anexos_embutidos','severity':'review','detail':'PDF contém anexos embutidos'})
    # Reduz alertas repetidos por tipo/página, preservando um exemplo.
    unique = list({(a['type'],a.get('page')):a for a in reversed(alerts)}.values())
    unique.reverse()
    return scrub({'alerts':unique, 'text':text, 'metrics':metrics})

# Nomes de ação que executam algo ou enviam dados. No texto canônico do MuPDF os escapes de nome (#xx) já vêm
# resolvidos: `/Java#53cript` chega aqui como `/JavaScript`, então a ofuscação por escape não escapa da busca.
_ACTIVE_ACTIONS = re.compile(r'/(JavaScript|JS|Launch|SubmitForm|ImportData)(?![\w#.\-])')
_OBJECT_SCAN_CAP = 65_536     # caracteres lidos por objeto: um objeto gigante não trava a varredura
_STRINGS_BUDGET = 200_000     # total de caracteres de strings internas enviadas à busca de frases
_ESCAPE = re.compile(r'\\([0-7]{1,3}|.)', re.S)
_SIMPLE_ESCAPES = {'n': '\n', 'r': '\r', 't': '\t', 'b': '\b', 'f': '\f'}
_SEPARATORS = re.compile(r'[+_\-./=&?#:;,|~]+')
_LONG_NAME = re.compile(r'/([^\s/<>\[\]()%]{16,})')   # nomes longos (chaves de destinos antigos, etc.) também podem carregar frases


def _loosen(value):
    """Versão da string sem codificação de URL e sem separadores: `ignore+all_previous%20instructions` vira frase."""
    return _SEPARATORS.sub(' ', unquote(value))


def _unescape_pdf_string(text):
    """Decodifica escapes de uma string literal PDF e o prefixo de UTF-16/UTF-8 (BOM)."""
    def one(m):
        g = m.group(1)
        if g[0] in '01234567': return chr(int(g, 8) & 0xFF)
        return _SIMPLE_ESCAPES.get(g, '' if g in ('\n', '\r') else g)
    out = _ESCAPE.sub(one, text)
    if out[:2] == '\xfe\xff': return out[2:].encode('latin-1', 'replace').decode('utf-16-be', 'replace')
    if out[:2] == '\xff\xfe': return out[2:].encode('latin-1', 'replace').decode('utf-16-le', 'replace')
    if out[:3] == '\xef\xbb\xbf': return out[3:].encode('latin-1', 'replace').decode('utf-8', 'replace')
    return out


def _pdf_strings(obj):
    """Separa o texto canônico de um objeto PDF em (resto sem strings, strings literais decodificadas).

    Aceita parênteses aninhados e escapes, como a sintaxe PDF. O MuPDF já imprime strings hexadecimais como literais.
    """
    rest, found, i, n = [], [], 0, len(obj)
    while i < n:
        start = obj.find('(', i)
        if start < 0: rest.append(obj[i:]); break
        rest.append(obj[i:start]); rest.append(' ')
        depth, j = 1, start + 1
        while j < n and depth:
            ch = obj[j]
            if ch == '\\': j += 2; continue
            depth += (ch == '(') - (ch == ')'); j += 1
        found.append(_unescape_pdf_string(obj[start + 1:j - 1] if depth == 0 else obj[start + 1:j])); i = j
    return ''.join(rest), found


def structural_checks(doc, alerts):
    """Sinaliza ações ativas e camadas, e devolve as strings internas do PDF para a busca de frases.

    Percorre o texto canônico de cada objeto, não só as chaves de primeiro nível: um dicionário de ação embutido
    (`/OpenAction << /S /JavaScript ... >>`, a forma que o Acrobat grava) não tem objeto próprio e passava sem
    alerta. As strings (títulos de marcadores, URIs de links, chaves personalizadas, rótulos de página, nomes de
    destinos, textos alternativos...) são devolvidas para a mesma busca de frases já aplicada ao texto, em vez de
    enumerar canal por canal. Nada é executado. Não substitui um antivírus.
    """
    if doc.xref_length() > 30_000: raise ValueError('PDF excede 30 mil objetos.')
    strings, budget, seen = [], _STRINGS_BUDGET, set()
    for xref in (-1, *range(1, doc.xref_length())):   # -1 é o trailer, onde também cabem chaves personalizadas
        try: keys = doc.xref_get_keys(xref); obj = doc.xref_object(xref, compressed=False)
        except (RuntimeError, ValueError): continue  # Xref livre não é um objeto utilizável.
        rest, found = _pdf_strings(obj[:_OBJECT_SCAN_CAP])
        action = _ACTIVE_ACTIONS.search(rest)
        if action:
            alerts.append({'type':'acao_ativa','severity':'review','detail':f'Ação ativa em objeto {xref}: /{action.group(1)}.'})
        if 'OCProperties' in keys:
            alerts.append({'type':'camadas_opcionais','severity':'review','detail':'Camadas opcionais podem mudar a visibilidade.'})
        candidates = [v for v in found if len(v) >= 8]   # strings curtas não carregam instrução
        candidates += _LONG_NAME.findall(rest)
        for value in candidates:
            if budget <= 0: break
            if value in seen: continue
            seen.add(value); strings.append(value); budget -= len(value)
            loose = _loosen(value)
            if loose != value: strings.append(loose); budget -= len(loose)
    return strings


def _analyze_child(connection, path, options):
    """Entrada de subprocesso: envia resultado ou erro, sem iniciar Tkinter."""
    _limit_memory(CHILD_MEMORY_MB)
    try:
        if _SURROGATES.search(path):
            # Nome de arquivo com bytes inválidos em UTF-8 (ex.: Latin-1 em Linux): o PyMuPDF não abre esse
            # caminho, então a análise usa uma cópia com nome seguro. O resultado não contém o caminho.
            with tempfile.TemporaryDirectory() as folder:
                safe = Path(folder) / 'entrada.pdf'; shutil.copyfile(path, safe)
                connection.send(('ok', analyze_pdf(safe, **options)))
        else: connection.send(('ok', analyze_pdf(path, **options)))
    except MemoryError: connection.send(('error', f'Memória excedeu o limite de análise ({CHILD_MEMORY_MB} MB).'))
    except Exception as exc: connection.send(('error', str(exc) or type(exc).__name__))
    finally: connection.close()


def analyze_isolated(path, options, timeout=45):
    """Limita tempo de análise usando processo terminável; não é sandbox de SO."""
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_analyze_child,args=(sender,str(path),options),daemon=True)
    saved = {name: os.environ.get(name) for name in SINGLE_THREAD_VARS}
    for name in SINGLE_THREAD_VARS: os.environ.setdefault(name, '1')   # evita reservar memória virtual por thread numérica
    try:
        try: process.start()
        finally:
            for name, value in saved.items():
                if value is None: os.environ.pop(name, None)
                else: os.environ[name] = value
        sender.close()
        if not receiver.poll(timeout): raise TimeoutError(f'Análise excedeu {timeout}s.')
        try: status, payload = receiver.recv()
        except EOFError as exc: raise RuntimeError('Processo de análise encerrou sem resultado.') from exc
        if status != 'ok': raise RuntimeError(payload)
        return payload
    finally:
        if process.pid is not None:
            if process.is_alive(): process.terminate()
            process.join(timeout=3)
            if process.is_alive(): process.kill(); process.join()
        receiver.close(); sender.close()


class Pipeline:
    def __init__(self, root, extra=(), reject_files=False, reference_dpi=96, analysis_dpi=150, min_px=8, analysis_options=None, routes=None, reprocess=False, timeout=45):
        """Cria pastas e indexa hashes; nunca apaga ou altera o original."""
        self.root = Path(root).resolve()
        self.reject_files = reject_files
        self.reference_dpi, self.analysis_dpi, self.min_px = reference_dpi, analysis_dpi, min_px
        self.analysis_options = analysis_options or {}
        self.routes = routes or {}
        self.reprocess, self.timeout = reprocess, timeout
        for name in extra:
            if not valid_folder_name(name, FOLDERS): raise ValueError('Nome de pasta inválido: '+str(name))
        for name in FOLDERS + list(extra):
            folder = self.root / name
            if not folder.resolve().is_relative_to(self.root):
                raise ValueError('Pasta de saída aponta para fora do diretório: '+name)
            folder.mkdir(parents=True, exist_ok=True)
        self.hashes = {}
        for file in self.root.rglob('*.pdf'):
            # Só conta como "já visto" o PDF que tem relatório: sem ele (queda entre a cópia e a gravação) nunca foi avaliado.
            if not file.is_symlink() and file.parent.name in INDEXED and (self.root / 'relatorios' / (file.stem + '.json')).is_file():
                try: self.hashes[sha256_file(file)] = str(file)
                except OSError: pass

    def supersede_quarantine(self, report_id, digest):
        """Remove a cópia e o relatório de uma tentativa anterior em quarentena do MESMO conteúdo, já substituída.

        A quarentena é reanalisada a cada execução; sem isso cada tentativa empilharia mais uma cópia do PDF
        (possivelmente hostil) e mais um relatório. Só remove com SHA-256 igual, status "quarentena", sem histórico
        de decisão humana e com o PDF dentro da pasta de quarentena; qualquer dúvida mantém tudo.
        """
        report = self.root / 'relatorios' / f'{report_id}.json'
        try:
            data = json.loads(report.read_text(encoding='utf-8')); pdf = Path(data.get('file', '')).resolve()
        except (OSError, ValueError, TypeError): return False
        if data.get('status') != 'quarentena' or data.get('sha256') != digest or data.get('history'): return False
        if pdf.parent != (self.root / 'quarentena').resolve() or Path(report).name != f'{report_id}.json': return False
        pdf.unlink(missing_ok=True); report.unlink(missing_ok=True); report.with_suffix('.txt').unlink(missing_ok=True)
        return True

    def process(self, source):
        """Classifica um arquivo; qualquer falha de análise impede liberação."""
        source = Path(source)
        if source.is_symlink(): raise ValueError('Link simbólico recusado: ' + source.name)
        if source.stat().st_size > MAX_BYTES:
            return self._move(source,'quarentena',{'reason':'arquivo muito grande'})
        digest = sha256_file(source)
        if digest in self.hashes and not self.reprocess:
            return self._move(source,'duplicados',{'reason':'hash duplicado','duplicate_of':self.hashes[digest]})
        try:
            if not has_pdf_header(source):
                return self._move(source,'quarentena',{'reason':'assinatura inválida'})
            result = analyze_isolated(source, dict(reference_dpi=self.reference_dpi,analysis_dpi=self.analysis_dpi,min_px=self.min_px,**self.analysis_options), self.timeout)
            # Bloqueio documental impede ingestão automática.
            # A decisão de contratação pertence à avaliação humana.
            actions = [self.routes.get(a['type'], 'verificacao_humana') for a in result['alerts']]
            folder = ('rejeitados' if self.reject_files and 'rejeitados' in actions else 'verificacao_humana') if actions else 'aprovados'
            result['configuration'] = {'reference_dpi': self.reference_dpi, 'analysis_dpi': self.analysis_dpi, 'min_px': self.min_px, 'checks': self.analysis_options, 'routes': self.routes, 'automatic_block': self.reject_files}
            # Segunda camada: um resultado que não vira JSON/UTF-8 vai para a quarentena em vez de derrubar o arquivo.
            try: json.dumps(result, ensure_ascii=False, allow_nan=False).encode('utf-8')
            except (ValueError, TypeError) as exc: raise ValueError('Resultado da análise não pôde ser gravado: ' + str(exc)) from exc
        except Exception as exc:
            folder = 'quarentena'
            result = {'error':scrub(str(exc)),'alerts':[{'type':'erro_processamento','severity':'review'}]}
        result['sha256'] = digest
        return self._move(source,folder,result)

    def _move(self, source, folder, report):
        """Cria cópia e relatório únicos para cada processamento; revisões têm histórico."""
        source = Path(source)
        digest = sha256_file(source)
        if report.get('sha256') and report['sha256'] != digest:
            raise ValueError('Arquivo mudou durante a análise; resultado não publicado.')
        identifier = uuid.uuid4().hex
        # ID único: duplicatas/reanálises não sobrescrevem relatórios anteriores.
        target = self.root / folder / f'{_SURROGATES.sub("_", source.stem[:45])}_{identifier}.pdf'   # sem substitutos no nome nem no relatório
        shutil.copy2(source,target)
        if sha256_file(target) != digest:
            target.unlink(missing_ok=True)
            raise ValueError('Arquivo mudou durante a cópia; tente novamente.')
        stamp = datetime.now(timezone.utc).isoformat()
        report.update({'id':identifier,'sha256':digest,'file':str(target),'original_name':source.name,
                       'status':folder,'processed_at':stamp,'history':[],'app_version':APP_VERSION})
        report = scrub(report)
        report_path = self.root / 'relatorios' / (target.stem+'.json')
        try: write_report(report_path,report)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if 'text' in report and folder == 'aprovados':
            atomic_write(report_path.with_suffix('.txt'),report['text'])
        if folder in INDEXED: self.hashes.setdefault(digest, str(target))
        return folder, target


def manifest_urls(url, cancel=None):
    """Aceita PDF direto ou JSON explícito; não raspa diretórios arbitrários.

    A leitura do manifesto tem prazo total e responde ao cancelamento, como o download de PDFs: um servidor
    que "goteja" bytes não pode segurar o lote (nem o botão Interromper) indefinidamente.
    """
    if not urlparse(url).path.lower().endswith('.json'): return [url]
    is_public_https(url)
    content = bytearray()
    with strict_egress(), requests.Session() as session:
        session.trust_env = False  # mesma política do download: sem proxies de ambiente
        with session.get(url, stream=True, timeout=(8, 25), allow_redirects=False,
                         headers={'User-Agent':f'CurriculoGuard/{APP_VERSION}'}) as response:
            if 300 <= response.status_code < 400: raise ValueError('Redirecionamento bloqueado.')
            response.raise_for_status()
            _copy_body(response, content.extend, 65536, 'Manifesto excede 64 KB.', time.monotonic() + MANIFEST_DEADLINE_S,
                       f'Leitura do manifesto excedeu {MANIFEST_DEADLINE_S} segundos.', cancel)
    links = json.loads(content)
    if not isinstance(links, list) or not 1 <= len(links) <= 100 or any(not isinstance(v, str) for v in links):
        raise ValueError('Manifesto deve ser lista JSON com 1 a 100 URLs.')
    for link in links: is_public_https(link)
    return links


# Limites aceitos para os parâmetros editáveis (os mesmos exibidos na interface).
SETTING_LIMITS = (('reference_dpi','DPI referência',36,600),('analysis_dpi','DPI renderização',72,300),
                  ('min_px','Fonte mínima em px',1,30),('timeout','Tempo máximo por análise',5,180))
OPTION_LIMITS = (('contrast_limit','Contraste mínimo',1,21),('opacity_limit','Opacidade mínima',0,1),
                 ('overlap_limit','Cobertura suspeita',0,1),('max_pages','Máximo de páginas',1,100))

def validate_params(params):
    """Valida os parâmetros de um lote (os mesmos que `Pipeline` recebe); levanta ValueError."""
    if not str(params.get('root', '')).strip(): raise ValueError('Informe a pasta de saída.')
    def check(source, limits):
        for key, label, low, high in limits:
            if key not in source: continue
            value = source[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not low <= value <= high:
                raise ValueError(f'{label} fora do intervalo permitido ({low}–{high}).')
    check(params, SETTING_LIMITS)
    check(params.get('analysis_options') or {}, OPTION_LIMITS)
    for name in params.get('extra', ()):
        if not valid_folder_name(name, FOLDERS): raise ValueError('Pasta extra inválida: ' + str(name))


def run_batch(params, url='', local='', recursive=False, cancel=None, report=None):
    """Executa um lote completo: coleta PDFs locais, baixa URLs e classifica cada arquivo.

    `params` são os argumentos de `Pipeline`. `cancel` é um objeto com `is_set()` (ex.:
    threading.Event). `report(tipo, valor)` recebe 'log', 'total' e 'progress'. Erros
    individuais não abortam o lote. Devolve um Counter com o destino de cada arquivo.

    O lote é incremental: um arquivo (ou URL) já analisado, sem alteração e com o relatório ainda existente é
    ignorado (contado em 'ja_processados'), a menos que `reprocess` esteja ligado. Uma trava impede dois lotes
    simultâneos na mesma pasta de saída.
    """
    notify = report or (lambda kind, value: None)
    report = lambda kind, value: notify(kind, scrub(value) if kind == 'log' else value)
    cancel = cancel or threading.Event()
    validate_params(params)
    pipe = Pipeline(**params)
    lock = FileLock(pipe.root / '.lote.lock', timeout=0, stale=300, busy_message=(
        'Já existe um lote em andamento nesta pasta de saída (outra janela ou outro computador). Aguarde o término. '
        'Se nenhum lote estiver rodando (queda anterior), aguarde 5 minutos ou apague o arquivo .lote.lock da pasta de saída.'))
    lock.acquire()
    try: return _run_batch_locked(pipe, lock, url, local, recursive, cancel, report)
    finally: lock.release()


def _run_batch_locked(pipe, lock, url, local, recursive, cancel, report):
    sources = []; destinations = Counter(); registry = SourceRegistry(pipe.root)   # sources: (arquivo, origem, baixado)
    if local:
        folder = Path(local).resolve()
        if not folder.is_dir(): raise ValueError('Pasta de origem inválida.')
        candidates = [p for p in (folder.rglob('*') if recursive else folder.iterdir()) if p.suffix.lower() == '.pdf' and p.is_file()]
        for p in candidates:
            if p.is_symlink() or not p.resolve().is_relative_to(folder): report('log', f'{p.name}: ignorado (link simbólico ou fora da pasta de origem)')
        sources.extend((p, str(p.resolve()), False) for p in candidates if not p.is_symlink() and p.resolve().is_relative_to(folder) and pipe.root not in p.resolve().parents)
    for link in (manifest_urls(url, cancel) if url else []):
        if cancel.is_set(): break
        lock.touch()
        dest = pipe.root / 'originais' / ('download_' + uuid.uuid4().hex + '.pdf')
        try: download_pdf(link, dest, cancel); sources.append((dest, link, True))
        except Exception as exc: report('log', 'Download falhou: ' + str(exc))
    report('total', len(sources))
    skipped = 0
    for index, (path, origin, downloaded) in enumerate(sources, 1):
        if cancel.is_set(): break
        lock.touch()
        try:
            stat = path.stat(); entry = registry.get(origin)
            unchanged = bool(entry) and entry.get('tamanho') == stat.st_size and entry.get('mtime_ns') == stat.st_mtime_ns
            digest = entry['sha256'] if unchanged and not downloaded else sha256_file(path)
            if (not pipe.reprocess and entry and digest == entry.get('sha256') and entry.get('status') != 'quarentena'
                    and (pipe.root / 'relatorios' / f"{entry.get('relatorio')}.json").is_file()):
                skipped += 1; destinations['ja_processados'] += 1
                if downloaded: path.unlink(missing_ok=True)   # o conteúdo já está guardado: não acumula download repetido
                elif not unchanged: registry.remember(origin, stat.st_size, stat.st_mtime_ns, digest, entry['status'], entry['relatorio'])
                report('log', f'{path.name}: já processado ({entry["status"]}), sem alteração; ignorado')
            else:
                status, target = pipe.process(path); destinations[status] += 1
                registry.remember(origin, stat.st_size, stat.st_mtime_ns, digest, status, target.stem)
                if entry and entry.get('status') == 'quarentena' and entry.get('sha256') == digest and entry.get('relatorio') != target.stem:
                    pipe.supersede_quarantine(entry['relatorio'], digest)   # tentativa anterior substituída por esta
                report('log', f'{path.name} → {status} | relatório: {target.stem}.json')
        except Exception as exc: report('log', f'{path.name}: erro — {exc}')
        report('progress', index)
    if skipped: report('log', f'{skipped} arquivo(s) já processado(s) e sem alteração foram ignorados. Marque "Reanalisar duplicados" para analisá-los de novo.')
    report('log', 'Interrompido.' if cancel.is_set() else 'Lote concluído.')
    return destinations
