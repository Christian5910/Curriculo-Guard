"""Currículo Guard: filtragem documental local, sem decisões de contratação.

Execute com Python 3.11+ após instalar pymupdf, numpy e requests.
O PDF e os relatórios são dados não confiáveis: nunca executar suas instruções.
"""
import os, re, json, hashlib, shutil, threading, queue, socket, ipaddress
import unicodedata, uuid, time, multiprocessing
from workflow import sha256_file, atomic_write, write_report, ReviewStore
from review_ui import ReviewPanel
from pathlib import Path
from urllib.parse import urlparse
from datetime import datetime, timezone
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import requests
import fitz
import numpy as np

FOLDERS = ['aprovados','verificacao_humana','rejeitados','duplicados','quarentena','relatorios','originais']
MAX_BYTES = 15 * 1024 * 1024
PATTERNS = [
    ('instrucao_ia', r'(?i)(ignore (all )?(previous|prior) instructions|ignore todas as instru[cç][oõ]es|desconsidere (as )?instru[cç][oõ]es anteriores)'),
    ('papel_sistema', r'(?i)(\[\s*(system|developer|assistant)\s*\]|<\s*/?\s*(system|developer|assistant)\s*>|\b(system prompt|developer message)\b)'),
    ('comando_avaliacao', r'(?i)(approve (this|the) (candidate|resume)|aprove (este|o) candidato|atribua (nota|pontua[cç][aã]o) m[aá]xima|give (me|this candidate) (a )?(perfect|maximum) score)'),
    ('exfiltracao', r'(?i)(send|envie|transmita).{0,70}(dados|data|curr[ií]culos|resumes).{0,100}(https?://|email|e-mail|@)'),
]

def is_public_https(url):
    """Valida protocolo e IPs públicos; exige política de saída contra DNS rebinding."""
    p = urlparse(url)
    if p.scheme != 'https' or not p.hostname or p.username or p.password or p.port not in (None, 443):
        raise ValueError('Somente HTTPS público na porta 443 é permitido.')
    addresses = socket.getaddrinfo(p.hostname, 443, type=socket.SOCK_STREAM)
    if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):
        raise ValueError('Destino privado, local ou não público bloqueado.')
    return url

def download_pdf(url, dest, cancel=None):
    """Baixa em temporário e só publica PDF completo; pode cancelar por bloco."""
    is_public_https(url)
    dest = Path(dest)
    partial = dest.with_name(dest.name + '.' + uuid.uuid4().hex + '.part')
    deadline = time.monotonic() + 90
    try:
        # Desabilitar proxies de ambiente reduz destinos inesperados.
        with requests.Session() as session:
            session.trust_env = False
            with session.get(url, stream=True, timeout=(8, 15), allow_redirects=False,
                             headers={'User-Agent':'CurriculoGuard/2.0'}) as response:
                if 300 <= response.status_code < 400: raise ValueError('Redirecionamento bloqueado.')
                response.raise_for_status()
                total = 0
                with partial.open('wb') as stream:
                    for chunk in response.iter_content(65536):
                        if cancel is not None and cancel.is_set(): raise ValueError('Download cancelado.')
                        if time.monotonic() > deadline: raise TimeoutError('Download excedeu 90 segundos.')
                        total += len(chunk)
                        if total > MAX_BYTES: raise ValueError('PDF excede 15 MB.')
                        stream.write(chunk)
        with partial.open('rb') as stream:
            if stream.read(5) != b'%PDF-': raise ValueError('Arquivo não tem assinatura PDF.')
        os.replace(partial, dest)
    finally:
        partial.unlink(missing_ok=True)


