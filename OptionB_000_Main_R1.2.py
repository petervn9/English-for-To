import os
import json
import time
import threading
from dataclasses import dataclass, asdict, field
from typing import Dict, List, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter import font as tkfont

import nltk
from nltk.tokenize import sent_tokenize, word_tokenize
from nltk.stem import WordNetLemmatizer
import pygame

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
    "reading": "#ffd000",
}

TEXT_FG = "#222222"
TEXT_BG = "#ffffff"
SELECT_BG = "#5dade2"
TRIM_CHARS = set(" \t\r\n.,!?;:\"'()[]{}<>…“”‘’`-")

CACHE_DIR = os.path.join(os.getcwd(), "cache", "audio")
os.makedirs(CACHE_DIR, exist_ok=True)


def current_iso() -> str:
    import datetime as dt
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class WordEntry:
    display: str
    pos: str
    ipa: str
    vi_meaning: str
    gloss_en: str
    context_sentence: str
    offsets: List[Dict] = field(default_factory=list)
    added_at: str = ""
    surface: str = ""
    vi_index: str = ""


class VocabReaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x700")
        self.minsize(1000, 600)
        self.font_size = DEFAULT_FONT_SIZE
        self.text_path = None
        self.text_content = ""
        self.sentences_cache: List[Tuple[int, int]] = []
        self.entries: Dict[str, WordEntry] = {}
        self.llm_cache: Dict[str, Dict] = {}
        self.tts = api.TTSManager(cache_dir=CACHE_DIR, lang="en", tld="com")
        self._reading_thread = None
        self._reading_stop = threading.Event()
        self._reading_pause = threading.Event()
        self._reading_mode = None
        self.marker_en_widgets: Dict[str, Dict] = {}
        self.marker_vi_widgets: Dict[str, Dict] = {}
        self.entry_marks_en: Dict[str, Dict[str, str]] = {}
        self.lemmatizer = WordNetLemmatizer()
        self._build_ui()
        self._bind_keys()
        self._apply_theme()

    def _build_ui(self):
        self.style = ttk.Style(self)
        self._configure_tree_style()
        self._build_menubar()
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x")
        ttk.Button(toolbar, text="Open .txt", command=self.action_open_txt).pack(side="left", padx=4, pady=4)
        ttk.Button(toolbar, text="Save Session (JSON)", command=self.action_save_session).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Load Session (JSON)", command=self.action_load_session).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Export TXT", command=self.action_export_txt).pack(side="left", padx=4)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(toolbar, text="Read Paragraph", command=lambda: self.start_reading("paragraph")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Read Sentence", command=lambda: self.start_reading("sentence")).pack(side="left", padx=4)
        ttk.Button(toolbar, text="Read Word", command=lambda: self.start_reading("word")).pack(side="left", padx=4)
        self.btn_pause = ttk.Button(toolbar, text="Pause", command=self.toggle_pause, state="disabled")
        self.btn_pause.pack(side="left", padx=4)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Label(toolbar, text="Font:").pack(side="left", padx=(12, 2))
        self.font_slider = ttk.Scale(toolbar, from_=MIN_FONT, to=MAX_FONT, value=self.font_size, command=self.on_change_font)
        self.font_slider.pack(side="left", padx=4)
        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True)
        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        self.nb_left = ttk.Notebook(left)
        self.nb_left.pack(fill="both", expand=True)
        self.tab_en = ttk.Frame(self.nb_left)
        self.nb_left.add(self.tab_en, text="English")
        en_wrap = ttk.Frame(self.tab_en)
        en_wrap.pack(fill="both", expand=True)
        self.text_en = tk.Text(en_wrap, wrap="word", undo=True, font=("Segoe UI", self.font_size))
        self.text_en.pack(side="left", fill="both", expand=True)
        self.text_en.config(selectbackground="#5dade2", selectforeground="#000000")
        self.en_scrollbar = ttk.Scrollbar(en_wrap, orient="vertical", command=self.text_en.yview)
        self.en_scrollbar.pack(side="right", fill="y")
        self.text_en.configure(yscrollcommand=self.en_scrollbar.set)
        for tag, color in HIGHLIGHT_COLORS.items():
            self.text_en.tag_configure(tag, background=color)
        self.tab_vi = ttk.Frame(self.nb_left)
        self.nb_left.add(self.tab_vi, text="Viet-sub")
        vi_wrap = ttk.Frame(self.tab_vi)
        vi_wrap.pack(fill="both", expand=True)
        self.text_vi = tk.Text(vi_wrap, wrap="word", font=("Segoe UI", self.font_size))
        self.text_vi.pack(side="left", fill="both", expand=True)
        self.text_vi.config(selectbackground="#5dade2", selectforeground="#000000")
        vi_scroll = ttk.Scrollbar(vi_wrap, orient="vertical", command=self.text_vi.yview)
        vi_scroll.pack(side="right", fill="y")
        self.text_vi.configure(yscrollcommand=vi_scroll.set)
        for tag, color in HIGHLIGHT_COLORS.items():
            self.text_vi.tag_configure(tag, background=color)
        self.cm = tk.Menu(self, tearoff=0)
        self.cm.add_command(label="Đánh dấu từ mới (Alt+D)", command=self.mark_new_word)
        self.cm.add_command(label="Phát âm", command=self.speak_selection)
        self.cm.add_separator()
        self.text_en.bind("<Button-3>", self._show_context_menu)
        self.nb_left.bind("<<NotebookTabChanged>>", self._on_left_tab_changed)
        right = ttk.Frame(paned)
        paned.add(right, weight=2)
        self.nb_right = ttk.Notebook(right)
        self.nb_right.pack(fill="both", expand=True)
        self.tab_dict = ttk.Frame(self.nb_right)
        self.nb_right.add(self.tab_dict, text="Từ điển cá nhân")
        cols = ("No.", "Word", "POS", "Meaning (VI)")
        self.tree = ttk.Treeview(self.tab_dict, columns=cols, show="headings")
        for col in cols:
            self.tree.heading(col, text=col)
        self.tree.column("No.", width=60, anchor="center")
        self.tree.column("Word", width=220, anchor="w")
        self.tree.column("POS", width=120, anchor="w")
        self.tree.column("Meaning (VI)", width=520, anchor="w")
        self.tree.pack(fill="both", expand=True)
        dict_toolbar = ttk.Frame(self.tab_dict)
        dict_toolbar.pack(fill="x")
        ttk.Button(dict_toolbar, text="Phát âm", command=self.speak_selected_word).pack(side="left", padx=4, pady=4)
        ttk.Button(dict_toolbar, text="Xoá dòng", command=self.delete_selected_word).pack(side="left", padx=4)
        ttk.Button(dict_toolbar, text="Export TXT", command=self.action_export_txt).pack(side="left", padx=4)
        self.text = self.text_en

    def _build_menubar(self):
        menu_root = tk.Menu(self)
        file_menu = tk.Menu(menu_root, tearoff=0)
        file_menu.add_command(label="Open .txt", command=self.action_open_txt, accelerator="Ctrl+O")
        file_menu.add_command(label="Save Session (JSON)", command=self.action_save_session, accelerator="Ctrl+S")
        file_menu.add_command(label="Load Session (JSON)", command=self.action_load_session)
        file_menu.add_separator()
        file_menu.add_command(label="Export TXT", command=self.action_export_txt, accelerator="Ctrl+E")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu_root.add_cascade(label="File", menu=file_menu)
        tools_menu = tk.Menu(menu_root, tearoff=0)
        tools_menu.add_command(label="Read Paragraph", command=lambda: self.start_reading("paragraph"), accelerator="Ctrl+P")
        tools_menu.add_command(label="Read Sentence", command=lambda: self.start_reading("sentence"), accelerator="Ctrl+Shift+S")
        tools_menu.add_command(label="Read Word", command=lambda: self.start_reading("word"), accelerator="Ctrl+W")
        tools_menu.add_command(label="Pause/Resume", command=self.toggle_pause, accelerator="Space")
        menu_root.add_cascade(label="Tools", menu=tools_menu)
        help_menu = tk.Menu(menu_root, tearoff=0)
        help_menu.add_command(label="About", command=lambda: messagebox.showinfo("About", APP_TITLE))
        menu_root.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu_root)

    def _bind_keys(self):
        self.bind("<Alt-d>", lambda _: self.mark_new_word())
        self.bind("<Control-o>", lambda _: self.action_open_txt())
        self.bind("<Control-s>", lambda _: self.action_save_session())
        self.bind("<Control-e>", lambda _: self.action_export_txt())
        self.bind("<Control-p>", lambda _: self.start_reading("paragraph"))
        self.bind("<Control-Shift-S>", lambda _: self.start_reading("sentence"))
        self.bind("<Control-w>", lambda _: self.start_reading("word"))
        self.bind("<space>", lambda _: self.toggle_pause())

    def _apply_theme(self):
        for widget in (self.text_en, self.text_vi):
            widget.config(
                bg=TEXT_BG,
                fg=TEXT_FG,
                insertbackground=TEXT_FG,
                selectbackground=SELECT_BG,
                selectforeground="#000000",
            )
        self._refresh_number_widgets()

    def _configure_tree_style(self):
        if not hasattr(self, "style"):
            self.style = ttk.Style(self)
        body_font = ("Segoe UI", self.font_size)
        heading_font = ("Segoe UI", max(self.font_size - 1, 12), "bold")
        row_height = max(28, int(self.font_size * 1.6))
        self.style.configure("Treeview", font=body_font, rowheight=row_height)
        self.style.configure("Treeview.Heading", font=heading_font)

    def _refresh_number_widgets(self):
        bundles = list(self.marker_en_widgets.values()) + list(self.marker_vi_widgets.values())
        for bundle in bundles:
            widget = bundle["widget"]
            font = tkfont.Font(font=widget["font"])
            line_height = font.metrics("linespace")
            height = line_height
            width = max(14, int(line_height * 0.55))
            frame = bundle["frame"]
            canvas = bundle["canvas"]
            frame.config(width=width, height=height, bg=HIGHLIGHT_COLORS["word_new"])
            frame.pack_propagate(False)
            canvas.config(width=width, height=height, bg=HIGHLIGHT_COLORS["word_new"], highlightthickness=0, bd=0)
            canvas.coords(bundle["text_item"], 2, 2)
            size = max(8, int(self.font_size / 3))
            canvas.itemconfig(bundle["text_item"], font=("Segoe UI", size), fill="#000000")
            canvas.bind("<Button-1>", lambda _event, target=widget: target.focus_set())

    def action_open_txt(self):
        path = filedialog.askopenfilename(filetypes=[("UTF-8 Text", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
        self.text_path = path
        self.text_content = raw
        self._render_text_en(raw)
        self._build_sentence_offsets(raw)
        self.text_en.tag_remove("word_new", "1.0", "end")
        self.text_vi.tag_remove("word_new", "1.0", "end")
        self._clear_number_widgets()
        self._clear_entry_marks()
        self.entries.clear()
        self.llm_cache.clear()
        self.tree.delete(*self.tree.get_children())
        self.title(f"{APP_TITLE} – {os.path.basename(path)}")
        self.text_vi.delete("1.0", "end")

    def _render_text_en(self, content: str):
        self.text_en.configure(state="normal")
        self.text_en.delete("1.0", "end")
        self.text_en.insert("1.0", content)
        self.text_en.see("1.0")

    def _build_sentence_offsets(self, content: str):
        self.sentences_cache.clear()
        index = 0
        for sentence in sent_tokenize(content):
            start = content.find(sentence, index)
            if start == -1:
                start = index
            end = start + len(sentence)
            self.sentences_cache.append((start, end))
            index = end

    def action_save_session(self):
        data = {
            "text_path": self.text_path,
            "text_content": self.text_content,
            "created_at": current_iso(),
            "entries": [asdict(entry) for entry in self.entries.values()],
            "font_size": self.font_size,
        }
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        messagebox.showinfo("Saved", "Đã lưu phiên học.")

    def action_load_session(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        self.text_content = data.get("text_content", "")
        self._render_text_en(self.text_content)
        self._build_sentence_offsets(self.text_content)
        self.text_en.tag_remove("word_new", "1.0", "end")
        self.text_vi.tag_remove("word_new", "1.0", "end")
        self._clear_number_widgets()
        self._clear_entry_marks()
        self.font_size = data.get("font_size", DEFAULT_FONT_SIZE)
        self.font_slider.set(self.font_size)
        self.text_en.config(font=("Segoe UI", self.font_size))
        self.text_vi.config(font=("Segoe UI", self.font_size))
        self._configure_tree_style()
        self._apply_theme()
        self.entries.clear()
        self.tree.delete(*self.tree.get_children())
        self.marker_en_widgets.clear()
        self.marker_vi_widgets.clear()
        self.entry_marks_en.clear()
        for entry_data in data.get("entries", []):
            offsets = entry_data.get("offsets") or []
            converted: List[Dict] = []
            for item in offsets:
                if isinstance(item, dict) and "abs_start" in item:
                    converted.append(item)
                elif isinstance(item, dict) and "start" in item:
                    converted.append({"abs_start": item["start"], "abs_end": item.get("end", item["start"])})
            entry_data["offsets"] = converted
            if "surface" not in entry_data:
                entry_data["surface"] = ""
            entry = WordEntry(**entry_data)
            key = self._entry_key(entry.display, entry.context_sentence)
            self.entries[key] = entry
        self._refresh_tree_sorted()
        self._reapply_highlights_en()
        self.text_vi.delete("1.0", "end")

    def action_export_txt(self):
        if not self.entries:
            messagebox.showwarning("Export", "Chưa có từ để export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("word\tpos\tmeaning_vi\n")
            for entry in self._entries_sorted_by_offset():
                vi = (entry.vi_meaning or "").replace("\n", " ").replace("\t", " ")
                handle.write(f"{entry.display}\t{entry.pos}\t{vi}\n")
        messagebox.showinfo("Export", "Đã export TXT (UTF-8) với 3 cột.")

    def _show_context_menu(self, event):
        try:
            self.cm.tk_popup(event.x_root, event.y_root)
        finally:
            self.cm.grab_release()

    def mark_new_word(self):
        try:
            start_index = self.text_en.index("sel.first")
            end_index = self.text_en.index("sel.last")
        except tk.TclError:
            messagebox.showwarning("Đánh dấu", "Hãy bôi đen 1 từ/cụm từ trên tab English.")
            return
        trimmed_start = self._trim_left(start_index, end_index, self.text_en)
        trimmed_end = self._trim_right(trimmed_start, end_index, self.text_en)
        if self.text_en.compare(trimmed_start, ">=", trimmed_end):
            return
        selection = self.text_en.get(trimmed_start, trimmed_end)
        if not selection.strip():
            return
        full_text = self.text_en.get("1.0", "end-1c")
        abs_start = self._index_to_abs_pos(trimmed_start, full_text)
        abs_end = self._index_to_abs_pos(trimmed_end, full_text)
        paragraph = self._find_paragraph(full_text, abs_start, abs_end)
        word_info = self._fetch_word_info(selection, paragraph)
        entry_key = self._entry_key(word_info["lemma"], paragraph)
        entry = WordEntry(
            display=word_info["lemma"],
            pos=word_info["pos"],
            ipa=word_info["ipa"],
            vi_meaning=word_info["meaning"],
            gloss_en=word_info["gloss"],
            context_sentence=paragraph,
            offsets=[{"abs_start": abs_start, "abs_end": abs_end}],
            added_at=current_iso(),
            surface=selection,
        )
        self.entries[entry_key] = entry
        self._apply_entry_highlight(entry_key, entry)
        self._refresh_tree_sorted()
        if self.text_vi.get("1.0", "end-1c").strip():
            self._update_vietsub_highlights()
        else:
            self.translate_full_text()
        self._update_number_labels()
        try:
            self.tts.speak(selection)
        except Exception as exc:
            messagebox.showerror("TTS", str(exc))

    def speak_selection(self):
        try:
            snippet = self.text_en.get("sel.first", "sel.last").strip()
        except tk.TclError:
            idx = self.text_en.index("insert wordstart")
            snippet = self.text_en.get(idx, "insert wordend").strip()
        if snippet:
            try:
                self.tts.speak(snippet)
            except Exception as exc:
                messagebox.showerror("TTS", str(exc))

    def start_reading(self, mode: str):
        if self._reading_thread and self._reading_thread.is_alive():
            messagebox.showinfo("Reading", "Đang đọc. Hãy Pause/Resume hoặc chờ xong.")
            return
        self._reading_mode = mode
        self._reading_stop.clear()
        self._reading_pause.clear()
        self.btn_pause.config(state="normal", text="Pause")
        self._reading_thread = threading.Thread(target=self._reading_worker, daemon=True)
        self._reading_thread.start()

    def _reading_worker(self):
        full_text = self.text_en.get("1.0", "end-1c")
        try:
            if self._reading_mode == "paragraph":
                paragraphs = [p.strip() for p in full_text.split("\n\n") if p.strip()]
                for paragraph in paragraphs:
                    self._highlight_sentence_once(full_text, paragraph)
                    self.tts.speak(paragraph)
                    self._wait_audio_or_pause()
                    self._clear_reading_highlight()
            elif self._reading_mode == "sentence":
                sentence = self._get_current_sentence(full_text)
                if sentence:
                    self._highlight_sentence_once(full_text, sentence)
                    self.tts.speak(sentence)
                    self._wait_audio_or_pause()
                    self._clear_reading_highlight()
            elif self._reading_mode == "word":
                try:
                    snippet = self.text_en.get("sel.first", "sel.last").strip()
                except tk.TclError:
                    idx = self.text_en.index("insert wordstart")
                    snippet = self.text_en.get(idx, "insert wordend").strip()
                if snippet:
                    try:
                        start = self.text_en.index("sel.first")
                        end = self.text_en.index("sel.last")
                    except tk.TclError:
                        start = self.text_en.index("insert wordstart")
                        end = self.text_en.index("insert wordend")
                    self.text_en.tag_add("reading", start, end)
                    self.tts.speak(snippet)
                    self._wait_audio_or_pause()
                    self._clear_reading_highlight()
        finally:
            self.btn_pause.config(state="disabled", text="Pause")

    def _wait_audio_or_pause(self):
        while pygame.mixer.get_busy():
            if self._reading_stop.is_set():
                pygame.mixer.stop()
                break
            if self._reading_pause.is_set():
                time.sleep(0.1)
                continue
            time.sleep(0.05)

    def _highlight_sentence_once(self, full_text: str, segment: str):
        start = full_text.find(segment)
        if start == -1:
            return
        end = start + len(segment)
        start_index = self._abs_to_index(start, full_text)
        end_index = self._abs_to_index(end, full_text)
        self.text_en.tag_add("reading", start_index, end_index)

    def _clear_reading_highlight(self):
        self.text_en.tag_remove("reading", "1.0", "end")

    def toggle_pause(self):
        if not (self._reading_thread and self._reading_thread.is_alive()):
            return
        if not self._reading_pause.is_set():
            self._reading_pause.set()
            self.btn_pause.config(text="Resume")
        else:
            self._reading_pause.clear()
            self.btn_pause.config(text="Pause")

    def on_change_font(self, value):
        self.font_size = max(MIN_FONT, min(MAX_FONT, int(float(value))))
        self.text_en.config(font=("Segoe UI", self.font_size))
        self.text_vi.config(font=("Segoe UI", self.font_size))
        self._configure_tree_style()
        self._refresh_number_widgets()

    def _find_paragraph(self, full_text: str, start: int, end: int) -> str:
        left = full_text.rfind("\n\n", 0, start)
        right = full_text.find("\n\n", end)
        para_start = 0 if left == -1 else left + 2
        para_end = len(full_text) if right == -1 else right
        return full_text[para_start:para_end].strip()

    def _trim_left(self, start: str, end: str, widget: tk.Text) -> str:
        current = start
        while widget.compare(current, "<", end):
            char = widget.get(current)
            if char not in TRIM_CHARS:
                break
            current = widget.index(f"{current}+1c")
        return current

    def _trim_right(self, start: str, end: str, widget: tk.Text) -> str:
        current = end
        while widget.compare(start, "<", current):
            prev = widget.index(f"{current}-1c")
            char = widget.get(prev)
            if char not in TRIM_CHARS:
                break
            current = prev
        return current

    def _pos_from_tagger(self, selection: str, paragraph: str) -> str:
        tokens_selection: List[str] = []
        try:
            tokens_selection = [t for t in word_tokenize(selection) if t.strip()]
        except LookupError:
            ensure_nltk_resources()
            tokens_selection = [t for t in word_tokenize(selection) if t.strip()]
        lowered_selection = [t.lower() for t in tokens_selection if any(ch.isalpha() for ch in t)]
        tokens_paragraph: List[Tuple[str, str]] = []
        if paragraph.strip():
            try:
                para_tokens = word_tokenize(paragraph)
            except LookupError:
                ensure_nltk_resources()
                para_tokens = word_tokenize(paragraph)
            try:
                tokens_paragraph = nltk.pos_tag(para_tokens)
            except LookupError:
                ensure_nltk_resources()
                tokens_paragraph = nltk.pos_tag(para_tokens)
        if lowered_selection and tokens_paragraph:
            first = lowered_selection[0]
            length = len(lowered_selection)
            for index, (token, tag) in enumerate(tokens_paragraph):
                if token.lower() != first:
                    continue
                match = True
                for offset in range(1, length):
                    if index + offset >= len(tokens_paragraph):
                        match = False
                        break
                    if tokens_paragraph[index + offset][0].lower() != lowered_selection[offset]:
                        match = False
                        break
                if match:
                    return tag.lower()
        if lowered_selection:
            try:
                tagged = nltk.pos_tag([tok for tok in tokens_selection if any(ch.isalpha() for ch in tok)])
            except LookupError:
                ensure_nltk_resources()
                tagged = nltk.pos_tag([tok for tok in tokens_selection if any(ch.isalpha() for ch in tok)])
            if tagged:
                return tagged[0][1].lower()
        if tokens_paragraph:
            return tokens_paragraph[0][1].lower()
        return ""

    def _fetch_word_info(self, selection: str, paragraph: str) -> Dict[str, str]:
        cache_key = f"{selection.lower()}|{abs(hash(paragraph))}"
        if cache_key in self.llm_cache:
            return self.llm_cache[cache_key]
        lookup = api.lookup_dictionaryapi(selection)
        ipa = lookup.get("ipa", "")
        pos_guess = lookup.get("pos", "")
        defs = lookup.get("defs") or []
        tag_pos = self._pos_from_tagger(selection, paragraph)
        pos_source = tag_pos or pos_guess
        lemma = self._lemmatize(selection, pos_source)
        vi_meaning = self._build_vi_meaning(selection, lemma, paragraph, defs)
        info = {
            "lemma": lemma,
            "pos": self._normalize_pos(pos_source),
            "ipa": ipa,
            "meaning": vi_meaning,
            "gloss": defs[0] if defs else "",
        }
        self.llm_cache[cache_key] = info
        return info

    def _normalize_pos(self, pos_value: str) -> str:
        value = (pos_value or "").lower()
        if value.startswith("v"):
            return "verb"
        if value.startswith("n"):
            return "noun"
        if value.startswith("adj") or value.startswith("j"):
            return "adjective"
        if value.startswith("adv") or value.startswith("r"):
            return "adverb"
        return value or "other"

    def _lemmatize(self, token: str, pos_hint: str) -> str:
        base = token.strip().lower()
        pos = "n"
        hint = (pos_hint or "").lower()
        if hint.startswith("v"):
            pos = "v"
        elif hint.startswith("adj"):
            pos = "a"
        elif hint.startswith("adv"):
            pos = "r"
        lemma = self.lemmatizer.lemmatize(base, pos=pos)
        if lemma.endswith("'s"):
            lemma = lemma[:-2]
        return lemma

    def _build_vi_meaning(self, selection: str, lemma: str, paragraph: str, defs: List[str]) -> str:
        prompt = (
            "You translate vocabulary for learners. Translate the isolated English word or phrase exactly as given into "
            "natural Vietnamese. Use the paragraph only to determine the appropriate sense. Always output a concise "
            "translation of one to three Vietnamese words in base form. Do not include adjectives that are not part of the "
            "highlighted term. Example: if the word is 'houses' in 'Stilt houses are popular', the answer must be 'nhà'."
        )
        user_content = (
            f"Word in text: {selection}\n"
            f"Lemma: {lemma}\n"
            f"Paragraph: {paragraph}\n"
            "Return only the Vietnamese translation."
        )
        try:
            vi = api._openai_chat(
                [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.2,
            ).strip()
        except Exception as exc:
            if "insufficient_quota" in str(exc).lower():
                vi = ""
            else:
                raise
        if vi:
            return vi.splitlines()[0].strip()
        if defs:
            return defs[0].split(";")[0].strip()
        return lemma

    def speak_selected_word(self):
        selection = self.tree.selection()
        if not selection:
            return
        key = selection[0]
        entry = self.entries.get(key)
        if entry:
            text = entry.surface or entry.display
            try:
                self.tts.speak(text)
            except Exception as exc:
                messagebox.showerror("TTS", str(exc))

    def delete_selected_word(self):
        selection = self.tree.selection()
        if not selection:
            return
        key = selection[0]
        entry = self.entries.pop(key, None)
        if not entry:
            return
        self._remove_entry_highlight(key, entry)
        self.tree.delete(key)
        self._update_vietsub_highlights()
        self._update_number_labels()

    def _entries_sorted_by_offset(self) -> List[WordEntry]:
        def key_fn(entry: WordEntry) -> Tuple[int, int]:
            if entry.offsets:
                info = entry.offsets[0]
                return info.get("abs_start", 10**9), info.get("abs_end", 10**9)
            return 10**9, 10**9
        return sorted(self.entries.values(), key=key_fn)

    def _refresh_tree_sorted(self):
        self.tree.delete(*self.tree.get_children())
        for index, entry in enumerate(self._entries_sorted_by_offset(), start=1):
            key = self._entry_key(entry.display, entry.context_sentence)
            values = [index, entry.display, entry.pos, entry.vi_meaning]
            self.tree.insert("", "end", iid=key, values=values)

    def _apply_entry_highlight(self, key: str, entry: WordEntry):
        full_text = self.text_en.get("1.0", "end-1c")
        if not entry.offsets:
            return
        data = entry.offsets[0]
        start_index = self._abs_to_index(data["abs_start"], full_text)
        end_index = self._abs_to_index(data["abs_end"], full_text)
        surface = entry.surface or self.text_en.get(start_index, end_index)
        word_end = self.text_en.index(f"{start_index}+{len(surface)}c")
        self.text_en.tag_add("word_new", start_index, word_end)
        start_mark = f"start_{key}"
        end_mark = f"end_{key}"
        self.text_en.mark_set(start_mark, start_index)
        self.text_en.mark_set(end_mark, word_end)
        self.text_en.mark_gravity(start_mark, tk.LEFT)
        self.text_en.mark_gravity(end_mark, tk.LEFT)
        self.entry_marks_en[key] = {"start": start_mark, "end": end_mark}
        mark = f"marker_en_{key}"
        self.text_en.mark_set(mark, start_index)
        self.text_en.mark_gravity(mark, tk.LEFT)
        bundle = self._create_number_widget(self.text_en)
        self.text_en.window_create(mark, window=bundle["frame"])
        bundle["mark"] = mark
        self.marker_en_widgets[key] = bundle

    def _remove_entry_highlight(self, key: str, _entry: WordEntry):
        marks = self.entry_marks_en.pop(key, None)
        if marks:
            start_mark = marks["start"]
            end_mark = marks["end"]
            self.text_en.tag_remove("word_new", start_mark, end_mark)
            self.text_en.mark_unset(start_mark)
            self.text_en.mark_unset(end_mark)
        bundle = self.marker_en_widgets.pop(key, None)
        if bundle:
            mark = bundle.get("mark")
            try:
                if mark:
                    self.text_en.delete(mark)
                    self.text_en.mark_unset(mark)
            except tk.TclError:
                pass
            bundle["frame"].destroy()

    def _create_number_widget(self, widget: tk.Text) -> Dict[str, object]:
        frame = tk.Frame(widget, bg=HIGHLIGHT_COLORS["word_new"])
        canvas = tk.Canvas(frame, bg=HIGHLIGHT_COLORS["word_new"], highlightthickness=0, bd=0)
        canvas.pack(fill="both", expand=True)
        text_item = canvas.create_text(2, 2, anchor="nw", text="", fill="#000000")
        return {"widget": widget, "frame": frame, "canvas": canvas, "text_item": text_item}

    def _entry_key(self, word: str, sentence: str) -> str:
        return f"{word.lower()}|{abs(hash(sentence))}"

    def _reapply_highlights_en(self):
        self.text_en.tag_remove("word_new", "1.0", "end")
        for bundle in self.marker_en_widgets.values():
            mark = bundle.get("mark")
            if mark:
                try:
                    self.text_en.delete(mark)
                except tk.TclError:
                    pass
                self.text_en.mark_unset(mark)
            bundle["frame"].destroy()
        self.marker_en_widgets.clear()
        self.entry_marks_en.clear()
        for key in sorted(self.entries.keys(), key=lambda k: self.entries[k].offsets[0]["abs_start"] if self.entries[k].offsets else 10**9):
            self._apply_entry_highlight(key, self.entries[key])
        self._update_number_labels()

    def _update_number_labels(self):
        sorted_entries = self._entries_sorted_by_offset()
        order_map = {self._entry_key(entry.display, entry.context_sentence): index for index, entry in enumerate(sorted_entries, start=1)}
        for key, bundle in self.marker_en_widgets.items():
            number = order_map.get(key, "")
            bundle["canvas"].itemconfig(bundle["text_item"], text=str(number) if number else "")
        for key, bundle in self.marker_vi_widgets.items():
            number = order_map.get(key, "")
            bundle["canvas"].itemconfig(bundle["text_item"], text=str(number) if number else "")
        self._refresh_number_widgets()

    def _clear_number_widgets(self):
        for bundle in list(self.marker_en_widgets.values()):
            mark = bundle.get("mark")
            if mark:
                try:
                    self.text_en.delete(mark)
                except tk.TclError:
                    pass
                self.text_en.mark_unset(mark)
            bundle["frame"].destroy()
        self.marker_en_widgets.clear()
        for bundle in list(self.marker_vi_widgets.values()):
            mark = bundle.get("mark")
            if mark:
                try:
                    self.text_vi.delete(mark)
                except tk.TclError:
                    pass
                self.text_vi.mark_unset(mark)
            bundle["frame"].destroy()
        self.marker_vi_widgets.clear()

    def _clear_entry_marks(self):
        for marks in list(self.entry_marks_en.values()):
            start = marks.get("start")
            end = marks.get("end")
            if start:
                try:
                    self.text_en.mark_unset(start)
                except tk.TclError:
                    pass
            if end:
                try:
                    self.text_en.mark_unset(end)
                except tk.TclError:
                    pass
        self.entry_marks_en.clear()

    def _on_left_tab_changed(self, _event):
        tab = self.nb_left.nametowidget(self.nb_left.select())
        if tab is self.tab_vi:
            self.translate_full_text()

    def translate_full_text(self):
        english = self.text_en.get("1.0", "end-1c")
        if not english.strip():
            self.text_vi.delete("1.0", "end")
            self._clear_vietsub_state()
            return
        try:
            vietnamese = api._openai_chat(
                [
                    {
                        "role": "system",
                        "content": "You translate English passages into natural Vietnamese. Preserve paragraph breaks exactly.",
                    },
                    {"role": "user", "content": english},
                ],
                temperature=0.2,
            )
        except Exception as exc:
            if "insufficient_quota" in str(exc).lower():
                messagebox.showwarning("OpenAI", "Không thể dịch vì quota. Vui lòng kiểm tra API key.")
                return
            messagebox.showerror("Lỗi dịch", str(exc))
            return
        self.text_vi.delete("1.0", "end")
        self.text_vi.insert("1.0", vietnamese)
        self._update_vietsub_highlights()

    def _clear_vietsub_state(self):
        self.text_vi.tag_remove("word_new", "1.0", "end")
        for bundle in self.marker_vi_widgets.values():
            mark = bundle.get("mark")
            if mark:
                try:
                    self.text_vi.delete(mark)
                except tk.TclError:
                    pass
                self.text_vi.mark_unset(mark)
            bundle["frame"].destroy()
        self.marker_vi_widgets.clear()

    def _locate_vietsub_match(
        self,
        meaning: str,
        content: str,
        used_ranges: List[Tuple[int, int]],
    ):
        search_from = "1.0"
        while True:
            start = self.text_vi.search(meaning, search_from, stopindex="end", nocase=True)
            if not start:
                return None
            end = self.text_vi.index(f"{start}+{len(meaning)}c")
            abs_start = self._index_to_abs_pos(start, content)
            abs_end = self._index_to_abs_pos(end, content)
            overlap = any(not (abs_end <= used_start or abs_start >= used_end) for used_start, used_end in used_ranges)
            if overlap:
                search_from = end
                continue
            used_ranges.append((abs_start, abs_end))
            return start, end, self.text_vi.get(start, end)

    def _update_vietsub_highlights(self):
        self._clear_vietsub_state()
        content = self.text_vi.get("1.0", "end-1c")
        if not content.strip():
            return
        sorted_entries = self._entries_sorted_by_offset()
        used_ranges: List[Tuple[int, int]] = []
        updated_any = False
        for entry in sorted_entries:
            key = self._entry_key(entry.display, entry.context_sentence)
            meaning = (entry.vi_meaning or "").strip()
            if not meaning:
                entry.vi_index = ""
                continue
            match = self._locate_vietsub_match(meaning, content, used_ranges)
            if not match:
                entry.vi_index = ""
                continue
            start, end, matched_text = match
            self.text_vi.tag_add("word_new", start, end)
            mark = f"marker_vi_{key}"
            self.text_vi.mark_set(mark, start)
            self.text_vi.mark_gravity(mark, tk.LEFT)
            bundle = self._create_number_widget(self.text_vi)
            self.text_vi.window_create(mark, window=bundle["frame"])
            bundle["mark"] = mark
            self.marker_vi_widgets[key] = bundle
            entry.vi_index = start
            cleaned_match = matched_text.strip()
            if cleaned_match and cleaned_match != entry.vi_meaning:
                entry.vi_meaning = cleaned_match
                updated_any = True
        if updated_any:
            self._refresh_tree_sorted()
        self._update_number_labels()

    def _get_current_sentence(self, full_text: str):
        try:
            idx = self.text_en.index("insert")
        except tk.TclError:
            return None
        abs_pos = self._index_to_abs_pos(idx, full_text)
        for start, end in self.sentences_cache:
            if start <= abs_pos <= end:
                return full_text[start:end]
        return None

    def _index_to_abs_pos(self, tkindex: str, full_text: str) -> int:
        line, col = map(int, tkindex.split("."))
        lines = full_text.split("\n")
        return sum(len(line_text) + 1 for line_text in lines[: line - 1]) + col

    def _abs_to_index(self, abspos: int, full_text: str) -> str:
        lines = full_text.split("\n")
        acc = 0
        for line_no, line_text in enumerate(lines, start=1):
            if acc + len(line_text) >= abspos:
                return f"{line_no}.{abspos - acc}"
            acc += len(line_text) + 1
        last_line = len(lines)
        last_col = len(lines[-1]) if lines else 0
        return f"{last_line}.{last_col}"


def ensure_nltk_resources():
    try:
        sent_tokenize("Test.")
    except LookupError:
        nltk.download("punkt")
    try:
        nltk.data.find("corpora/wordnet")
    except LookupError:
        nltk.download("wordnet")
        nltk.download("omw-1.4")
    try:
        nltk.data.find("taggers/averaged_perceptron_tagger")
    except LookupError:
        nltk.download("averaged_perceptron_tagger")
    try:
        nltk.data.find("taggers/averaged_perceptron_tagger_eng")
    except LookupError:
        nltk.download("averaged_perceptron_tagger_eng")


if __name__ == "__main__":
    ensure_nltk_resources()
    app = VocabReaderApp()
    app.mainloop()
