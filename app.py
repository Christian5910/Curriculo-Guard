"""Currículo Guard: interface gráfica (Tkinter) sobre o motor `engine.py`.

Execute com `python app.py`. Toda a análise vive em engine.py/workflow.py;
este arquivo apenas coleta parâmetros, dispara o lote numa thread e mostra o andamento.
"""
import json, threading, queue, multiprocessing
from pathlib import Path
from engine import validate_params, run_batch
from review_ui import ReviewPanel
try:
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox
except ImportError:  # servidor/CI sem Tk: importar este módulo continua possível
    tk = ttk = filedialog = messagebox = None

ASSETS = Path(__file__).resolve().parent / 'assets'
ICON_SIZES = (256, 64, 48, 32, 16)   # janela/barra de tarefas; o cabeçalho usa HEADER_ICON
HEADER_ICON = 48
COMPACT_LABEL_WIDTH = 46   # em caracteres: cabe o rótulo mais longo e mantém as caixas alinhadas


def load_icons(photo_image, folder=ASSETS, sizes=ICON_SIZES):
    """Carrega os PNGs do ícone que existirem; arquivo ausente ou ilegível é ignorado.

    `photo_image` é o construtor de imagem do Tk (recebido por parâmetro para poder
    testar sem interface). O app funciona normalmente, só sem ícone, se faltar a pasta.
    """
    icons = {}
    for size in sizes:
        path = Path(folder) / f'icon_{size}.png'
        if not path.is_file(): continue
        try: icons[size] = photo_image(file=str(path))
        except Exception: continue   # tk.TclError em PNG inválido; nunca impede abrir o app
    return icons


class App:
    """Interface por abas; somente a thread principal acessa o Tkinter."""

    def __init__(self, master):
        self.master = master
        master.title('Currículo Guard')
        master.geometry('850x740')
        master.minsize(800, 680)
        self.icons = load_icons(tk.PhotoImage)   # mantém referência: o Tk descarta imagens sem dono
        if self.icons:
            try: master.iconphoto(True, *[self.icons[size] for size in sorted(self.icons, reverse=True)])
            except tk.TclError: pass
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
        self.contrast = tk.DoubleVar(value=2.0)
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
        header = ttk.Frame(base); header.pack(fill='x', pady=(0, 5))
        if HEADER_ICON in self.icons: ttk.Label(header, image=self.icons[HEADER_ICON]).pack(side='left', padx=(0, 10))
        titles = ttk.Frame(header); titles.pack(side='left', anchor='center')
        ttk.Label(titles, text='Currículo Guard', font=('Arial', 18, 'bold')).pack(anchor='w')
        ttk.Label(titles, text='Triagem técnica de PDFs. Aprovação documental não é aprovação de contratação.').pack(anchor='w', pady=(2, 0))
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
        for key, label in [('size','Filtrar fonte pequena'),('contrast','Medir contraste e tinta visível contra o fundo real'),('opacity','Filtrar texto invisível ou semitransparente'),('overlap','Sinalizar possível objeto sobreposto'),('commands','Procurar padrões de instruções para IA')]:
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
            'REJEITADOS: bloqueados da ingestão automática conforme suas regras, sem decisão sobre o candidato. QUARENTENA: PDF inválido ou falha (reanalisado na próxima execução). DUPLICADOS: mesmo SHA-256 já analisado.\n\n'
            'O fundo é medido numa renderização da página sem texto (se ela falhar, usa-se o anel ao redor) e cada trecho precisa deixar tinta visível. Fotos, recortes e textos sobrepostos podem confundir a estimativa. Branco no branco não comprova má-fé. Não existe garantia de detectar toda injeção.\n\n'
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
        ttk.Label(row,text=label,width=COMPACT_LABEL_WIDTH if compact else 0).pack(side='left' if compact else 'top',anchor='w')
        ttk.Entry(row,textvariable=var,width=12 if compact else 65).pack(side='left',fill=None if compact else 'x',expand=not compact)
        if browse:
            ttk.Button(row,text='Escolher',command=lambda:var.set(filedialog.askdirectory() or var.get())).pack(side='left',padx=5)

    def settings(self):
        """Captura valores antes de iniciar a thread; valida limites e nomes."""
        data = dict(reprocess=self.reprocess.get(),timeout=self.timeout.get(),root=self.out.get().strip(),extra=[s.strip() for s in self.extra.get().split(',') if s.strip()],reject_files=self.reject.get(),reference_dpi=self.refdpi.get(),analysis_dpi=self.dpi.get(),min_px=self.minpx.get(),analysis_options=dict(max_pages=self.maxpages.get(),contrast_limit=self.contrast.get(),opacity_limit=self.opacity.get(),overlap_limit=self.cover.get(),enabled=[k for k,v in self.checks.items() if v.get()]),routes={k:v.get() for k,v in self.routes.items()})
        validate_params(data)
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
        """Roda o lote do motor fora do Tkinter; o motor reporta andamento pela fila."""
        try: run_batch(params,url,local,recursive,self.cancel,lambda kind,value:self.q.put((kind,value)))
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


if __name__=='__main__':
    multiprocessing.freeze_support()
    if tk is None: raise SystemExit('Tkinter não encontrado. No Ubuntu/Debian: sudo apt install python3-tk')
    root=tk.Tk(); App(root); root.mainloop()
