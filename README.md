# English-for-To

Trình đọc Từ vựng – Ngữ cảnh (OptionB)
=========================================

Ứng dụng Tkinter giúp đọc – học từ vựng Anh–Việt với các tính năng:
- Mở file .txt, đọc theo đoạn/câu/từ với TTS.
- Đánh dấu “từ mới” trực tiếp trong văn bản tiếng Anh, tự tô sáng ở English & Viet‑sub.
- Tự thêm số thứ tự (bubble) trước từ ở cả English & Viet‑sub; số thứ tự luôn đồng bộ khi cuộn/đổi cỡ chữ.
- Bảng “Từ điển cá nhân” bên phải: phát âm theo LEMMA (cột Word) hoặc theo NGỮ CẢNH (cột No.).
- Lưu/khôi phục phiên học (.json) và Export TXT 3 cột (word, pos, meaning_vi).

Tài liệu này hướng dẫn cài đặt, sử dụng, phím tắt, định dạng dữ liệu, tuỳ biến và xử lý sự cố.

-----------------------------------------
1) Yêu cầu hệ thống
-----------------------------------------
- Python 3.11+ (đã thử 3.12)
- Windows / macOS / Linux
- Gói: tkinter (có sẵn với Python chuẩn), nltk, pygame
- (Tuỳ TTS/LLM) Các phụ thuộc trong OptionB_api_module.py

Cài đặt nhanh:
    pip install nltk pygame

Dữ liệu NLTK cần dùng (ứng dụng sẽ tự tải khi thiếu):
- punkt
- wordnet, omw-1.4
- averaged_perceptron_tagger (hoặc averaged_perceptron_tagger_eng)

TTS & LLM (định nghĩa trong OptionB_api_module.py, đặt cùng thư mục với file .py chính):
- Cần cung cấp các API sau:
    class TTSManager:
        def __init__(self, cache_dir: str, lang: str = "en", tld: str = "com"): ...
        def speak(self, text: str): ...
    def lookup_dictionaryapi(term: str) -> dict:
        # Trả về {'ipa': str, 'pos': str, 'defs': List[str]}
    def _openai_chat(messages: list[dict], temperature: float = 0.2) -> str:
        # Trả về chuỗi kết quả (dịch/meaning VI)

- Nếu _openai_chat cần API key, hãy cấu hình trong OptionB_api_module.py (ENV hoặc file cấu hình).
- Âm thanh TTS sẽ cache dưới ./cache/audio (tự tạo).

-----------------------------------------
2) Chạy ứng dụng
-----------------------------------------
- Đảm bảo có OptionB_api_module.py cạnh file .py chính.
- Chạy:
    python your_main_file.py

- Lần đầu có thể cần internet để tải NLTK.
- Giao diện gồm 2 khu vực:
  • Trái (Notebook): English và Viet‑sub (mỗi tab có scrollbar riêng).
  • Phải (Notebook): “Từ điển cá nhân” (bảng No. | Word | POS | Meaning (VI)).

-----------------------------------------
3) Quy trình sử dụng cơ bản
-----------------------------------------
1. Mở văn bản:
   - File → Open .txt (Ctrl+O).
   - Nội dung tiếng Anh hiển thị trong tab “English”.

2. Đánh dấu từ mới (tab English):
   - Bôi đen từ/cụm từ → chuột phải → “Đánh dấu từ mới (Alt+D)” hoặc nhấn Alt+D.
   - Ứng dụng sẽ:
     • Phân tích lemma/POS/IPA, dựng nghĩa VI theo ngữ cảnh đoạn.
     • Thêm dòng vào bảng từ điển (No., Word, POS, Meaning (VI)).
     • Tô nền vàng vùng chọn trong English và chèn bubble nhỏ (số thứ tự) trước từ.
     • Nếu Viet‑sub đang trống, tự dịch toàn văn; sau đó highlight nghĩa VI (khớp đầu tiên) và chèn bubble cùng số.
     • Phát âm NGAY lập tức theo surface (đúng từ bạn bôi đen).

