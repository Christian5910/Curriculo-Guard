"""Fila de revisão humana com visualização raster; não abre links ou anexos."""
import base64
import multiprocessing
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import fitz
from workflow import ReviewStore


def _render_child(sender, path, number, boxes):
    """Renderiza uma página com teto de pixels e destaca retângulos de alertas."""
    try:
        with fitz.open(path) as doc:
            if doc.needs_pass: raise ValueError('PDF exige senha.')
            if not 0 <= number < len(doc): raise ValueError('Página inexistente.')
            page = doc[number]; page.set_rotation(0)
            width, height = page.rect.width, page.rect.height
            if width <= 0 or height <= 0: raise ValueError('Dimensões inválidas.')
            for box in boxes:
                rect = fitz.Rect(box) & page.rect
                if not rect.is_empty: page.draw_rect(rect,color=(1,0,0),width=.7)
            scale = min(600/width, 650/height, (2_000_000/(width*height))**.5)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale,scale),alpha=False)
            sender.send(('ok',(pix.tobytes('png'),len(doc))))
    except Exception as exc: sender.send(('error',str(exc)))
    finally: sender.close()


def render_preview(path, number, boxes):
    """Processo separado e limite de 15s para não congelar o revisor."""
    ctx=multiprocessing.get_context('spawn'); receiver,sender=ctx.Pipe(duplex=False)
    proc=ctx.Process(target=_render_child,args=(sender,str(path),number,boxes),daemon=True)
    try:
        proc.start();sender.close()
        if not receiver.poll(15): raise TimeoutError('Prévia excedeu 15s.')
        status,data=receiver.recv()
        if status!='ok': raise ValueError(data)
        return data
    finally:
        if proc.pid is not None:
            if proc.is_alive(): proc.terminate()
            proc.join(2)
            if proc.is_alive(): proc.kill();proc.join()
        sender.close();receiver.close()