def normalized_instruction_text(text):
    """NFKC, remoção de controles invisíveis e espaços uniformes para heurísticas."""
    text = unicodedata.normalize('NFKC', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return re.sub(r'\s+', ' ', text)


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
    samples = patch[mask]
    if len(samples) < 10: return None
    # Um anel heterogêneo não fornece evidência confiável de fundo local.
    median = np.median(samples, axis=0)
    if np.percentile(np.max(np.abs(samples - median), axis=1), 90) > 35:
        return None
    return median

def overlap(a, b):
    """Retorna fração da área de A coberta pelo retângulo B."""
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    area = max(0,x1-x0) * max(0,y1-y0)
    base = max(.00001, (a[2]-a[0]) * (a[3]-a[1]))
    return area / base

def analyze_pdf(path, reference_dpi=96, analysis_dpi=150, min_px=8,
                contrast_limit=1.2, opacity_limit=.95, overlap_limit=.75,
                enabled=None, max_pages=35):
    """Extrai texto elegível e evidências; contraste/oclusão são estimativas.

    PDF mede fontes em pontos. DPI referência define o limite de leitura;
    DPI análise define somente a resolução da imagem usada para contraste.
    """
    enabled = set(enabled) if enabled is not None else {'size','contrast','opacity','overlap','commands'}
    alerts, texts, metrics = [], [], {'pages':0, 'characters':0, 'small':0, 'low_contrast':0, 'transparent':0, 'overlap':0}
    with fitz.open(path) as doc:
        if doc.needs_pass:
            return {'alerts':[{'type':'senha', 'severity':'review', 'detail':'PDF protegido por senha'}], 'text':'', 'metrics':metrics}
        if doc.page_count > max_pages:
            return {'alerts':[{'type':'paginas_excessivas','severity':'review','detail':f'{doc.page_count} páginas; análise interrompida'}], 'text':'', 'metrics':metrics}
        metrics['pages'] = doc.page_count
        inspection_parts = [str(v) for v in doc.metadata.values() if v] + [doc.get_xml_metadata()]
        structural_checks(doc, alerts)
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
            pix = page.get_pixmap(dpi=analysis_dpi, colorspace=fitz.csRGB, alpha=False, annots=True)
            image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height,pix.width,3)
            scale = analysis_dpi / 72
            bboxlog = page.get_bboxlog()
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
                    for later_type, later_box in bboxlog[seq+1:]:
                        if later_type in ('fill-image','fill-path','fill-shade') and overlap(box,later_box) > overlap_limit:
                            blocked_boxes.append(box)
                            metrics['overlap'] += 1
                            alerts.append({'type':'possivel_sobreposicao','severity':'review','page':pn,'detail':'Objeto posterior sobre região textual','bbox':list(box)})
                            break
            if sum(len(part) for part in inspection_parts) > 1_000_000:
                raise ValueError('Conteúdo textual excede 1 milhão de caracteres.')
            raw = page.get_text('dict', sort=True)
            page_lines = []
            for block in raw['blocks']:
                if block.get('type') != 0: continue
                for line in block.get('lines',[]):
                    fragments = []
                    for span in line.get('spans',[]):
                        t = span.get('text','')
                        if not t.strip():
                            fragments.append(t); continue
                        metrics['characters'] += len(t)
                        if overlap(span['bbox'], tuple(page.rect)) < .98:
                            alerts.append({'type':'fora_da_pagina','severity':'review','page':pn,'sample':t[:100],'bbox':list(span['bbox'])})
                            continue
                        if '\ufffd' in t:
                            alerts.append({'type':'unicode_indeterminado','severity':'review','page':pn,'detail':'Caractere sem mapeamento Unicode confiável.'})
                        size_px = float(span['size']) * reference_dpi / 72
                        if any(overlap(span['bbox'], b) > .01 for b in blocked_boxes):
                            continue  # Conteúdo excluído permanece apenas no PDF original.
                        if 'size' in enabled and size_px < min_px:
                            metrics['small'] += len(t)
                            alerts.append({'type':'fonte_pequena','severity':'review','page':pn,'detail':f'{size_px:.1f}px @ {reference_dpi}DPI','sample':t[:100],'bbox':list(span['bbox'])})
                            continue
                        bg = local_background(image, span['bbox'], scale)
                        fg = rgb(span['color'])
                        if 'contrast' in enabled and bg is None:
                            alerts.append({'type':'fundo_indeterminado','severity':'review','page':pn,'sample':t[:100],'bbox':list(span['bbox'])})
                            continue
                        elif 'contrast' in enabled and contrast(fg,bg) < contrast_limit:
                            metrics['low_contrast'] += len(t)
                            alerts.append({'type':'baixo_contraste','severity':'review','page':pn,'detail':f'Contraste estimado {contrast(fg,bg):.2f}:1','sample':t[:100],'bbox':list(span['bbox'])})
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
        if any(unicodedata.category(c) == 'Cf' for c in inspection):
            alerts.append({'type':'controles_unicode','severity':'review','detail':'Controles invisíveis/direcionais encontrados; podem ser legítimos.'})
        inspection = normalized_instruction_text(inspection)
        for name, pattern in PATTERNS if 'commands' in enabled else []:
            for m in list(re.finditer(pattern,inspection))[:8]:
                alerts.append({'type':name,'severity':'review','detail':'Possível instrução dirigida ao avaliador automatizado','sample':inspection[max(0,m.start()-40):m.end()+40]})
        if doc.embfile_count() > 0:
            alerts.append({'type':'anexos_embutidos','severity':'review','detail':'PDF contém anexos embutidos'})
    # Reduz alertas repetidos por tipo/página, preservando um exemplo.
    unique = list({(a['type'],a.get('page')):a for a in reversed(alerts)}.values())
    unique.reverse()
    return {'alerts':unique, 'text':text, 'metrics':metrics}