3. Chế độ đọc (TTS) ở tab English:
   - Read Paragraph (Ctrl+P): đọc từng đoạn, highlight vàng tạm thời.
   - Read Sentence (Ctrl+Shift+S): đọc câu hiện tại tại con trỏ.
   - Read Word (Ctrl+W): đọc từ đã chọn/đang đứng.
   - Pause/Resume (Space) trong khi phát.

4. Viet‑sub:
   - Chuyển sang tab “Viet‑sub”; nếu trống, app tự gọi _openai_chat để dịch.
   - Highlight và bubble ở Viet‑sub đồng bộ theo thứ tự xuất hiện của English.

5. Lưu/Khôi phục/Export:
   - Save Session (JSON): lưu text, theme, font, entries…
   - Load Session (JSON): khôi phục và áp lại highlight/bubble.
   - Export TXT (Ctrl+E): ghi tệp UTF‑8 với 3 cột: word	pos	meaning_vi

-----------------------------------------
4) Giao diện & Phím tắt
-----------------------------------------
Thanh công cụ trên cùng:
- Open .txt • Save Session (JSON) • Load Session (JSON) • Export TXT
- Read Paragraph / Read Sentence / Read Word • Pause
- Thanh trượt Font: chỉnh cỡ chữ toàn cục (MIN_FONT → MAX_FONT).

Notebook bên trái:
- English: nơi bôi đen để đánh dấu từ mới, nghe TTS.
- Viet‑sub: phần dịch tự động, highlight VI và bubble tương ứng.

Notebook bên phải – “Từ điển cá nhân”:
- Bảng: No. | Word | POS | Meaning (VI)
- Nhấp vào hàng (cột Word): phát âm LEMMA (dạng nguyên mẫu).
- Nhấp vào số thứ tự (cột No.): phát âm dạng NGỮ CẢNH (surface) – chính xác như lúc bạn bôi đen.
- Thanh công cụ trong tab: “Phát âm”, “Xoá dòng”, “Export TXT”.

Menu chuột phải (tab English):
- “Đánh dấu từ mới (Alt+D)” – thêm vào bảng + highlight + bubble + phát âm ngay.
- “Phát âm” – đọc vùng chọn/ từ tại caret.

Phím tắt:
- Alt+D  → Đánh dấu từ mới
- Ctrl+O → Open .txt
- Ctrl+S → Save Session (JSON)
- Ctrl+E → Export TXT
- Ctrl+P → Read Paragraph
- Ctrl+Shift+S → Read Sentence
- Ctrl+W → Read Word
- Space  → Pause/Resume TTS

-----------------------------------------
5) Dữ liệu & Định dạng tệp
-----------------------------------------
Session JSON gồm: text_content, created_at, theme, font_size, entries[].
Mỗi entry:
{
  "display": "<lemma>",
  "pos": "noun|verb|adjective|adverb|other",
  "ipa": "...",
  "vi_meaning": "<nghĩa VI>",
  "gloss_en": "<gloss EN đầu tiên>",
  "context_sentence": "<đoạn ngữ cảnh>",
  "offsets": [{"abs_start": int, "abs_end": int}],
  "status": "new",
  "added_at": "YYYY-MM-DD HH:MM:SS",
  "surface": "<chuỗi bạn bôi đen>"
}

Export TXT (UTF‑8, dạng TSV):
word	pos	meaning_vi

Cache âm thanh:
- Được TTSManager ghi vào ./cache/audio