class ReviewPanel(ttk.Frame):
    """Lista, detalhes, CSV e decisões; desabilita alterações durante o lote."""
    def __init__(self, parent, root_var, busy):
        super().__init__(parent,padding=8)
        self.root_var,self.busy=root_var,busy
        self.rows={};self.previews=queue.Queue();self.preview_token=0
        self.filter=tk.StringVar(value='verificacao_humana');self.search=tk.StringVar()
        row=ttk.Frame(self);row.pack(fill='x')
        ttk.Combobox(row,textvariable=self.filter,values=['todos','aprovados','verificacao_humana','rejeitados','quarentena','duplicados'],state='readonly',width=22).pack(side='left')
        ttk.Entry(row,textvariable=self.search,width=23).pack(side='left',padx=5)
        ttk.Button(row,text='Atualizar / buscar',command=self.refresh).pack(side='left')
        ttk.Button(row,text='Exportar CSV',command=self.export).pack(side='right')
        table_box=ttk.Frame(self);table_box.pack(fill='both',expand=True,pady=5)
        self.table=ttk.Treeview(table_box,columns=('name','status','alerts'),show='headings',height=6,selectmode='browse')
        for key,title,width in [('name','Arquivo',310),('status','Destino',170),('alerts','Alertas',270)]:
            self.table.heading(key,text=title);self.table.column(key,width=width)
        self.table.pack(side='left',fill='both',expand=True)
        scroll=ttk.Scrollbar(table_box,orient='vertical',command=self.table.yview);scroll.pack(side='right',fill='y');self.table.configure(yscrollcommand=scroll.set)
        self.table.bind('<<TreeviewSelect>>',lambda event:self.details())
        detail_box=ttk.Frame(self);detail_box.pack(fill='both',expand=True)
        self.info=tk.Text(detail_box,height=6,wrap='word',state='disabled');self.info.pack(side='left',fill='both',expand=True)
        detail_scroll=ttk.Scrollbar(detail_box,orient='vertical',command=self.info.yview);detail_scroll.pack(side='right',fill='y');self.info.configure(yscrollcommand=detail_scroll.set)
        reviewer_row=ttk.Frame(self);reviewer_row.pack(fill='x',pady=4)
        self.reviewer=tk.StringVar();self.reason=tk.StringVar()
        ttk.Label(reviewer_row,text='Revisor').pack(side='left');ttk.Entry(reviewer_row,textvariable=self.reviewer,width=22).pack(side='left',padx=5)
        ttk.Label(reviewer_row,text='Justificativa').pack(side='left');ttk.Entry(reviewer_row,textvariable=self.reason).pack(side='left',fill='x',expand=True,padx=5)
        actions=ttk.Frame(self);actions.pack(fill='x')
        for label,status in [('Liberar texto filtrado','aprovados'),('Bloquear documento','rejeitados'),('Devolver à revisão','verificacao_humana')]:
            ttk.Button(actions,text=label,command=lambda v=status:self.decide(v)).pack(side='left',padx=2)
        ttk.Button(actions,text='Ver página',command=self.preview).pack(side='right')
        self.summary=ttk.Label(self,text='Selecione a saída em Entrada e clique Atualizar.');self.summary.pack(anchor='w',pady=3)
        self.after(100,self.poll_preview)

    def store(self):
        """Usa a saída atual; não lê nenhum currículo de outro diretório."""
        return ReviewStore(self.root_var.get())

    def refresh(self):
        """Atualiza a tabela e limpa detalhes antigos para evitar seleção enganosa."""
        if self.busy(): return messagebox.showinfo('Lote em curso','Aguarde o término antes de revisar.')
        rows,errors=self.store().list_reports(self.filter.get(),self.search.get())
        self.table.delete(*self.table.get_children());self.rows={}
        self.show_text('')
        for index,(path,data) in enumerate(rows):
            key=str(index);self.rows[key]=(path,data)
            self.table.insert('', 'end',iid=key,values=(data.get('original_name',path.stem),data.get('status',''),'; '.join(a.get('type','') for a in data.get('alerts',[]))))
        self.summary.configure(text=f'{len(rows)} documentos | {len(errors)} relatórios inválidos (não liberados).')

    def selected(self):
        """Exige seleção atual e rejeita revisão enquanto há processamento."""
        if self.busy(): raise ValueError('Aguarde o término do lote.')
        keys=self.table.selection()
        if not keys or keys[0] not in self.rows: raise ValueError('Selecione um documento.')
        path,data=self.rows[keys[0]]
        if path.parent.resolve() != self.store().reports.resolve(): raise ValueError('Saída mudou; atualize a tabela.')
        return path,data

    def show_text(self,text):
        """Detalhes são somente leitura e nunca interpretados como comandos."""
        self.info.configure(state='normal');self.info.delete('1.0','end');self.info.insert('end',text);self.info.configure(state='disabled')

    def details(self):
        """Expõe motivo, trecho e histórico sem executar ou abrir conteúdos."""
        try:
            _,data=self.selected()
            lines=[f"Status: {data.get('status')} | SHA-256: {data.get('sha256','ausente')}"]
            for alert in data.get('alerts',[]):
                lines.append(f"Página {alert.get('page','—')} | {alert.get('type')}: {alert.get('detail','')}\nTrecho: {alert.get('sample','')}")
            for event in data.get('history',[]):
                lines.append(f"Revisão {event['time']} | {event['reviewer']} → {event['to']}: {event['reason']}")
            lines.append('\nTEXTO FILTRADO (dados não confiáveis):\n'+data.get('text','')[:12000])
            self.show_text('\n\n'.join(lines))
        except ValueError: self.show_text('')

    def decide(self,status):
        """Justificativa e revisor obrigatórios; atualizar histórico após decisão."""
        try:
            path,_=self.selected();self.store().decide(path,status,self.reviewer.get(),self.reason.get())
            self.refresh();self.reason.set('')
        except Exception as exc: messagebox.showerror('Revisão não aplicada',str(exc))

    def export(self):
        """CSV traz inventário de todos os destinos, sem conteúdo do currículo."""
        if self.busy(): return messagebox.showinfo('Lote em curso','Aguarde o término.')
        path=filedialog.asksaveasfilename(defaultextension='.csv',filetypes=[('CSV','*.csv')])
        if path:
            try:
                count,errors=self.store().export_csv(path)
                self.summary.configure(text=f'Exportados {count} registros; {errors} relatórios inválidos ignorados.')
            except Exception as exc: messagebox.showerror('Exportação',str(exc))

    def preview(self):
        """Abre visualização paginada rasterizada, sem iniciar leitor PDF externo."""
        try:
            _,data=self.selected();path=self.store().checked_pdf(data)
        except Exception as exc: return messagebox.showerror('Prévia',str(exc))
        window=tk.Toplevel(self);window.title('Prévia — retângulos vermelhos indicam alertas');window.geometry('650x760')
        controls=ttk.Frame(window,padding=5);controls.pack(fill='x')
        number=tk.IntVar(value=1)
        ttk.Label(controls,text='Página').pack(side='left');ttk.Entry(controls,textvariable=number,width=6).pack(side='left',padx=5)
        image_label=ttk.Label(window,text='Carregando…');image_label.pack(fill='both',expand=True)
        def load():
            try: page=number.get()-1
            except tk.TclError: return
            self.preview_token+=1;token=self.preview_token
            boxes=[a['bbox'] for a in data.get('alerts',[]) if a.get('page')==page+1 and 'bbox' in a]
            def work():
                try: self.previews.put((token,image_label,number,page,render_preview(path,page,boxes),None))
                except Exception as exc: self.previews.put((token,image_label,number,page,None,str(exc)))
            threading.Thread(target=work,daemon=True).start()
        ttk.Button(controls,text='Mostrar',command=load).pack(side='left')
        ttk.Label(controls,text='Informe o número e clique Mostrar.').pack(side='left',padx=10)
        load()

    def poll_preview(self):
        """Imagem Tk criada na thread principal; resultados antigos são ignorados."""
        try:
            while True:
                token,label,number,page,result,error=self.previews.get_nowait()
                if token!=self.preview_token or not label.winfo_exists(): continue
                if error: label.configure(text=error,image='');continue
                png,total=result
                label.photo=tk.PhotoImage(data=base64.b64encode(png).decode())
                label.configure(image=label.photo,text='')
                self.summary.configure(text=f'Prévia da página {page+1}/{total}.')
        except queue.Empty: pass
        self.after(100,self.poll_preview)
