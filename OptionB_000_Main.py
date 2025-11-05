# OptionC_00_Main.py
# - Giữ nguyên phân đoạn gốc (English/Viet-sub)
# - Scrollbar riêng, không clipping
# - Bảng từ vựng có cột No., sắp theo thứ tự xuất hiện
# - Nghĩa theo NGỮ CẢNH ĐOẠN (api.llm_word_vi)
# - Viet-sub highlight theo meaning_vi
# - Export TXT: 3 cột (word, pos, meaning_vi)
# - Khi đánh dấu từ mới: KHÔNG popup -> PHÁT ÂM ngay
# - Đánh số (bubble) ở CẢ English & Viet-sub, đồng bộ khi cuộn/đổi font/đổi theme

import os
import json
import time
import threading
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import nltk
from nltk.tokenize import sent_tokenize
import pygame

# ==== nạp OptionC_api_module.py bằng importlib ====
import importlib.util
API_PATH = os.path.join(os.path.dirname(__file__), "OptionC_api_module.py")
_spec = importlib.util.spec_from_file_location("api_module", API_PATH)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)

APP_TITLE = "Vocabulary Reader – Context Aware"
DEFAULT_FONT_SIZE = 18
MIN_FONT, MAX_FONT = 12, 36

HIGHLIGHT_COLORS = {
    "word_new": "#fff7ad",
    "word_proficient": "#c7f9cc",
    "word_review": "#ffd6a5",
    "reading": "#ffd000",
}

THEMES = {
    "light": {"text_fg": "#222", "text_bg": "#ffffff", "sel_bg": "#5dade2"},
    "dark":  {"text_fg": "#e6e6e6", "text_bg": "#1f1f1f", "sel_bg": "#5dade2"},
}

CACHE_DIR = os.path.join(os.getcwd(), "cache", "audio")
os.makedirs(CACHE_DIR, exist_ok=True)

@dataclass
class WordEntry:
    display: str
    pos: str
    ipa: str
    vi_meaning: str
    gloss_en: str
    context_sentence: str
    offsets: List[Dict] = field(default_factory=list)
    status: str = "new"
    added_at: str = ""

def current_iso() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

class VocabReaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE); self.geometry("1200x700"); self.minsize(1000, 600)
        self.theme = "light"; self.font_size = DEFAULT_FONT_SIZE
        self.text_path = None
        self.text_content = ""   # English gốc (giữ nguyên xuống dòng)
        self.sentences_cache: List[Tuple[int,int]] = []

        self.entries: Dict[str, WordEntry] = {}
        self.llm_cache: Dict[str, Dict] = {}

        self.tts = api.TTSManager(cache_dir=CACHE_DIR, lang="en", tld="com")
        self._reading_thread = None
        self._reading_stop = threading.Event()
        self._reading_pause = threading.Event()
        self._reading_mode = None

        # Scrollbar & bubble markers
        self.en_scrollbar: ttk.Scrollbar | None = None
        self._marker_en: list[tk.Canvas] = []
        self._marker_vi: list[tk.Canvas] = []

        self._build_ui()
        self._bind_keys()
        self._apply_theme()

    # ---------- UI ----------
    def _build_ui(self):
        style = ttk.Style(self)
        style.configure("Treeview", font=("Segoe UI", 14))
        style.configure("Treeview.Heading", font=("Segoe UI", 15, "bold"))

        self._build_menubar()

        tb = ttk.Frame(self); tb.pack(side="top", fill="x")
        ttk.Button(tb, text="Open .txt", command=self.action_open_txt).pack(side="left", padx=4, pady=4)
        ttk.Button(tb, text="Save Session (JSON)", command=self.action_save_session).pack(side="left", padx=4)
        ttk.Button(tb, text="Load Session (JSON)", command=self.action_load_session).pack(side="left", padx=4)
        ttk.Button(tb, text="Export TXT", command=self.action_export_txt).pack(side="left", padx=4)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(tb, text="Read Paragraph", command=lambda: self.start_reading("paragraph")).pack(side="left", padx=4)
        ttk.Button(tb, text="Read Sentence", command=lambda: self.start_reading("sentence")).pack(side="left", padx=4)
        ttk.Button(tb, text="Read Word", command=lambda: self.start_reading("word")).pack(side="left", padx=4)
        self.btn_pause = ttk.Button(tb, text="Pause", command=self.toggle_pause, state="disabled"); self.btn_pause.pack(side="left", padx=4)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(tb, text="Toggle Theme", command=self.toggle_theme).pack(side="left", padx=4)
        ttk.Label(tb, text="Font:").pack(side="left", padx=(12,2))
        self.font_slider = ttk.Scale(tb, from_=MIN_FONT, to=MAX_FONT, value=self.font_size, command=self.on_change_font); self.font_slider.pack(side="left", padx=4)

        paned = ttk.PanedWindow(self, orient="horizontal"); paned.pack(fill="both", expand=True)

        # ==== LEFT: [English] [Viet-sub] ====
        left = ttk.Frame(paned); paned.add(left, weight=3)
        self.nb_left = ttk.Notebook(left); self.nb_left.pack(fill="both", expand=True)

        # English tab: Text + Scrollbar
        self.tab_en = ttk.Frame(self.nb_left); self.nb_left.add(self.tab_en, text="English")
        en_wrap = ttk.Frame(self.tab_en); en_wrap.pack(fill="both", expand=True)

        self.text_en = tk.Text(en_wrap, wrap="word", undo=True, font=("Segoe UI", self.font_size))
        self.text_en.pack(side="left", fill="both", expand=True)
        self.text_en.config(selectbackground="#5dade2", selectforeground="#000000")

        self.en_scrollbar = ttk.Scrollbar(en_wrap, orient="vertical")
        self.en_scrollbar.pack(side="right", fill="y")

        # liên kết scrollbar <-> text + vẽ bubble khi cuộn
        self.text_en.configure(yscrollcommand=self._on_en_scroll)
        self.en_scrollbar.configure(command=self._on_en_scrollbar)

        for t, col in HIGHLIGHT_COLORS.items():
            self.text_en.tag_configure(t, background=col)

        # Viet-sub tab
        self.tab_vi = ttk.Frame(self.nb_left); self.nb_left.add(self.tab_vi, text="Viet-sub")
        vi_wrap = ttk.Frame(self.tab_vi); vi_wrap.pack(fill="both", expand=True)
        self.text_vi = tk.Text(vi_wrap, wrap="word", font=("Segoe UI", self.font_size), bg="#fafafa")
        self.text_vi.pack(side="left", fill="both", expand=True)
        self.text_vi.config(selectbackground="#5dade2", selectforeground="#000000")
        vi_scroll = ttk.Scrollbar(vi_wrap, orient="vertical", command=self.text_vi.yview)
        vi_scroll.pack(side="right", fill="y")
        self.text_vi.configure(yscrollcommand=vi_scroll.set)
        for t, col in HIGHLIGHT_COLORS.items():
            self.text_vi.tag_configure(t, background=col)

        # Context menu (English only)
        self.cm = tk.Menu(self, tearoff=0)
        self.cm.add_command(label="Đánh dấu từ mới (Alt+D)", command=self.mark_new_word)
        self.cm.add_command(label="Phát âm", command=self.speak_selection)
        self.cm.add_separator()
        self.cm.add_command(label="Đặt trạng thái: Đã thuộc", command=lambda: self.set_status_selection("proficient"))
        self.cm.add_command(label="Đặt trạng thái: Cần ôn lại", command=lambda: self.set_status_selection("review"))
        self.cm.add_command(label="Bỏ đánh dấu", command=self.clear_selection_highlight)
        self.text_en.bind("<Button-3>", self._show_context_menu)

        # Cập nhật bubble khi thay đổi hiển thị
        self.text_en.bind("<Configure>", lambda e: self._schedule_update_markers())
        self.text_en.bind("<KeyRelease>", lambda e: self._schedule_update_markers())
        self.text_en.bind("<ButtonRelease-1>", lambda e: self._schedule_update_markers())
        self.text_en.bind("<MouseWheel>", lambda e: self._schedule_update_markers())   # Windows
        self.text_en.bind("<Button-4>", lambda e: self._schedule_update_markers())      # Linux
        self.text_en.bind("<Button-5>", lambda e: self._schedule_update_markers())      # Linux

        # Viet-sub cũng cần bind để vẽ số khi cuộn/chuyển
        self.text_vi.bind("<Configure>", lambda e: self._schedule_update_markers())
        self.text_vi.bind("<KeyRelease>", lambda e: self._schedule_update_markers())
        self.text_vi.bind("<ButtonRelease-1>", lambda e: self._schedule_update_markers())
        self.text_vi.bind("<MouseWheel>", lambda e: self._schedule_update_markers())
        self.text_vi.bind("<Button-4>", lambda e: self._schedule_update_markers())
        self.text_vi.bind("<Button-5>", lambda e: self._schedule_update_markers())

        self.nb_left.bind("<<NotebookTabChanged>>", self._on_left_tab_changed)

        # ==== RIGHT: Personal dictionary ====
        right = ttk.Frame(paned); paned.add(right, weight=2)
        self.nb_right = ttk.Notebook(right); self.nb_right.pack(fill="both", expand=True)
        self.tab_dict = ttk.Frame(self.nb_right); self.nb_right.add(self.tab_dict, text="Từ điển cá nhân")

        cols = ("No.","Word","POS","Meaning (VI)")
        self.tree = ttk.Treeview(self.tab_dict, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("No.", width=60, anchor="center")
        self.tree.column("Word", width=220, anchor="w")
        self.tree.column("POS", width=120, anchor="w")
        self.tree.column("Meaning (VI)", width=520, anchor="w")
        self.tree.pack(fill="both", expand=True)

        dict_tb = ttk.Frame(self.tab_dict); dict_tb.pack(fill="x")
        ttk.Button(dict_tb, text="Phát âm", command=self.speak_selected_word).pack(side="left", padx=4, pady=4)
        ttk.Button(dict_tb, text="Đổi trạng thái → Đã thuộc", command=lambda: self.set_status_selected("proficient")).pack(side="left", padx=4)
        ttk.Button(dict_tb, text="Đổi trạng thái → Cần ôn lại", command=lambda: self.set_status_selected("review")).pack(side="left", padx=4)
        ttk.Button(dict_tb, text="Xoá dòng", command=self.delete_selected_word).pack(side="left", padx=4)
        ttk.Button(dict_tb, text="Export TXT", command=self.action_export_txt).pack(side="left", padx=4)

        self.text = self.text_en  # tương thích code cũ

    def _build_menubar(self):
        m = tk.Menu(self)
        mf = tk.Menu(m, tearoff=0)
        mf.add_command(label="Open .txt", command=self.action_open_txt, accelerator="Ctrl+O")
        mf.add_command(label="Save Session (JSON)", command=self.action_save_session, accelerator="Ctrl+S")
        mf.add_command(label="Load Session (JSON)", command=self.action_load_session)
        mf.add_separator(); mf.add_command(label="Export TXT", command=self.action_export_txt, accelerator="Ctrl+E")
        mf.add_separator(); mf.add_command(label="Exit", command=self.destroy)
        m.add_cascade(label="File", menu=mf)

        mv = tk.Menu(m, tearoff=0)
        mv.add_command(label="Toggle Theme", command=self.toggle_theme, accelerator="Ctrl+T")
        m.add_cascade(label="View", menu=mv)

        mt = tk.Menu(m, tearoff=0)
        mt.add_command(label="Read Paragraph", command=lambda: self.start_reading("paragraph"), accelerator="Ctrl+P")
        mt.add_command(label="Read Sentence", command=lambda: self.start_reading("sentence"), accelerator="Ctrl+Shift+S")
        mt.add_command(label="Read Word", command=lambda: self.start_reading("word"), accelerator="Ctrl+W")
        mt.add_command(label="Pause/Resume", command=self.toggle_pause, accelerator="Space")
        m.add_cascade(label="Tools", menu=mt)

        mh = tk.Menu(m, tearoff=0)
        mh.add_command(label="About", command=lambda: messagebox.showinfo("About", "Vocabulary Reader – Context Aware"))
        m.add_cascade(label="Help", menu=mh)
        self.config(menu=m)

    def _bind_keys(self):
        self.bind("<Alt-d>", lambda e: self.mark_new_word())
        self.bind("<Control-o>", lambda e: self.action_open_txt())
        self.bind("<Control-s>", lambda e: self.action_save_session())
        self.bind("<Control-e>", lambda e: self.action_export_txt())
        self.bind("<Control-p>", lambda e: self.start_reading("paragraph"))
        self.bind("<Control-Shift-S>", lambda e: self.start_reading("sentence"))
        self.bind("<Control-w>", lambda e: self.start_reading("word"))
        self.bind("<space>", lambda e: self.toggle_pause())
        self.bind("<Control-t>", lambda e: self.toggle_theme())

    def _apply_theme(self):
        c = THEMES[self.theme]
        for widget in (self.text_en, self.text_vi):
            widget.config(bg=c["text_bg"], fg=c["text_fg"], insertbackground=c["text_fg"])
            widget.config(selectbackground=c["sel_bg"], selectforeground="#000000")
        self.after_idle(self._update_markers_all)

    # ---------- File ops ----------
    def action_open_txt(self):
        path = filedialog.askopenfilename(filetypes=[("UTF-8 Text", "*.txt"), ("All files", "*.*")])
        if not path: return
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        self.text_path = path
        self.text_content = raw  # GIỮ NGUYÊN phân đoạn gốc
        self._render_text_en(self.text_content)
        self._build_sentence_offsets(self.text_content)
        self.entries.clear(); self.llm_cache.clear()
        self.tree.delete(*self.tree.get_children())
        self.title(f"{APP_TITLE} – {os.path.basename(path)}")
        self.text_vi.delete("1.0", "end")
        self.after_idle(self._update_markers_all)

    def _render_text_en(self, content: str):
        self.text_en.configure(state="normal"); self.text_en.delete("1.0", "end"); self.text_en.insert("1.0", content)

    def _build_sentence_offsets(self, content: str):
        self.sentences_cache.clear()
        idx = 0
        for s in sent_tokenize(content):
            start = content.find(s, idx)
            if start == -1: start = idx
            end = start + len(s)
            self.sentences_cache.append((start, end))
            idx = end

    def action_save_session(self):
        data = {
            "text_path": self.text_path,
            "text_content": self.text_content,
            "created_at": current_iso(),
            "entries": [asdict(w) for w in self.entries.values()],
            "theme": self.theme,
            "font_size": self.font_size
        }
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Saved", "Đã lưu phiên học.")

    def action_load_session(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path: return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.text_content = data.get("text_content", "")
        self._render_text_en(self.text_content)
        self._build_sentence_offsets(self.text_content)
        self.theme = data.get("theme", "light")
        self.font_size = data.get("font_size", DEFAULT_FONT_SIZE)
        self.font_slider.set(self.font_size)
        self.text_en.config(font=("Segoe UI", self.font_size)); self.text_vi.config(font=("Segoe UI", self.font_size))
        self._apply_theme()

        self.entries.clear(); self.tree.delete(*self.tree.get_children())
        for w in data.get("entries", []):
            entry = WordEntry(**w)
            self.entries[self._entry_key(entry.display, entry.context_sentence)] = entry
        self._refresh_tree_sorted()
        self._reapply_highlights_en()
        self.text_vi.delete("1.0", "end")
        self.after_idle(self._update_markers_all)

    # ---------- Export TXT: chỉ 3 cột ----------
    def action_export_txt(self):
        if not self.entries:
            messagebox.showwarning("Export", "Chưa có từ để export."); return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path: return
        with open(path, "w", encoding="utf-8") as f:
            f.write("word\tpos\tmeaning_vi\n")
            for e in self._entries_sorted_by_offset():
                mvi = (e.vi_meaning or "").replace("\n", " ").replace("\t", "  ")
                f.write(f"{e.display}\t{e.pos}\t{mvi}\n")
        messagebox.showinfo("Export", "Đã export TXT (UTF-8) với 3 cột.")

    # ---------- Context menu (English) ----------
    def _show_context_menu(self, event):
        try:
            self.cm.tk_popup(event.x_root, event.y_root)
        finally:
            self.cm.grab_release()

    def _find_paragraph(self, full: str, start: int, end: int) -> str:
        left = full.rfind("\n\n", 0, start)
        right = full.find("\n\n", end)
        p_start = 0 if left == -1 else left + 2
        p_end = len(full) if right == -1 else right
        return full[p_start:p_end].strip()

    def mark_new_word(self):
        try:
            start = self.text_en.index("sel.first"); end = self.text_en.index("sel.last")
        except tk.TclError:
            messagebox.showwarning("Đánh dấu", "Hãy bôi đen 1 từ/cụm từ trên tab English."); return

        selected = self.text_en.get(start, end).strip()
        if not selected: return

        full = self.text_en.get("1.0", "end-1c")
        abs_start = self._index_to_abs_pos(start, full); abs_end = self._index_to_abs_pos(end, full)

        paragraph = self._find_paragraph(full, abs_start, abs_end)

        para_key = str(abs(hash(paragraph)))
        cache_key = f"{selected.lower()}|{para_key}"

        vi_meaning = ""; pos = ""; ipa = ""; gloss_en = ""
        if cache_key in self.llm_cache:
            data = self.llm_cache[cache_key]
            pos = data.get("pos","other"); ipa = data.get("ipa","")
            gloss_en = data.get("gloss_en",""); vi_meaning = data.get("meaning_vi","")
        else:
            di = api.lookup_dictionaryapi(selected); ipa = di.get("ipa",""); pos_guess = di.get("pos","")
            try:
                data = api.llm_word_vi(selected, paragraph)
                pos = data.get("pos","") or pos_guess or "other"
                ipa = data.get("ipa","") or ipa
                gloss_en = data.get("gloss_en",""); vi_meaning = data.get("meaning_vi","")
                self.llm_cache[cache_key] = data
            except Exception as e:
                if "OPENAI_INSUFFICIENT_QUOTA" in str(e) or "insufficient_quota" in str(e):
                    messagebox.showwarning("OpenAI hết hạn mức","Project/API key hiện chưa có quota. Sẽ dùng định nghĩa EN tạm.")
                    pos = pos_guess or "other"
                    defs = api.lookup_dictionaryapi(selected).get("defs") or []
                    gloss_en = (defs or [f"Meaning of '{selected}'"])[0]
                    vi_meaning = (gloss_en.split(";")[0]).split(",")[0].strip().split(" ")[:3]
                    vi_meaning = " ".join(vi_meaning)
                else:
                    messagebox.showwarning("OpenAI lỗi", str(e)); return

        entry = WordEntry(
            display=selected, pos=pos or "other", ipa=ipa, vi_meaning=vi_meaning, gloss_en=gloss_en,
            context_sentence=paragraph, offsets=[{"start": abs_start, "end": abs_end}],
            status="new", added_at=current_iso()
        )
        self.entries[self._entry_key(selected, paragraph)] = entry

        # highlight English
        self._tag_range(abs_start, abs_end, "word_new")

        # cập nhật bảng theo thứ tự xuất hiện
        self._refresh_tree_sorted()

        # cập nhật highlight Viet-sub
        self._update_vietsub_highlights()

        # PHÁT ÂM thay cho popup
        try:
            self.tts.speak(selected)
        except Exception as e:
            messagebox.showerror("TTS", str(e))

        self.after_idle(self._update_markers_all)

    def speak_selection(self):
        try:
            txt = self.text_en.get("sel.first", "sel.last").strip()
        except tk.TclError:
            idx = self.text_en.index("insert wordstart")
            txt = self.text_en.get(idx, "insert wordend").strip()
        if txt:
            try: self.tts.speak(txt)
            except Exception as e: messagebox.showerror("TTS", str(e))

    def set_status_selection(self, status: str):
        try:
            start = self.text_en.index("sel.first"); end = self.text_en.index("sel.last")
        except tk.TclError:
            messagebox.showwarning("Trạng thái", "Bôi đen từ đã đánh dấu trên tab English."); return
        full = self.text_en.get("1.0", "end-1c")
        abs_start = self._index_to_abs_pos(start, full); abs_end = self._index_to_abs_pos(end, full)

        for _, w in self.entries.items():
            for off in w.offsets:
                if not (abs_end <= off["start"] or abs_start >= off["end"]):
                    w.status = status
                    self._clear_range_tags(abs_start, abs_end)
                    self._tag_range(abs_start, abs_end, self._status_to_tag(status))
                    self._refresh_tree_row(w)
                    self._update_vietsub_highlights()
                    self.after_idle(self._update_markers_all)
                    return

    def clear_selection_highlight(self):
        try:
            start = self.text_en.index("sel.first"); end = self.text_en.index("sel.last")
        except tk.TclError:
            return
        full = self.text_en.get("1.0", "end-1c")
        abs_start = self._index_to_abs_pos(start, full); abs_end = self._index_to_abs_pos(end, full)

        removed_any = False
        for k in list(self.entries.keys()):
            w = self.entries[k]
            keep, changed = [], False
            for off in w.offsets:
                if not (abs_end <= off["start"] or abs_start >= off["end"]):
                    changed = True
                else:
                    keep.append(off)
            if changed:
                self._clear_range_tags(abs_start, abs_end)
                if keep:
                    w.offsets = keep; self._refresh_tree_row(w)
                else:
                    del self.entries[k]; self._remove_tree_row_by_key(k); removed_any = True
        if removed_any:
            self._update_vietsub_highlights()
        self.after_idle(self._update_markers_all)

    # ---------- Reading ----------
    def start_reading(self, mode: str):
        if self._reading_thread and self._reading_thread.is_alive():
            messagebox.showinfo("Reading", "Đang đọc. Hãy Pause/Resume hoặc chờ xong."); return
        self._reading_mode = mode
        self._reading_stop.clear(); self._reading_pause.clear()
        self.btn_pause.config(state="normal", text="Pause")
        self._reading_thread = threading.Thread(target=self._reading_worker, daemon=True); self._reading_thread.start()

    def _reading_worker(self):
        full = self.text_en.get("1.0", "end-1c")
        try:
            if self._reading_mode == "paragraph":
                paragraphs = [p.strip() for p in full.split("\n\n") if p.strip()]
                for p in paragraphs:
                    self._highlight_sentence_once(full, p)
                    self.tts.speak(p); self._wait_audio_or_pause(); self._clear_reading_highlight()
            elif self._reading_mode == "sentence":
                cur = self._get_current_sentence(full)
                if cur:
                    self._highlight_sentence_once(full, cur)
                    self.tts.speak(cur); self._wait_audio_or_pause(); self._clear_reading_highlight()
            elif self._reading_mode == "word":
                try:
                    txt = self.text_en.get("sel.first", "sel.last").strip()
                except tk.TclError:
                    idx = self.text_en.index("insert wordstart"); txt = self.text_en.get(idx, "insert wordend").strip()
                if txt:
                    try: start = self.text_en.index("sel.first"); end = self.text_en.index("sel.last")
                    except tk.TclError: start = self.text_en.index("insert wordstart"); end = self.text_en.index("insert wordend")
                    self.text_en.tag_add("reading", start, end)
                    self.tts.speak(txt); self._wait_audio_or_pause(); self._clear_reading_highlight()
        finally:
            self.btn_pause.config(state="disabled", text="Pause")

    def _wait_audio_or_pause(self):
        while pygame.mixer.get_busy():
            if self._reading_stop.is_set(): pygame.mixer.stop(); break
            if self._reading_pause.is_set(): time.sleep(0.1); continue
            time.sleep(0.05)

    def _highlight_sentence_once(self, full, segment):
        start = full.find(segment)
        if start == -1: return
        end = start + len(segment)
        self._tag_range(start, end, "reading")

    def _clear_reading_highlight(self):
        self.text_en.tag_remove("reading", "1.0", "end")

    def toggle_pause(self):
        if not (self._reading_thread and self._reading_thread.is_alive()): return
        if not self._reading_pause.is_set():
            self._reading_pause.set(); self.btn_pause.config(text="Resume")
        else:
            self._reading_pause.clear(); self.btn_pause.config(text="Pause")

    # ---------- Helpers ----------
    def on_change_font(self, value):
        self.font_size = max(MIN_FONT, min(MAX_FONT, int(float(value))))
        self.text_en.config(font=("Segoe UI", self.font_size))
        self.text_vi.config(font=("Segoe UI", self.font_size))
        self.after_idle(self._update_markers_all)

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self._apply_theme()

    def _index_to_abs_pos(self, tkindex: str, full_text: str) -> int:
        line, col = map(int, tkindex.split("."))
        lines = full_text.split("\n")
        return sum(len(l)+1 for l in lines[:line-1]) + col

    def _abs_to_index(self, abspos: int, full_text: str) -> str:
        lines = full_text.split("\n"); acc = 0
        for i, l in enumerate(lines, start=1):
            if acc + len(l) >= abspos: return f"{i}.{abspos-acc}"
            acc += len(l) + 1
        return f"{len(lines)}.{len(lines[-1]) if lines else 0}"

    def _get_current_sentence(self, full: str):
        try: idx = self.text_en.index("insert")
        except tk.TclError: return None
        abs_pos = self._index_to_abs_pos(idx, full)
        for s_start, s_end in self.sentences_cache:
            if s_start <= abs_pos <= s_end: return full[s_start:s_end]
        return None

    def _tag_range(self, abs_start: int, abs_end: int, tag: str):
        full = self.text_en.get("1.0", "end-1c")
        i1 = self._abs_to_index(abs_start, full); i2 = self._abs_to_index(abs_end, full)
        self.text_en.tag_add(tag, i1, i2)

    def _clear_range_tags(self, abs_start: int, abs_end: int):
        full = self.text_en.get("1.0", "end-1c")
        i1 = self._abs_to_index(abs_start, full); i2 = self._abs_to_index(abs_end, full)
        for t in ["word_new","word_proficient","word_review","reading"]:
            self.text_en.tag_remove(t, i1, i2)

    def _status_to_tag(self, status: str) -> str:
        return {"new":"word_new","proficient":"word_proficient","review":"word_review"}.get(status, "word_new")

    def _entry_key(self, word: str, sentence: str) -> str:
        return f"{word.lower()}|{abs(hash(sentence))}"

    # ----- Tree sorting by first appearance -----
    def _entries_sorted_by_offset(self) -> List[WordEntry]:
        return sorted(self.entries.values(), key=lambda e: (e.offsets[0]["start"] if e.offsets else 1e18))

    def _refresh_tree_sorted(self):
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self._entries_sorted_by_offset(), start=1):
            self._insert_tree_row(e, i)

    def _insert_tree_row(self, e: WordEntry, order_no: int):
        self.tree.insert("", "end", iid=self._entry_key(e.display, e.context_sentence),
                         values=[order_no, e.display, e.pos, e.vi_meaning])

    def _refresh_tree_row(self, e: WordEntry):
        sorted_entries = self._entries_sorted_by_offset()
        order_map = { self._entry_key(x.display, x.context_sentence): i+1
                      for i, x in enumerate(sorted_entries) }
        iid = self._entry_key(e.display, e.context_sentence)
        if self.tree.exists(iid):
            self.tree.item(iid, values=[order_map.get(iid, ""), e.display, e.pos, e.vi_meaning])

    def _remove_tree_row_by_key(self, key: str):
        if self.tree.exists(key): self.tree.delete(key)

    # ----- Reapply EN highlights after load -----
    def _reapply_highlights_en(self):
        for e in self.entries.values():
            for off in e.offsets:
                self._tag_range(off["start"], off["end"], self._status_to_tag(e.status))
        self.after_idle(self._update_markers_all)

    # ----- Viet-sub handling -----
    def _on_left_tab_changed(self, event):
        tab = self.nb_left.nametowidget(self.nb_left.select())
        if tab is self.tab_vi:
            self.translate_full_text()
        self.after_idle(self._update_markers_all)

    def translate_full_text(self):
        english = self.text_en.get("1.0", "end-1c")
        if not english.strip():
            self.text_vi.delete("1.0", "end"); return
        try:
            vi = api._openai_chat(
                [
                    {"role": "system", "content": "You translate English to natural, fluent Vietnamese. Keep paragraph breaks exactly as input."},
                    {"role": "user", "content": english},
                ],
                temperature=0.2,
            )
        except Exception as e:
            if "OPENAI_INSUFFICIENT_QUOTA" in str(e) or "insufficient_quota" in str(e):
                messagebox.showwarning("OpenAI hết hạn mức", "Không thể dịch vì quota. Vui lòng kiểm tra API key/project.")
                return
            else:
                messagebox.showerror("Lỗi dịch", str(e)); return
        self.text_vi.delete("1.0", "end")
        self.text_vi.insert("1.0", vi)
        self._update_vietsub_highlights()
        self.after_idle(self._update_markers_all)

    def _update_vietsub_highlights(self):
        for t in ["word_new","word_proficient","word_review","reading"]:
            self.text_vi.tag_remove(t, "1.0", "end")
        content = self.text_vi.get("1.0","end-1c")
        if not content.strip(): return
        for e in self.entries.values():
            tag = self._status_to_tag(e.status)
            needle = (e.vi_meaning or "").strip()
            if not needle: continue
            start = "1.0"
            while True:
                idx = self.text_vi.search(needle, start, stopindex="end", nocase=True)
                if not idx: break
                end = f"{idx}+{len(needle)}c"
                self.text_vi.tag_add(tag, idx, end)
                start = end

    # ---------- Right-side actions ----------
    def speak_selected_word(self):
        sel = self.tree.selection()
        if not sel: return
        key = sel[0]; e = self.entries.get(key)
        if e and e.display:
            try: self.tts.speak(e.display)
            except Exception as ex: messagebox.showerror("TTS", str(ex))

    def set_status_selected(self, status: str):
        sel = self.tree.selection()
        if not sel: return
        key = sel[0]; e = self.entries.get(key)
        if not e: return
        e.status = status
        for off in e.offsets:
            self._clear_range_tags(off["start"], off["end"])
            self._tag_range(off["start"], off["end"], self._status_to_tag(status))
        self._refresh_tree_row(e)
        self._update_vietsub_highlights()
        self.after_idle(self._update_markers_all)

    def delete_selected_word(self):
        sel = self.tree.selection()
        if not sel: return
        key = sel[0]; entry = self.entries.pop(key, None)
        if entry:
            for off in entry.offsets:
                self._clear_range_tags(off["start"], off["end"])
            self._remove_tree_row_by_key(key)
            self._update_vietsub_highlights()
            self.after_idle(self._update_markers_all)

    # ---------- Scrolling ----------
    def _on_en_scroll(self, *args):
        if self.en_scrollbar:
            self.en_scrollbar.set(*args)
        self._schedule_update_markers()

    def _on_en_scrollbar(self, *args):
        self.text_en.yview(*args)
        self._schedule_update_markers()

    # ---------- Bubble markers ----------
    def _schedule_update_markers(self):
        self.after_idle(self._update_markers_all)

    def _clear_markers_en(self):
        for c in self._marker_en:
            try: c.destroy()
            except Exception: pass
        self._marker_en.clear()

    def _clear_markers_vi(self):
        for c in self._marker_vi:
            try: c.destroy()
            except Exception: pass
        self._marker_vi.clear()

    def _update_markers_all(self):
        self._update_markers_en()
        self._update_markers_vi()

    def _bubble_color(self, status: str) -> str:
        return {"new": "#ffd000", "proficient": "#32cd32", "review": "#ff8c00"}.get(status, "#ffd000")

    def _update_markers_en(self):
        # chỉ vẽ khi có nội dung
        full = self.text_en.get("1.0", "end-1c")
        self._clear_markers_en()
        if not full.strip():
            return

        # chỉ vẽ khi tab English đang mở (để đỡ tốn công)
        current = self.nb_left.nametowidget(self.nb_left.select())
        if current is not self.tab_en:
            return

        entries_sorted = self._entries_sorted_by_offset()
        bg_text = self.text_en.cget("bg")

        for i, e in enumerate(entries_sorted, start=1):
            if not e.offsets: continue
            start_abs = e.offsets[0]["start"]
            idx = self._abs_to_index(start_abs, full)
            bbox = self.text_en.bbox(idx)
            if not bbox:  # không nằm trong vùng nhìn thấy
                continue
            x, y, w, h = bbox

            r = max(10, min(12, h // 2 + 4))
            diam = 2 * r

            cx = max(2, x - r - 4)  # tâm x (lệch trái từ)
            cy = y + h / 2          # tâm y
            left = cx - r
            top = cy - r

            c = tk.Canvas(self.text_en, width=diam, height=diam,
                          highlightthickness=0, bd=0, bg=bg_text)
            c.place(x=left, y=top)
            fill = self._bubble_color(e.status)
            c.create_oval(0, 0, diam, diam, fill=fill, outline="")
            c.create_text(r, r, text=str(i), fill="#000",
                          font=("Segoe UI", max(8, self.font_size - 6), "bold"))
            c.bind("<Button-1>", lambda ev: self.text_en.focus_set())
            self._marker_en.append(c)

    def _update_markers_vi(self):
        # vẽ số tại VỊ TRÍ KHỚP NGHĨA_VI đầu tiên trong bản dịch
        full = self.text_vi.get("1.0", "end-1c")
        self._clear_markers_vi()
        if not full.strip():
            return

        current = self.nb_left.nametowidget(self.nb_left.select())
        if current is not self.tab_vi:
            # vẫn cho phép hiển thị cả khi đang ở English? -> thôi, chỉ vẽ khi tab Viet-sub mở để nhẹ
            return

        entries_sorted = self._entries_sorted_by_offset()
        bg_text = self.text_vi.cget("bg")

        for i, e in enumerate(entries_sorted, start=1):
            needle = (e.vi_meaning or "").strip()
            if not needle:
                continue
            idx = self.text_vi.search(needle, "1.0", stopindex="end", nocase=True)
            if not idx:
                continue
            bbox = self.text_vi.bbox(idx)
            if not bbox:
                continue
            x, y, w, h = bbox

            r = max(10, min(12, h // 2 + 4))
            diam = 2 * r
            cx = max(2, x - r - 4)
            cy = y + h / 2
            left = cx - r
            top = cy - r

            c = tk.Canvas(self.text_vi, width=diam, height=diam,
                          highlightthickness=0, bd=0, bg=bg_text)
            c.place(x=left, y=top)
            fill = self._bubble_color(e.status)
            c.create_oval(0, 0, diam, diam, fill=fill, outline="")
            c.create_text(r, r, text=str(i), fill="#000",
                          font=("Segoe UI", max(8, self.font_size - 6), "bold"))
            c.bind("<Button-1>", lambda ev: self.text_vi.focus_set())
            self._marker_vi.append(c)

# ---------------- Main ----------------
if __name__ == "__main__":
    try: _ = sent_tokenize("Test.")
    except LookupError: nltk.download("punkt")
    app = VocabReaderApp()
    app.mainloop()