-----------------------------------------
6) Tuỳ biến (hằng số & chủ đề)
-----------------------------------------
- APP_TITLE, DEFAULT_FONT_SIZE, MIN_FONT, MAX_FONT
- HIGHLIGHT_COLOR (mặc định: #fff7ad)
- LEMMA_CELL_COLOR (mặc định: #5dade2) – màu cell khi phát LEMMA ở bảng
- CONTEXT_CELL_COLOR (mặc định: #ffe082) – màu cell khi phát NGỮ CẢNH (cột No.)
- TREE_HIGHLIGHT_TIMEOUT_MS (mặc định: 1800 ms) – thời gian tự xoá màu cell
- THEMES["light"|"dark"]: text_fg, text_bg, sel_bg

Ghi chú:
- Hàm toggle_theme có sẵn nội bộ; nếu không cần đổi theme, có thể giữ mặc định “light”.

-----------------------------------------
7) Cơ chế Bubble & Highlight
-----------------------------------------
English:
- Khi mark_new_word, vùng chọn được “cắt mép” (bỏ khoảng trắng/ký tự thừa).
- Lưu offsets tuyệt đối; đặt 2 marks (start/end) trong Text.
- Thêm tag nền vàng (“word_highlight”) phủ vùng chọn.
- Tạo “bubble” số thứ tự bằng Text.window_create ngay tại mark bắt đầu; kích thước bám theo line‑height hiện tại.
- Thứ tự đánh số dựa vào vị trí xuất hiện đầu tiên; tự làm mới khi đổi cỡ chữ.

Viet‑sub:
- Với từng entry (theo thứ tự offsets của English), tìm KHỚP ĐẦU TIÊN của nghĩa VI trong đoạn dịch, tô vàng và chèn bubble cùng số.
- Nếu không tìm thấy, bỏ qua lặng lẽ (không báo lỗi).

Bảng từ điển:
- Chọn dòng mặc định phát LEMMA và tô màu ô “Word” (xanh).
- Nhấn cột “No.” phát NGỮ CẢNH (surface) và tô màu ô “No.” (vàng nhạt).
- Màu ô tự xoá khi kết thúc phát hoặc hết timeout.

-----------------------------------------
8) Khắc phục sự cố
-----------------------------------------
• Lỗi NLTK LookupError (punkt/wordnet/tagger):
  Ứng dụng sẽ cố tải tự động; nếu bị chặn mạng, chạy thủ công:
      import nltk
      nltk.download("punkt"); nltk.download("wordnet")
      nltk.download("omw-1.4")
      nltk.download("averaged_perceptron_tagger")

  Ngoài ra, app hỗ trợ NLTK_FALLBACK (phù hợp build PyInstaller one‑file).

• Lỗi OpenAI/LLM hoặc hết quota:
  _openai_chat() đã có try/except; nếu quota thiếu, nghĩa VI/ dịch có thể rỗng.
  Cấu hình API key và xử lý lỗi ở OptionB_api_module.py.

• Pygame mixer không phát tiếng:
  Kiểm tra thiết bị âm thanh; trên máy ảo/server không có audio sẽ phát lỗi.
  Có thể khởi tạo pygame.mixer sớm hơn/điều chỉnh sample rate theo TTS bạn dùng.

• Viet‑sub không highlight được:
  App khớp theo “nghĩa VI” đầu tiên. Nếu quá chung chung, nhiều vị trí có thể trùng; app chỉ đánh dấu vị trí đầu tiên.
  Hãy làm nghĩa VI cụ thể hơn nếu cần.

• Bubble đè chữ:
  Bubble được chèn trước từ bằng window_create và scale theo font. Nếu font quá nén, hãy tăng DEFAULT_FONT_SIZE hoặc chỉnh lại kích thước trong _style_number_widget().

-----------------------------------------
9) Mẹo sử dụng
-----------------------------------------
- Chọn “từ” hay “cụm từ” đều được; POS ưu tiên theo tag trong đoạn.
- Chế độ đọc (paragraph/sentence/word) độc lập với danh sách từ mới.
- File phiên học có thể di chuyển giữa máy, nhưng offsets phụ thuộc đúng nội dung văn bản.
- Dịch Viet‑sub giữ nguyên ngắt đoạn (\n\n).

