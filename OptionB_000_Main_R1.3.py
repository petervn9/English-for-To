import os
import json
import time
import threading
from dataclasses import dataclass, asdict
from typing import Dict, List, Tuple, Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import nltk
from nltk.tokenize import sent_tokenize
import pygame

import importlib.util

API_PATH = os.path.join(os.path.dirname(__file__), "OptionC_api_module.py")
_spec = importlib.util.spec_from_file_location("api_module", API_PATH)
api = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(api)

APP_TITLE = "Vocabulary Reader – Context Aware"
DEFAULT_FONT_SIZE = 18
MIN_FONT = 12
MAX_FONT = 36
HIGHLIGHT_COLOR = "#fff7ad"
CACHE_DIR = os.path.join(os.getcwd(), "cache", "audio")
os.makedirs(CACHE_DIR, exist_ok=True)
TRIM_CHARS = "\u201c\u201d\u2018\u2019'\".,!?;:()[]{}<>\u2026"

@dataclass
class WordEntry:
    display: str
    pos: str
    ipa: str
    vi_meaning: str
    gloss_en: str
    context_sentence: str
    offsets: List[Dict]
    added_at: str

class VocabReaderApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1200x700")
        self.minsize(1000, 600)
        self.font_size = DEFAULT_FONT_SIZE
        self.text_path: Optional[str] = None
        self.text_content = ""
        self.sentences_cache: List[Tuple[int, int]] = []
        self.entries: Dict[str, WordEntry] = {}
        self.llm_cache: Dict[str, Dict] = {}
        self.tts = api.TTSManager(cache_dir=CACHE_DIR, lang="en", tld="com")
        self._reading_thread: Optional[threading.Thread] = None
        self._reading_stop = threading.Event()
        self._reading_pause = threading.Event()
        self._reading_mode: Optional[str] = None
        self.en_mark_tags: Dict[str, str] = {}
        self.vi_mark_tags: Dict[str, str] = {}
        self.en_windows: Dict[str, tk.Widget] = {}
        self.vi_windows: Dict[str, tk.Widget] = {}
        self._build_ui()
        self._bind_keys()

    def _build_ui(self) -> None:
        style = ttk.Style(self)
        style.configure("Treeview", font=("Segoe UI", 14))
        style.configure("Treeview.Heading", font=("Segoe UI", 15, "bold"))
        tb = ttk.Frame(self)
        tb.pack(side="top", fill="x")
        ttk.Button(tb, text="Open .txt", command=self.action_open_txt).pack(side="left", padx=4, pady=4)
        ttk.Button(tb, text="Save Session (JSON)", command=self.action_save_session).pack(side="left", padx=4)
        ttk.Button(tb, text="Load Session (JSON)", command=self.action_load_session).pack(side="left", padx=4)
        ttk.Button(tb, text="Export TXT", command=self.action_export_txt).pack(side="left", padx=4)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(tb, text="Read Paragraph", command=lambda: self.start_reading("paragraph")).pack(side="left", padx=4)
        ttk.Button(tb, text="Read Sentence", command=lambda: self.start_reading("sentence")).pack(side="left", padx=4)
        ttk.Button(tb, text="Read Word", command=lambda: self.start_reading("word")).pack(side="left", padx=4)
        self.btn_pause = ttk.Button(tb, text="Pause", command=self.toggle_pause, state="disabled")
        self.btn_pause.pack(side="left", padx=4)
        ttk.Separator(tb, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Label(tb, text="Font:").pack(side="left", padx=(12, 2))
        self.font_slider = ttk.Scale(tb, from_=MIN_FONT, to=MAX_FONT, value=self.font_size, command=self.on_change_font)
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
        self.text_en.tag_configure("word_new", background=HIGHLIGHT_COLOR)
        self.tab_vi = ttk.Frame(self.nb_left)
        self.nb_left.add(self.tab_vi, text="Viet-sub")
        vi_wrap = ttk.Frame(self.tab_vi)
        vi_wrap.pack(fill="both", expand=True)
        self.text_vi = tk.Text(vi_wrap, wrap="word", font=("Segoe UI", self.font_size), bg="#fafafa")
        self.text_vi.pack(side="left", fill="both", expand=True)
        self.text_vi.config(selectbackground="#5dade2", selectforeground="#000000")
        vi_scroll = ttk.Scrollbar(vi_wrap, orient="vertical", command=self.text_vi.yview)
        vi_scroll.pack(side="right", fill="y")
        self.text_vi.configure(yscrollcommand=vi_scroll.set)
        self.text_vi.tag_configure("word_new", background=HIGHLIGHT_COLOR)
        self.cm = tk.Menu(self, tearoff=0)
        self.cm.add_command(label="Đánh dấu từ mới (Alt+D)", command=self.mark_new_word)
        self.cm.add_command(label="Phát âm", command=self.speak_selection)
        self.text_en.bind("<Button-3>", self._show_context_menu)
        self.text_en.bind("<Configure>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_en.bind("<ButtonRelease-1>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_en.bind("<MouseWheel>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_en.bind("<Button-4>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_en.bind("<Button-5>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_vi.bind("<Configure>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_vi.bind("<ButtonRelease-1>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_vi.bind("<MouseWheel>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_vi.bind("<Button-4>", lambda _: self.after_idle(self._render_all_highlights))
        self.text_vi.bind("<Button-5>", lambda _: self.after_idle(self._render_all_highlights))
        self.nb_left.bind("<<NotebookTabChanged>>", self._on_left_tab_changed)
        right = ttk.Frame(paned)
        paned.add(right, weight=2)
        self.nb_right = ttk.Notebook(right)
        self.nb_right.pack(fill="both", expand=True)
        self.tab_dict = ttk.Frame(self.nb_right)
        self.nb_right.add(self.tab_dict, text="Từ điển cá nhân")
        cols = ("No.", "Word", "POS", "Meaning (VI)")
        self.tree = ttk.Treeview(self.tab_dict, columns=cols, show="headings")
        for c in cols:
            self.tree.heading(c, text=c)
        self.tree.column("No.", width=60, anchor="center")
        self.tree.column("Word", width=220, anchor="w")
        self.tree.column("POS", width=120, anchor="w")
        self.tree.column("Meaning (VI)", width=520, anchor="w")
        self.tree.pack(fill="both", expand=True)
        dict_tb = ttk.Frame(self.tab_dict)
        dict_tb.pack(fill="x")
        ttk.Button(dict_tb, text="Phát âm", command=self.speak_selected_word).pack(side="left", padx=4, pady=4)
        ttk.Button(dict_tb, text="Xoá dòng", command=self.delete_selected_word).pack(side="left", padx=4)
        ttk.Button(dict_tb, text="Export TXT", command=self.action_export_txt).pack(side="left", padx=4)
        self._build_menubar()

    def _build_menubar(self) -> None:
        m = tk.Menu(self)
        mf = tk.Menu(m, tearoff=0)
        mf.add_command(label="Open .txt", command=self.action_open_txt, accelerator="Ctrl+O")
        mf.add_command(label="Save Session (JSON)", command=self.action_save_session, accelerator="Ctrl+S")
        mf.add_command(label="Load Session (JSON)", command=self.action_load_session)
        mf.add_separator()
        mf.add_command(label="Export TXT", command=self.action_export_txt, accelerator="Ctrl+E")
        mf.add_separator()
        mf.add_command(label="Exit", command=self.destroy)
        m.add_cascade(label="File", menu=mf)
        mt = tk.Menu(m, tearoff=0)
        mt.add_command(label="Read Paragraph", command=lambda: self.start_reading("paragraph"), accelerator="Ctrl+P")
        mt.add_command(label="Read Sentence", command=lambda: self.start_reading("sentence"), accelerator="Ctrl+Shift+S")
        mt.add_command(label="Read Word", command=lambda: self.start_reading("word"), accelerator="Ctrl+W")
        mt.add_command(label="Pause/Resume", command=self.toggle_pause, accelerator="Space")
        m.add_cascade(label="Tools", menu=mt)
        mh = tk.Menu(m, tearoff=0)
        mh.add_command(label="About", command=lambda: messagebox.showinfo("About", APP_TITLE))
        m.add_cascade(label="Help", menu=mh)
        self.config(menu=m)

    def _bind_keys(self) -> None:
        self.bind("<Alt-d>", lambda _: self.mark_new_word())
        self.bind("<Control-o>", lambda _: self.action_open_txt())
        self.bind("<Control-s>", lambda _: self.action_save_session())
        self.bind("<Control-e>", lambda _: self.action_export_txt())
        self.bind("<Control-p>", lambda _: self.start_reading("paragraph"))
        self.bind("<Control-Shift-S>", lambda _: self.start_reading("sentence"))
        self.bind("<Control-w>", lambda _: self.start_reading("word"))
        self.bind("<space>", lambda _: self.toggle_pause())

    def _show_context_menu(self, event: tk.Event) -> None:
        try:
            self.cm.tk_popup(event.x_root, event.y_root)
        finally:
            self.cm.grab_release()

    def action_open_txt(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("UTF-8 Text", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            raw = f.read()
        self.text_path = path
        self.text_content = raw
        self._render_text_en(self.text_content)
        self._build_sentence_offsets(self.text_content)
        self.entries.clear()
        self.llm_cache.clear()
        self.en_mark_tags.clear()
        self.vi_mark_tags.clear()
        self._destroy_all_windows()
        self.tree.delete(*self.tree.get_children())
        self.title(f"{APP_TITLE} – {os.path.basename(path)}")
        self.text_vi.delete("1.0", "end")
        self.after_idle(self._render_all_highlights)

    def _render_text_en(self, content: str) -> None:
        self.text_en.configure(state="normal")
        self.text_en.delete("1.0", "end")
        self.text_en.insert("1.0", content)

    def _build_sentence_offsets(self, content: str) -> None:
        self.sentences_cache.clear()
        idx = 0
        for s in sent_tokenize(content):
            start = content.find(s, idx)
            if start == -1:
                start = idx
            end = start + len(s)
            self.sentences_cache.append((start, end))
            idx = end

    def action_save_session(self) -> None:
        data = {
            "text_path": self.text_path,
            "text_content": self.text_content,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "entries": [asdict(w) for w in self.entries.values()],
            "font_size": self.font_size,
        }
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        messagebox.showinfo("Saved", "Đã lưu phiên học.")

    def action_load_session(self) -> None:
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.text_content = data.get("text_content", "")
        self._render_text_en(self.text_content)
        self._build_sentence_offsets(self.text_content)
        self.font_size = data.get("font_size", DEFAULT_FONT_SIZE)
        self.font_slider.set(self.font_size)
        self.text_en.config(font=("Segoe UI", self.font_size))
        self.text_vi.config(font=("Segoe UI", self.font_size))
        self.entries.clear()
        self.llm_cache.clear()
        self.en_mark_tags.clear()
        self.vi_mark_tags.clear()
        self._destroy_all_windows()
        self.tree.delete(*self.tree.get_children())
        for w in data.get("entries", []):
            entry = self._coerce_entry(w)
            if entry:
                self.entries[self._entry_key(entry.display, entry.context_sentence)] = entry
        self._refresh_tree_sorted()
        self.after_idle(self._render_all_highlights)

    def action_export_txt(self) -> None:
        if not self.entries:
            messagebox.showwarning("Export", "Chưa có từ để export.")
            return
        path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text", "*.txt")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write("word\tpos\tmeaning_vi\n")
            for e in self._entries_sorted_by_offset():
                mvi = (e.vi_meaning or "").replace("\n", " ").replace("\t", "  ")
                f.write(f"{e.display}\t{e.pos}\t{mvi}\n")
        messagebox.showinfo("Export", "Đã export TXT (UTF-8) với 3 cột.")

    def mark_new_word(self) -> None:
        try:
            start = self.text_en.index("sel.first")
            end = self.text_en.index("sel.last")
        except tk.TclError:
            messagebox.showwarning("Đánh dấu", "Hãy bôi đen 1 từ hoặc cụm từ trên tab English.")
            return
        full = self.text_en.get("1.0", "end-1c")
        abs_start = self._index_to_abs_pos(start, full)
        abs_end = self._index_to_abs_pos(end, full)
        while abs_start < abs_end and full[abs_start] in TRIM_CHARS:
            abs_start += 1
        while abs_end > abs_start and full[abs_end - 1] in TRIM_CHARS:
            abs_end -= 1
        if abs_start >= abs_end:
            return
        selected = full[abs_start:abs_end]
        paragraph = self._find_paragraph(full, abs_start, abs_end)
        cache_key = f"{selected.lower()}|{abs(hash(paragraph))}"
        vi_meaning = ""
        pos = "other"
        ipa = ""
        gloss_en = ""
        if cache_key in self.llm_cache:
            data = self.llm_cache[cache_key]
            pos = data.get("pos", "other") or "other"
            ipa = data.get("ipa", "")
            gloss_en = data.get("gloss_en", "")
            vi_meaning = data.get("meaning_vi", "")
        else:
            di = api.lookup_dictionaryapi(selected)
            ipa = di.get("ipa", "")
            pos_guess = di.get("pos", "other") or "other"
            try:
                data = api.llm_word_vi(selected, paragraph)
                pos = data.get("pos", pos_guess) or pos_guess
                ipa = data.get("ipa", ipa) or ipa
                gloss_en = data.get("gloss_en", "")
                vi_meaning = data.get("meaning_vi", "")
                self.llm_cache[cache_key] = data
            except Exception as e:
                pos = pos_guess
                defs = di.get("defs") or []
                gloss_en = (defs or [f"Meaning of '{selected}'"])[0]
                vi_meaning = (gloss_en.split(";")[0]).split(",")[0].strip()
                messagebox.showwarning("OpenAI", str(e))
        entry = WordEntry(
            display=selected,
            pos=pos,
            ipa=ipa,
            vi_meaning=vi_meaning,
            gloss_en=gloss_en,
            context_sentence=paragraph,
            offsets=[{"start": abs_start, "end": abs_end}],
            added_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        )
        key = self._entry_key(selected, paragraph)
        self.entries[key] = entry
        self._refresh_tree_sorted()
        self._ensure_translation()
        self._render_all_highlights()
        try:
            self.tts.speak(selected)
        except Exception as e:
            messagebox.showerror("TTS", str(e))

    def speak_selection(self) -> None:
        try:
            txt = self.text_en.get("sel.first", "sel.last").strip()
        except tk.TclError:
            idx = self.text_en.index("insert wordstart")
            txt = self.text_en.get(idx, "insert wordend").strip()
        if txt:
            try:
                self.tts.speak(txt)
            except Exception as e:
                messagebox.showerror("TTS", str(e))

    def speak_selected_word(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        key = sel[0]
        entry = self.entries.get(key)
        if entry and entry.display:
            try:
                self.tts.speak(entry.display)
            except Exception as e:
                messagebox.showerror("TTS", str(e))

    def delete_selected_word(self) -> None:
        sel = self.tree.selection()
        if not sel:
            return
        key = sel[0]
        if key in self.entries:
            del self.entries[key]
        self._refresh_tree_sorted()
        self._render_all_highlights()

    def start_reading(self, mode: str) -> None:
        if self._reading_thread and self._reading_thread.is_alive():
            messagebox.showinfo("Reading", "Đang đọc. Hãy Pause/Resume hoặc chờ xong.")
            return
        self._reading_mode = mode
        self._reading_stop.clear()
        self._reading_pause.clear()
        self.btn_pause.config(state="normal", text="Pause")
        self._reading_thread = threading.Thread(target=self._reading_worker, daemon=True)
        self._reading_thread.start()

    def _reading_worker(self) -> None:
        full = self.text_en.get("1.0", "end-1c")
        try:
            if self._reading_mode == "paragraph":
                paragraphs = [p.strip() for p in full.split("\n\n") if p.strip()]
                for p in paragraphs:
                    self._highlight_sentence_once(full, p)
                    self.tts.speak(p)
                    self._wait_audio_or_pause()
                    self._clear_reading_highlight()
            elif self._reading_mode == "sentence":
                cur = self._get_current_sentence(full)
                if cur:
                    self._highlight_sentence_once(full, cur)
                    self.tts.speak(cur)
                    self._wait_audio_or_pause()
                    self._clear_reading_highlight()
            elif self._reading_mode == "word":
                try:
                    txt = self.text_en.get("sel.first", "sel.last").strip()
                except tk.TclError:
                    idx = self.text_en.index("insert wordstart")
                    txt = self.text_en.get(idx, "insert wordend").strip()
                if txt:
                    try:
                        start = self.text_en.index("sel.first")
                        end = self.text_en.index("sel.last")
                    except tk.TclError:
                        start = self.text_en.index("insert wordstart")
                        end = self.text_en.index("insert wordend")
                    self.text_en.tag_add("reading", start, end)
                    self.text_en.tag_configure("reading", background="#ffd000")
                    self.tts.speak(txt)
                    self._wait_audio_or_pause()
                    self._clear_reading_highlight()
        finally:
            self.btn_pause.config(state="disabled", text="Pause")

    def _wait_audio_or_pause(self) -> None:
        while pygame.mixer.get_busy():
            if self._reading_stop.is_set():
                pygame.mixer.stop()
                break
            if self._reading_pause.is_set():
                time.sleep(0.1)
                continue
            time.sleep(0.05)

    def _highlight_sentence_once(self, full: str, segment: str) -> None:
        start = full.find(segment)
        if start == -1:
            return
        end = start + len(segment)
        i1 = self._abs_to_index(start, full)
        i2 = self._abs_to_index(end, full)
        self.text_en.tag_add("reading", i1, i2)
        self.text_en.tag_configure("reading", background="#ffd000")

    def _clear_reading_highlight(self) -> None:
        self.text_en.tag_remove("reading", "1.0", "end")

    def toggle_pause(self) -> None:
        if not (self._reading_thread and self._reading_thread.is_alive()):
            return
        if not self._reading_pause.is_set():
            self._reading_pause.set()
            self.btn_pause.config(text="Resume")
        else:
            self._reading_pause.clear()
            self.btn_pause.config(text="Pause")

    def on_change_font(self, value: str) -> None:
        self.font_size = max(MIN_FONT, min(MAX_FONT, int(float(value))))
        self.text_en.config(font=("Segoe UI", self.font_size))
        self.text_vi.config(font=("Segoe UI", self.font_size))
        self._render_all_highlights()

    def _index_to_abs_pos(self, tkindex: str, full_text: str) -> int:
        line, col = map(int, tkindex.split("."))
        lines = full_text.split("\n")
        return sum(len(l) + 1 for l in lines[: line - 1]) + col

    def _abs_to_index(self, abspos: int, full_text: str) -> str:
        lines = full_text.split("\n")
        acc = 0
        for i, l in enumerate(lines, start=1):
            if acc + len(l) >= abspos:
                return f"{i}.{abspos - acc}"
            acc += len(l) + 1
        return f"{len(lines)}.{len(lines[-1]) if lines else 0}"

    def _get_current_sentence(self, full: str) -> Optional[str]:
        try:
            idx = self.text_en.index("insert")
        except tk.TclError:
            return None
        abs_pos = self._index_to_abs_pos(idx, full)
        for s_start, s_end in self.sentences_cache:
            if s_start <= abs_pos <= s_end:
                return full[s_start:s_end]
        return None

    def _find_paragraph(self, full: str, start: int, end: int) -> str:
        left = full.rfind("\n\n", 0, start)
        right = full.find("\n\n", end)
        p_start = 0 if left == -1 else left + 2
        p_end = len(full) if right == -1 else right
        return full[p_start:p_end].strip()

    def _entries_sorted_by_offset(self) -> List[WordEntry]:
        return sorted(self.entries.values(), key=lambda e: e.offsets[0]["start"] if e.offsets else 1_000_000_000)

    def _refresh_tree_sorted(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self._entries_sorted_by_offset(), start=1):
            self.tree.insert("", "end", iid=self._entry_key(e.display, e.context_sentence), values=[i, e.display, e.pos, e.vi_meaning])

    def _entry_key(self, word: str, sentence: str) -> str:
        return f"{word.lower()}|{abs(hash(sentence))}"

    def _coerce_entry(self, data: Dict) -> Optional[WordEntry]:
        try:
            offsets = data.get("offsets") or []
            entry = WordEntry(
                display=data.get("display", ""),
                pos=data.get("pos", "other"),
                ipa=data.get("ipa", ""),
                vi_meaning=data.get("vi_meaning", ""),
                gloss_en=data.get("gloss_en", ""),
                context_sentence=data.get("context_sentence", ""),
                offsets=offsets,
                added_at=data.get("added_at", ""),
            )
            return entry
        except Exception:
            return None

    def _destroy_all_windows(self) -> None:
        for widget in list(self.en_windows.values()):
            try:
                widget.destroy()
            except Exception:
                pass
        for widget in list(self.vi_windows.values()):
            try:
                widget.destroy()
            except Exception:
                pass
        self.en_windows.clear()
        self.vi_windows.clear()

    def _render_all_highlights(self) -> None:
        self._destroy_all_windows()
        for tag in list(self.en_mark_tags.values()):
            self.text_en.tag_remove(tag, "1.0", "end")
            self.text_en.tag_delete(tag)
        for tag in list(self.vi_mark_tags.values()):
            self.text_vi.tag_remove(tag, "1.0", "end")
            self.text_vi.tag_delete(tag)
        self.en_mark_tags.clear()
        self.vi_mark_tags.clear()
        occupied_vi: List[Tuple[str, str]] = []
        full_en = self.text_en.get("1.0", "end-1c")
        full_vi = self.text_vi.get("1.0", "end-1c")
        entries_sorted = self._entries_sorted_by_offset()
        for order, entry in enumerate(entries_sorted, start=1):
            if not entry.offsets:
                continue
            start_abs = entry.offsets[0]["start"]
            end_abs = entry.offsets[0]["end"]
            start_idx = self._abs_to_index(start_abs, full_en)
            end_idx = self._abs_to_index(end_abs, full_en)
            tag_en = f"mark_en_{order}_{start_abs}"
            self.text_en.tag_add(tag_en, start_idx, end_idx)
            self.text_en.tag_configure(tag_en, background=HIGHLIGHT_COLOR)
            widget_en = self._create_number_widget(self.text_en, order)
            self.text_en.window_create(start_idx, window=widget_en)
            self.en_mark_tags[self._entry_key(entry.display, entry.context_sentence)] = tag_en
            self.en_windows[self._entry_key(entry.display, entry.context_sentence)] = widget_en
            if full_vi.strip():
                span = self._find_vi_span(entry, full_vi, occupied_vi)
                if span:
                    vi_start, vi_end, vi_text = span
                    entry.vi_meaning = vi_text
                    tag_vi = f"mark_vi_{order}_{vi_start}"
                    self.text_vi.tag_add(tag_vi, vi_start, vi_end)
                    self.text_vi.tag_configure(tag_vi, background=HIGHLIGHT_COLOR)
                    widget_vi = self._create_number_widget(self.text_vi, order)
                    self.text_vi.window_create(vi_start, window=widget_vi)
                    self.vi_mark_tags[self._entry_key(entry.display, entry.context_sentence)] = tag_vi
                    self.vi_windows[self._entry_key(entry.display, entry.context_sentence)] = widget_vi
        self._refresh_tree_sorted()

    def _create_number_widget(self, host: tk.Text, order: int) -> tk.Widget:
        line_height = self._line_height(host)
        width = max(10, int(self.font_size * 0.6))
        canvas = tk.Canvas(host, width=width, height=line_height, highlightthickness=0, bd=0, bg=HIGHLIGHT_COLOR)
        font_size = max(8, int(self.font_size / 3))
        canvas.create_text(2, 1, text=str(order), fill="#000000", anchor="nw", font=("Segoe UI", font_size, "bold"))
        return canvas

    def _line_height(self, widget: tk.Text) -> int:
        bbox = widget.bbox("insert")
        if bbox:
            return bbox[3]
        font = widget.cget("font")
        return int(self.font_size * 1.4)

    def _find_vi_span(self, entry: WordEntry, full_vi: str, occupied: List[Tuple[str, str]]) -> Optional[Tuple[str, str, str]]:
        needle = (entry.vi_meaning or "").strip()
        if not needle:
            needle = entry.display.strip()
        if not needle:
            return None
        start = "1.0"
        while True:
            idx = self.text_vi.search(needle, start, stopindex="end", nocase=True)
            if not idx:
                return None
            end = f"{idx}+{len(needle)}c"
            if not any(self._ranges_overlap(idx, end, s, e) for s, e in occupied):
                occupied.append((idx, end))
                return idx, end, self.text_vi.get(idx, end)
            start = end

    def _ranges_overlap(self, a_start: str, a_end: str, b_start: str, b_end: str) -> bool:
        a_s = self._index_to_tuple(a_start)
        a_e = self._index_to_tuple(a_end)
        b_s = self._index_to_tuple(b_start)
        b_e = self._index_to_tuple(b_end)
        return not (a_e <= b_s or b_e <= a_s)

    def _index_to_tuple(self, index: str) -> Tuple[int, int]:
        line, col = map(int, index.split("."))
        return line, col

    def _ensure_translation(self) -> None:
        if self.text_vi.get("1.0", "end-1c").strip():
            return
        english = self.text_en.get("1.0", "end-1c")
        if not english.strip():
            return
        try:
            vi = api._openai_chat(
                [
                    {"role": "system", "content": "You translate English to natural, fluent Vietnamese. Keep paragraph breaks exactly as input."},
                    {"role": "user", "content": english},
                ],
                temperature=0.2,
            )
        except Exception as e:
            messagebox.showerror("Dịch", str(e))
            return
        self.text_vi.delete("1.0", "end")
        self.text_vi.insert("1.0", vi)

    def _on_left_tab_changed(self, _: tk.Event) -> None:
        tab = self.nb_left.nametowidget(self.nb_left.select())
        if tab is self.tab_vi:
            self._ensure_translation()
            self._render_all_highlights()

if __name__ == "__main__":
    try:
        _ = sent_tokenize("Test.")
    except LookupError:
        nltk.download("punkt")
    app = VocabReaderApp()
    app.mainloop()
