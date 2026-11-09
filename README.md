# md-graph

**Your Markdown files, as one picture.**

A Windows tool that reads a folder of `.md` files and draws which document points to which — as a single HTML file you open in your browser. No install, no server, no internet.

---

## What it does

Give it a folder full of Markdown notes, rules, or documentation. It finds every `` `file.md` `` mention, works out whether that is a rule reference, a document reference, or just a passing mention, and draws the whole web of links.

- **One file out.** Everything lands in `_docs/관계도.html`. Double-click it. Done.
- **Click a circle** to read that file on the right.
- **Hold a circle** to focus on it and its neighbours only.
- **Filter by link type** with the chips along the top.
- **Hover a link** to see the exact line that made it.
- **Press R** to reset the view.

It also scores each file against a few documentation rules (length, BOM, duplicated content, links to files that do not exist) and shows the result as `4/4` next to the name.

## Requirements

- **Windows** (the launcher is a `.bat` file)
- **Python 3.10 or newer**, with **"Add python.exe to PATH"** ticked during install
- Any modern browser

## How to use it

1. Download the repo (green **Code** button → **Download ZIP**) and unzip it **inside** the folder you want to map.
2. Move the `md관계도` folder into that same folder — it must sit directly inside it.
3. Open `md관계도` and double-click `build.bat`.
4. Your browser opens with the graph.

Result: `<your folder>/_docs/관계도.html`

```
your-notes/
├── AGENTS.md
├── notes/
│   └── design.md
└── md관계도/            <- keep this folder whole
    ├── build.bat
    ├── graph_explorer.py
    └── README.md
```

Or run it directly:

```
python md관계도\graph_explorer.py --root "C:\path\to\your\notes"
```

`build.bat` looks at the folder **above** itself, so the package folder must stay one level below the folder you want to map. It refuses to run if the three files were taken out of the folder.

## What the link types mean

| Chip | Meaning | Default |
|---|---|---|
| **A** 규칙 참조 | A rules file told you to read this | on |
| **B** 문서 참조 | Mentioned with words like "see", "refer to" | on |
| **C** 설명 언급 | The name appears in a sentence, nothing more | off |
| **D** 자리표시자 | Looks like `NN_` or `*` — not a real file | off |
| **E** 외부 경로 | Points outside this folder (another repo, another product) | off |
| **F** 없는 파일 | Points at something that does not exist | off |
| **G** 연결 없음 | Nothing links to it and it links to nothing | off |

Types A–D only appear when the folder contains an `AGENTS.md` or `CLAUDE.md` rules file. Without one, most links are B or C. That is not a bug — there are simply no rules to reference.

## Honest limits

- **Markdown only.** It does not read text inside images, PDFs, Word, or Excel files.
- **It does not understand meaning.** It counts which line points at which file. No summarising, translating, or judging.
- **Windows only.** macOS and Linux users would need to call `graph_explorer.py` themselves.
- **Large folders get slow.** Measured: 1,000 files takes about 2 seconds and produces a 446 KB page.
- **No internet, ever.** Nothing leaves your computer.
- **It never edits your files.** It writes exactly one new file, `_docs/관계도.html`.

## When it stops with `[ERROR]`

| Message | What happened | Fix |
|---|---|---|
| `Python 3.10 or newer is not installed` | No Python on PATH | Install from python.org, tick **"Add python.exe to PATH"** |
| `Your Python is too old` | Python below 3.10 | Install a newer one |
| `No .md files found in: ...` | No Markdown in the folder above the package | Unzip **inside** the folder you want to map |
| `Cannot open the folder above` | Unzipped too deep | Move the package one level up |
| `This package folder also contains YOUR .md files` | The three files were dropped loose instead of keeping the `md관계도` folder | Delete those three files and unzip again, keeping the folder whole |

`build.bat` stops on purpose in all five cases. It never guesses and never maps the wrong folder.

## Licence

MIT. See [LICENSE](LICENSE).