-----------------------------------------
10) Gợi ý cấu trúc dự án
-----------------------------------------
project_root/
  ├─ your_main_file.py
  ├─ OptionB_api_module.py
  ├─ cache/
  │   └─ audio/          # tạo tự động
  ├─ nltk_data/          # tuỳ chọn – nhúng cho PyInstaller
  └─ readme_vi.txt       # tài liệu này

-----------------------------------------
11) Bảo mật & Cấu hình API
-----------------------------------------
- Không hard‑code API key vào repo; dùng biến môi trường hoặc tệp cấu hình ngoài .git.
- Xử lý lỗi/quota trong OptionB_api_module.py để tránh crash UI.

-----------------------------------------
12) Giấy phép & Ghi công
-----------------------------------------
- Tự do sử dụng/chỉnh sửa cho mục đích cá nhân/nội bộ.
- Thư viện sử dụng: NLTK, pygame, Tkinter (stdlib Python).
- Việc dùng OpenAI/LLM phụ thuộc vào triển khai trong OptionB_api_module.py.

Chúc bạn học hiệu quả!


Chương trình học tiếng Anh cho To
Vocabulary Reader – Context Aware (OptionB)
=================================================

A Tkinter-based English–Vietnamese vocabulary reader that lets you:
- Load a plain-text (.txt) file and read by paragraph/sentence/word with TTS.
- Mark “new words” directly in the English text (no popup) and auto-highlight them in both English and Viet-sub.
- Auto-number each marked word with small “bubbles” in English and Viet-sub, kept in sync as you scroll or resize fonts.
- Maintain a personal dictionary on the right pane; click to play lemma (Word column) or context form (No. column).
- Save/load learning sessions to JSON and export a 3-column TXT (word, pos, meaning_vi).

This README explains setup, usage, hotkeys, file formats, customization, and troubleshooting.

-------------------------------------------------
1) Requirements
-------------------------------------------------
- Python: 3.11+ (tested with 3.12)
- OS: Windows/macOS/Linux
- Packages: tkinter (bundled with most Python installs), nltk, pygame
  (Optionally: gTTS/pydub/etc. depending on your TTS backend inside OptionB_api_module.py)

Install Python packages:
    pip install nltk pygame

NLTK data:
- The app attempts to use an embedded fallback (NLTK_FALLBACK) and will auto-download at first run if missing:
  - punkt
  - wordnet, omw-1.4
  - averaged_perceptron_tagger or averaged_perceptron_tagger_eng

TTS & LLM backends (in OptionB_api_module.py):
- You must provide OptionB_api_module.py in the same directory as the main script.
- It must implement:
    class TTSManager:
        def __init__(self, cache_dir: str, lang: str = "en", tld: str = "com"): ...
        def speak(self, text: str): ...
    def lookup_dictionaryapi(term: str) -> dict:
        # returns {'ipa': str, 'pos': str, 'defs': List[str]}
    def _openai_chat(messages: list[dict], temperature: float = 0.2) -> str:
        # returns model output (translation or VI meaning)
- If your _openai_chat needs an API key, configure it inside OptionB_api_module.py (env var or a config file).
- Audio caching will be written under ./cache/audio (auto-created).

-------------------------------------------------
2) Running the App
-------------------------------------------------
- Ensure OptionB_api_module.py is present alongside your main .py file.
- Run:
    python your_main_file.py

- First launch may download NLTK resources (internet required).
- The main window appears with two panes:
  - Left (Notebook): English tab and Viet-sub tab (each has its own scrollbar).
  - Right (Notebook): “Từ điển cá nhân” (personal dictionary table).

-------------------------------------------------
3) Basic Workflow
-------------------------------------------------
1. Open text:
   - File → Open .txt (Ctrl+O)
   - The English text renders in the “English” tab.