def structural_checks(doc, alerts):
    """Sinaliza ações/layers sem executar JS, Launch ou anexos do documento.

    Inspeção de chaves e valores estruturais é conservadora. Objetos órfãos
    também podem produzir alertas: este mecanismo não é um antivírus.
    """
    if doc.xref_length() > 30_000: raise ValueError('PDF excede 30 mil objetos.')
    for xref in range(1, doc.xref_length()):
        
        try: keys = doc.xref_get_keys(xref)
        except RuntimeError: continue  # Xref livre não é um objeto utilizável.
        action = doc.xref_get_key(xref, 'S')[1] if 'S' in keys else ''
        if 'JS' in keys or action in ('/JavaScript','/Launch','/SubmitForm','/ImportData'):
            alerts.append({'type':'acao_ativa','severity':'review','detail':f'Ação ativa em objeto {xref}: {action or "JS"}.'})
        if 'OCProperties' in keys:
            alerts.append({'type':'camadas_opcionais','severity':'review','detail':'Camadas opcionais podem mudar a visibilidade.'})


def _analyze_child(connection, path, options):
    """Entrada de subprocesso: envia resultado ou erro, sem iniciar Tkinter."""
    try: connection.send(('ok', analyze_pdf(path, **options)))
    except Exception as exc: connection.send(('error', str(exc)))
    finally: connection.close()


def analyze_isolated(path, options, timeout=45):
    """Limita tempo de análise usando processo terminável; não é sandbox de SO."""
    context = multiprocessing.get_context('spawn')
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_analyze_child,args=(sender,str(path),options),daemon=True)
    try:
        process.start(); sender.close()
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
        for name in FOLDERS + list(extra):
            if not re.fullmatch(r'[\w -]{1,40}', name) or name in ('.','..'):
                raise ValueError('Nome de pasta inválido: '+name)
            folder = self.root / name
            if not folder.resolve().is_relative_to(self.root):
                raise ValueError('Pasta de saída aponta para fora do diretório: '+name)
            folder.mkdir(parents=True, exist_ok=True)
        self.hashes = {}
        for file in self.root.rglob('*.pdf'):
            if not file.is_symlink() and file.parent.name in FOLDERS and file.parent.name != 'originais':
                try: self.hashes[sha256_file(file)] = str(file)
                except OSError: pass

    def process(self, source):
        """Classifica um arquivo; qualquer falha de análise impede liberação."""
        source = Path(source)
        if source.stat().st_size > MAX_BYTES:
            return self._move(source,'quarentena',{'reason':'arquivo muito grande'})
        digest = sha256_file(source)
        if digest in self.hashes and not self.reprocess:
            return self._move(source,'duplicados',{'reason':'hash duplicado','duplicate_of':self.hashes[digest]})
        try:
            if source.read_bytes()[:5] != b'%PDF-':
                return self._move(source,'quarentena',{'reason':'assinatura inválida'})
            result = analyze_isolated(source, dict(reference_dpi=self.reference_dpi,analysis_dpi=self.analysis_dpi,min_px=self.min_px,**self.analysis_options), self.timeout)
            # Bloqueio documental impede ingestão automática.
            # A decisão de contratação pertence à avaliação humana.
            actions = [self.routes.get(a['type'], 'verificacao_humana') for a in result['alerts']]
            folder = ('rejeitados' if self.reject_files and 'rejeitados' in actions else 'verificacao_humana') if actions else 'aprovados'
            result['configuration'] = {'reference_dpi': self.reference_dpi, 'analysis_dpi': self.analysis_dpi, 'min_px': self.min_px, 'checks': self.analysis_options, 'routes': self.routes, 'automatic_block': self.reject_files}
        except Exception as exc:
            folder = 'quarentena'
            result = {'error':str(exc),'alerts':[{'type':'erro_processamento','severity':'review'}]}
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
        target = self.root / folder / f'{source.stem[:45]}_{identifier}.pdf'
        shutil.copy2(source,target)
        if sha256_file(target) != digest:
            target.unlink(missing_ok=True)
            raise ValueError('Arquivo mudou durante a cópia; tente novamente.')
        stamp = datetime.now(timezone.utc).isoformat()
        report.update({'id':identifier,'sha256':digest,'file':str(target),'original_name':source.name,
                       'status':folder,'processed_at':stamp,'history':[],'app_version':'2.0'})
        report_path = self.root / 'relatorios' / (target.stem+'.json')
        try: write_report(report_path,report)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        if 'text' in report and folder == 'aprovados':
            atomic_write(report_path.with_suffix('.txt'),report['text'])
        self.hashes.setdefault(digest, str(target))
        return folder, target