2. Mark a new word (English tab):
   - Select a word/phrase, then right-click → “Đánh dấu từ mới (Alt+D)” or press Alt+D.
   - The app:
     - Lemmatizes and fetches IPA/POS/meaning.
     - Adds to the dictionary table (No., Word, POS, Meaning (VI)).
     - Highlights the selection in English and drops a small numbered bubble before it.
     - Generates/updates the Viet-sub (if empty) and highlights the Vietnamese meaning (first match) with the same number bubble.
     - Speaks the SELECTION immediately (surface form).

3. Listening/reading modes (English tab):
   - Read Paragraph (Ctrl+P): Reads each paragraph with a temporary yellow highlight.
   - Read Sentence (Ctrl+Shift+S): Reads only the current sentence at the cursor.
   - Read Word (Ctrl+W): Reads the selected/caret word and briefly highlights it.
   - Pause/Resume (Space) during TTS.

4. Viet-sub generation:
   - Switch to the “Viet-sub” tab; if it is empty, the app calls translation via _openai_chat to fill it.
   - Highlights/number-bubbles are auto-synced with the English tab entries.

5. Save/Load/Export:
   - Save Session (JSON): persists text, theme, font, and all entries.
   - Load Session (JSON): restores, then reapplies highlights/bubbles.
   - Export TXT (Ctrl+E): creates a TSV-like text file with 3 columns:
         word	pos	meaning_vi

-------------------------------------------------
4) UI Guide & Shortcuts
-------------------------------------------------
Top Toolbar:
- Open .txt — load UTF-8 text.
- Save Session (JSON) — persist current learning state.
- Load Session (JSON) — restore a prior session.
- Export TXT — save 3-column vocabulary file.
- Read Paragraph / Read Sentence / Read Word — TTS controls.
- Pause — pause/resume current speech.
- Font slider — adjust global font size (MIN_FONT to MAX_FONT).

Left Notebook:
- English tab — work here to mark new words and listen.
- Viet-sub tab — auto translation and VI highlights; synced numbering bubbles.

Right Notebook: “Từ điển cá nhân”
- Table columns: No. | Word | POS | Meaning (VI)
- Click row in “Word” column → speak LEMMA form (base form).
- Click row number (“No.” column) → speak the CONTEXT surface form (the exact text you selected originally).
- Toolbar: “Phát âm” (lemma), “Xoá dòng”, “Export TXT”.

Context Menu in English tab (Right-click):
- “Đánh dấu từ mới (Alt+D)” — add to dictionary + highlight + bubbles + speak immediately.
- “Phát âm” — pronounce the current selection/caret word.

Keyboard Shortcuts:
- Alt+D → Mark new word
- Ctrl+O → Open .txt
- Ctrl+S → Save Session (JSON)
- Ctrl+E → Export TXT
- Ctrl+P → Read Paragraph
- Ctrl+Shift+S → Read Sentence
- Ctrl+W → Read Word
- Space → Pause/Resume TTS

-------------------------------------------------
5) Data & File Formats
-------------------------------------------------
- Session JSON: includes text_content, created_at, theme, font_size, and entries[].
  Each entry follows:
    {
      "display": "<lemma>",
      "pos": "noun|verb|adjective|adverb|other",
      "ipa": "...",
      "vi_meaning": "<VI meaning>",
      "gloss_en": "<first English gloss>",
      "context_sentence": "<paragraph context>",
      "offsets": [{"abs_start": int, "abs_end": int}],
      "status": "new",
      "added_at": "YYYY-MM-DD HH:MM:SS",
      "surface": "<original selection>"
    }

- Export TXT (UTF-8 TSV-like):
    word	pos	meaning_vi

- Audio cache:
  - Generated by TTSManager under ./cache/audio