class App:
    """Interface por abas; somente a thread principal acessa o Tkinter."""

    def __init__(self, master):
        self.master = master
        master.title('Currículo Guard')
        master.geometry('850x740')
        master.minsize(800, 680)
        self.q = queue.Queue()
        self.cancel = threading.Event()
        self.url = tk.StringVar()
        self.local = tk.StringVar()
        self.out = tk.StringVar(value=str(Path.cwd() / 'triagem'))
        self.extra = tk.StringVar()
        self.reject = tk.BooleanVar(value=False)
        self.refdpi = tk.IntVar(value=96)
        self.dpi = tk.IntVar(value=150)
        self.minpx = tk.DoubleVar(value=8)
        self.contrast = tk.DoubleVar(value=1.2)
        self.opacity = tk.DoubleVar(value=.95)
        self.cover = tk.DoubleVar(value=.75)
        self.recursive = tk.BooleanVar(value=False)
        self.reprocess = tk.BooleanVar(value=False)
        self.timeout = tk.IntVar(value=45)
        self.maxpages = tk.IntVar(value=35)
        self.running = False
        self.checks = {k: tk.BooleanVar(value=True) for k in ('size','contrast','opacity','overlap','commands')}
        self.routes = {}
        base = ttk.Frame(master, padding=12)
        base.pack(fill='both', expand=True)
        ttk.Label(base, text='Currículo Guard', font=('Arial', 18, 'bold')).pack(anchor='w')
        ttk.Label(base, text='Triagem técnica de PDFs. Aprovação documental não é aprovação de contratação.').pack(anchor='w', pady=5)
        tabs = ttk.Notebook(base)
        tabs.pack(fill='both', expand=True)
        entry, rules, folders, help_tab = [ttk.Frame(tabs, padding=12) for _ in range(4)]
        for tab, title in zip((entry,rules,folders,help_tab), ('Entrada','Verificações','Destinos','Como funciona')):
            tabs.add(tab, text=title)
        self.review = ReviewPanel(tabs,self.out,lambda:self.running)
        tabs.insert(3,self.review,text='Revisão humana')
        self.field(entry, 'URL HTTPS direta de PDF (opcional)', self.url)
        ttk.Label(entry, text='Para vários downloads, use um manifesto JSON HTTPS: lista de URLs de PDFs.').pack(anchor='w')
        self.field(entry, 'Pasta local de PDFs (opcional)', self.local, browse=True)
        ttk.Checkbutton(entry, text='Incluir subpastas (exclui o diretório de saída)', variable=self.recursive).pack(anchor='w')
        self.field(entry, 'Diretório de saída', self.out, browse=True)
        ttk.Checkbutton(entry,text='Reanalisar duplicados (nova avaliação independente)',variable=self.reprocess).pack(anchor='w')
        self.field(entry,'Tempo máximo por análise em segundos (5–180)',self.timeout,compact=True)
        self.field(entry,'Máximo de páginas (1–100)',self.maxpages,compact=True)
        ttk.Label(entry, text='Originais preservados. Nenhum arquivo é apagado. Downloads não seguem redirecionamentos.').pack(anchor='w', pady=10)
        for key, label in [('size','Filtrar fonte pequena'),('contrast','Estimar contraste com fundo local'),('opacity','Filtrar texto invisível ou semitransparente'),('overlap','Sinalizar possível objeto sobreposto'),('commands','Procurar padrões de instruções para IA')]:
            ttk.Checkbutton(rules, text=label, variable=self.checks[key]).pack(anchor='w')
        for label, var in [('DPI referência (36–600)',self.refdpi),('DPI renderização (72–300)',self.dpi),('Fonte mínima em px (1–30)',self.minpx),('Contraste mínimo (1–21)',self.contrast),('Opacidade mínima (0–1)',self.opacity),('Cobertura suspeita (0–1)',self.cover)]:
            self.field(rules,label,var, compact=True)
        ttk.Label(rules, text='px = pontos × DPI referência ÷ 72. DPI renderização não muda o limite.\nDesativar verificações reduz a proteção. Contraste e sobreposição são heurísticas.', wraplength=760).pack(anchor='w', pady=8)
        self.field(folders,'Pastas extras (separadas por vírgula; organização manual)',self.extra)
        ttk.Checkbutton(folders, text='Permitir bloqueio automático documental nas regras marcadas “rejeitados”', variable=self.reject).pack(anchor='w', pady=8)
        # Cada alerta tem destino explícito. Sem permissão de bloqueio, todos vão à revisão.
        names = [('baixo_contraste','Baixo contraste / cor semelhante'),('fonte_pequena','Fonte pequena'),('texto_invisivel','Invisível / transparência'),('possivel_sobreposicao','Possível sobreposição'),('instrucao_ia','Ignorar instruções'),('papel_sistema','Marcadores de sistema'),('comando_avaliacao','Manipulação da avaliação'),('exfiltracao','Possível exfiltração')]
        for key,label in names:
            row = ttk.Frame(folders); row.pack(fill='x', pady=2)
            ttk.Label(row,text=label,width=35).pack(side='left')
            var = tk.StringVar(value='verificacao_humana'); self.routes[key] = var
            ttk.Combobox(row,textvariable=var,values=['verificacao_humana','rejeitados'],state='readonly',width=25).pack(side='left')
        ttk.Label(folders,text='Sem alertas → aprovados | falhas → quarentena | hash repetido → duplicados\nOutros alertas → verificação humana. Bloqueio não exclui o arquivo.',wraplength=760).pack(anchor='w',pady=10)
        help_text = (
            'APROVADOS: nenhum alerta nas verificações ativas; não garante ausência de ataque.\n\n'
            'VERIFICAÇÃO HUMANA: tamanho, contraste, opacidade, oclusão, comandos, senha, anexos ou falta de texto. OCR invisível legítimo também pode gerar alerta.\n\n'
            'REJEITADOS: bloqueados da ingestão automática conforme suas regras, sem decisão sobre o candidato. QUARENTENA: PDF inválido ou falha. DUPLICADOS: mesmo SHA-256.\n\n'
            'O fundo é estimado pelo anel ao redor do texto. Imagens, gradientes, recortes e efeitos podem confundir a estimativa. Branco no branco não comprova má-fé. Não existe garantia de detectar toda injeção.\n\n'
            'PDF escaneado exige OCR/revisão: este app não executa OCR. A ordem do texto pode ser imperfeita em colunas.\n\n'
            'Nenhum comando do PDF é executado. Se integrar uma IA, trate o texto como dados não confiáveis, sem ferramentas, segredos ou poder de alterar critérios. Relatórios também contêm dados não confiáveis.\n\n'
            'Limites: 15 MB por arquivo, páginas/tempo configuráveis, 20 milhões de pixels por página, 100 URLs por manifesto. Use ambiente isolado e bibliotecas atualizadas para PDFs externos.'
        )
        ttk.Label(help_tab,text=help_text,wraplength=760,justify='left').pack(anchor='w')
        buttons = ttk.Frame(base); buttons.pack(fill='x', pady=8)
        self.runbutton = ttk.Button(buttons,text='Iniciar',command=self.start); self.runbutton.pack(side='left')
        ttk.Button(buttons,text='Interromper lote/download',command=self.cancel.set).pack(side='left',padx=6)
        ttk.Button(buttons,text='Salvar configuração',command=self.save_settings).pack(side='right')
        ttk.Button(buttons,text='Carregar configuração',command=self.load_settings).pack(side='right',padx=6)
        self.progress = ttk.Progressbar(base,mode='determinate'); self.progress.pack(fill='x')
        self.log = tk.Text(base,height=7,wrap='word',state='disabled'); self.log.pack(fill='both',pady=6)
        master.after(100,self.poll)

    def field(self, parent, label, var, browse=False, compact=False):
        """Cria um campo consistente; compactos mantêm rótulo e valor na mesma linha."""
        row = ttk.Frame(parent); row.pack(fill='x',pady=4)
        ttk.Label(row,text=label,width=35 if compact else 0).pack(side='left' if compact else 'top',anchor='w')
        ttk.Entry(row,textvariable=var,width=12 if compact else 65).pack(side='left',fill=None if compact else 'x',expand=not compact)
        if browse:
            ttk.Button(row,text='Escolher',command=lambda:var.set(filedialog.askdirectory() or var.get())).pack(side='left',padx=5)

    def settings(self):
        """Captura valores antes de iniciar a thread; valida limites e nomes."""
        data = dict(reprocess=self.reprocess.get(),timeout=self.timeout.get(),root=self.out.get().strip(),extra=[s.strip() for s in self.extra.get().split(',') if s.strip()],reject_files=self.reject.get(),reference_dpi=self.refdpi.get(),analysis_dpi=self.dpi.get(),min_px=self.minpx.get(),analysis_options=dict(max_pages=self.maxpages.get(),contrast_limit=self.contrast.get(),opacity_limit=self.opacity.get(),overlap_limit=self.cover.get(),enabled=[k for k,v in self.checks.items() if v.get()]),routes={k:v.get() for k,v in self.routes.items()})
        if not data['root']: raise ValueError('Informe a pasta de saída.')
        for value,lo,hi in [(data['reference_dpi'],36,600),(data['analysis_dpi'],72,300),(data['min_px'],1,30),(self.contrast.get(),1,21),(self.opacity.get(),0,1),(self.cover.get(),0,1),(self.timeout.get(),5,180),(self.maxpages.get(),1,100)]:
            if not lo <= value <= hi: raise ValueError('Valor fora do intervalo exibido.')
        for name in data['extra']:
            if not re.fullmatch(r'[\w -]{1,40}',name): raise ValueError('Pasta extra inválida: '+name)
        return data

    def save_settings(self):
        """Grava configuração editável; não salva dados de candidatos."""
        try:
            data=self.settings(); data.update(url=self.url.get(),local=self.local.get(),recursive=self.recursive.get())
            path=filedialog.asksaveasfilename(defaultextension='.json',filetypes=[('JSON','*.json')])
            if path: Path(path).write_text(json.dumps(data,indent=2,ensure_ascii=False),encoding='utf-8')
        except Exception as exc: messagebox.showerror('Configuração',str(exc))

    def load_settings(self):
        """Carrega apenas campos conhecidos; a validação completa ocorre em Iniciar."""
        path=filedialog.askopenfilename(filetypes=[('JSON','*.json')])
        if not path: return
        try:
            data=json.loads(Path(path).read_text(encoding='utf-8'))
            for key,var in [('root',self.out),('url',self.url),('local',self.local),('reference_dpi',self.refdpi),('analysis_dpi',self.dpi),('min_px',self.minpx),('reject_files',self.reject),('recursive',self.recursive),('reprocess',self.reprocess),('timeout',self.timeout)]:
                if key in data: var.set(data[key])
            self.extra.set(', '.join(data.get('extra',[])))
            opts=data.get('analysis_options',{})
            for key,var in [('contrast_limit',self.contrast),('opacity_limit',self.opacity),('overlap_limit',self.cover),('max_pages',self.maxpages)]:
                if key in opts: var.set(opts[key])
            for key,var in self.checks.items(): var.set(key in opts.get('enabled',list(self.checks)))
            for key,var in self.routes.items(): var.set('rejeitados' if data.get('routes',{}).get(key)=='rejeitados' else 'verificacao_humana')
        except Exception as exc: messagebox.showerror('Configuração inválida',str(exc))

    def start(self):
        """Valida na thread da interface e inicia trabalho sem congelar a janela."""
        try:
            params=self.settings()
            if not self.url.get().strip() and not self.local.get().strip(): raise ValueError('Informe URL ou pasta local.')
        except Exception as exc: messagebox.showerror('Entrada inválida',str(exc)); return
        self.cancel.clear(); self.running=True; self.runbutton.configure(state='disabled')
        threading.Thread(target=self.worker,args=(params,self.url.get().strip(),self.local.get().strip(),self.recursive.get()),daemon=True).start()

    def worker(self,params,url,local,recursive):
        """Downloads e análise fora do Tkinter; erros individuais não abortam o lote."""
        try:
            pipe=Pipeline(**params); sources=[]
            if local:
                folder=Path(local).resolve()
                if not folder.is_dir(): raise ValueError('Pasta de origem inválida.')
                candidates=folder.rglob('*') if recursive else folder.iterdir()
                sources.extend(p for p in candidates if p.is_file() and p.suffix.lower()=='.pdf' and pipe.root not in p.resolve().parents)
            urls = manifest_urls(url) if url else []
            for link in urls:
                if self.cancel.is_set(): break
                dest=pipe.root/'originais'/('download_'+uuid.uuid4().hex+'.pdf')
                try: download_pdf(link,dest,self.cancel); sources.append(dest)
                except Exception as exc: self.q.put(('log','Download falhou: '+str(exc)))
            self.q.put(('total',len(sources)))
            for index,p in enumerate(sources,1):
                if self.cancel.is_set(): break
                try:
                    status,target=pipe.process(p)
                    self.q.put(('log',f'{p.name} → {status} | relatório: {target.stem}.json'))
                except Exception as exc: self.q.put(('log',f'{p.name}: erro — {exc}'))
                self.q.put(('progress',index))
            self.q.put(('log','Interrompido.' if self.cancel.is_set() else 'Lote concluído.'))
        except Exception as exc: self.q.put(('log','ERRO: '+str(exc)))
        finally: self.q.put(('done',None))

    def poll(self):
        """Consome mensagens da thread e atualiza widgets com segurança."""
        try:
            while True:
                kind,value=self.q.get_nowait()
                if kind=='done':
                    self.running=False; self.runbutton.configure(state='normal'); self.review.refresh()
                elif kind=='total': self.progress.configure(maximum=max(1,value),value=0)
                elif kind=='progress': self.progress.configure(value=value)
                else:
                    self.log.configure(state='normal'); self.log.insert('end',value+'\n'); self.log.see('end'); self.log.configure(state='disabled')
        except queue.Empty: pass
        self.master.after(100,self.poll)


def manifest_urls(url):
    """Aceita PDF direto ou JSON explícito; não raspa diretórios arbitrários."""
    if not urlparse(url).path.lower().endswith('.json'): return [url]
    is_public_https(url)
    with requests.get(url,stream=True,timeout=(8,25),allow_redirects=False) as response:
        if 300 <= response.status_code < 400: raise ValueError('Redirecionamento bloqueado.')
        response.raise_for_status(); content=bytearray()
        for chunk in response.iter_content(16384):
            content.extend(chunk)
            if len(content)>65536: raise ValueError('Manifesto excede 64 KB.')
    links=json.loads(content)
    if not isinstance(links,list) or not 1 <= len(links) <= 100 or any(not isinstance(v,str) for v in links):
        raise ValueError('Manifesto deve ser lista JSON com 1 a 100 URLs.')
    for link in links: is_public_https(link)
    return links


if __name__=='__main__':
    # Importar este módulo não abre a janela, permitindo testes do motor.
    multiprocessing.freeze_support()
    root=tk.Tk(); App(root); root.mainloop()