-------------------------------------------------
6) Customization (constants & themes)
-------------------------------------------------
- APP_TITLE, DEFAULT_FONT_SIZE, MIN_FONT, MAX_FONT
- HIGHLIGHT_COLOR (default: #fff7ad)
- LEMMA_CELL_COLOR (default: #5dade2) – table cell tint when playing lemma
- CONTEXT_CELL_COLOR (default: #ffe082) – table cell tint when playing context (No.)
- TREE_HIGHLIGHT_TIMEOUT_MS (default: 1800 ms) – auto-clear timing for table cell highlight
- THEMES["light"|"dark"]: text_fg, text_bg, sel_bg

Note:
- “Toggle theme” exists internally; if you don’t plan to expose a theme switcher, keep the default light theme.

-------------------------------------------------
7) How Bubbles & Highlights Work
-------------------------------------------------
- English:
  - On mark_new_word, the selection range is trimmed to exclude punctuation/space.
  - App stores absolute offsets and creates two marks (start/end) in the Text widget.
  - A yellow background tag (“word_highlight”) is added over the selection.
  - A small framed “number bubble” widget is inserted at the start mark using Text.window_create, sized to the current font.
  - Bubbles are numbered by first appearance order and are refreshed on font changes.

- Viet-sub:
  - For each entry (in sorted order of English offsets), the app searches the VI meaning text (first match) and applies the same highlight tag and bubble number in the Viet-sub Text.
  - If a meaning isn’t found, the app skips that entry silently.

- Dictionary table:
  - Selecting a row plays lemma by default and briefly highlights the “Word” cell (blue).
  - Clicking the “No.” cell plays the context (surface) and highlights the “No.” cell (amber).
  - Cell highlight auto-clears after speech ends or timeout.

-------------------------------------------------
8) Troubleshooting
-------------------------------------------------
- NLTK LookupError (punkt, wordnet, tagger):
  - The app tries to download automatically. If blocked by firewall, run these once in Python:
        import nltk
        nltk.download("punkt"); nltk.download("wordnet")
        nltk.download("omw-1.4")
        nltk.download("averaged_perceptron_tagger")
  - The code also checks NLTK_FALLBACK under sys._MEIPASS for PyInstaller one-file builds.

- OpenAI/LLM errors or quota:
  - _openai_chat() exceptions are caught; if quota is insufficient, VI meaning/translation may be empty.
  - Configure your API key and error handling inside OptionB_api_module.py.

- Pygame mixer not working (no audio device):
  - Ensure audio output exists; on servers/VMs without audio, TTS may fail to play.
  - Try initializing pygame.mixer earlier or checking sample rate settings in your TTS engine.

- Viet-sub highlight not found:
  - The app matches the FIRST occurrence of the short VI meaning. If the phrase is too generic, multiple hits may exist but only the first is used.
  - Consider making meanings a bit more specific if needed.

- Bubbles overlap text:
  - The bubble is inserted at the mark position before the word; the app attempts to size it to the current line height.
  - If your font is compressed, increase DEFAULT_FONT_SIZE or tweak _style_number_widget() width/height computation.

-------------------------------------------------
9) Tips & Notes
-------------------------------------------------
- Selecting a word vs. phrase:
  - The POS guess prioritizes the in-paragraph tag; lemma is derived from WordNet lemmatizer.
- Reading modes are independent from marked words; they simply highlight temporarily and speak the chosen segment.
- Session files are portable; however, absolute offsets assume the same exact text content.
- Translation preserves paragraph breaks exactly (\n\n).

-------------------------------------------------
10) Project Structure (suggested)
-------------------------------------------------
project_root/
  ├─ your_main_file.py
  ├─ OptionB_api_module.py
  ├─ cache/
  │   └─ audio/          # auto-created
  ├─ nltk_data/          # optional embedded data for PyInstaller
  └─ readme.txt          # this file

-------------------------------------------------
11) License & Credits
-------------------------------------------------
- You may use/modify this code for personal or internal projects.
- Credits: NLTK, pygame; Tkinter from Python stdlib.
- OpenAI (or other LLM) usage depends on your OptionB_api_module.py implementation.

Have fun learning!
