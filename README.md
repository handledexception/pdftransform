# pdftransform

A simple Python CLI/GUI application for modifying PDF documents. Flip, rotate, and delete pages from the command line, or edit a PDF interactively in a GUI editor.

## Installation

Requires Python 3.8+.

```sh
python -m pip install -r requirements.txt
```

Only `pypdf` is strictly required. The GUI preview/editor additionally needs `pymupdf` (renders the pages) and `PySide6-Essentials` (the editor window); without PySide6, `--preview` falls back to a view-only tkinter window.

## CLI usage

```sh
python main.py INPUT.pdf [actions] [options]
```

The input file is never modified. The result is saved next to it as `INPUT_modified.pdf` (see `--suffix` / `--output` to change that), and the PDF's Title metadata gets " (modified)" appended.

### Actions

| Action | Effect |
|---|---|
| `--flip-h` | Flip pages horizontally (mirror left/right) |
| `--flip-v` | Flip pages vertically (mirror top/bottom) |
| `--rotate-cw N` | Rotate pages clockwise N times (90° each) |
| `--rotate-ccw N` | Rotate pages counter-clockwise N times (90° each) |
| `--delete` | Delete the selected pages |

Flip/rotate actions can be combined and are applied in the order they appear on the command line.

### Selecting pages

By default, actions apply to every page. Use `--pages` to restrict them, with 1-based page numbers:

- a single page: `--pages 3`
- a list: `--pages 1,3,7`
- a range: `--pages 2-5` (or `2..5`)
- any combination: `--pages 1,3-5,8..10`

### Options

| Option | Effect |
|---|---|
| `--pages PAGES` | Pages to apply the actions to (default: all) |
| `--suffix SUFFIX` | Suffix for the output file name (default: `_modified`) |
| `-o, --output PATH` | Explicit output path (overrides `--suffix` naming) |
| `--preview` | Open the result (or the interactive editor) in a GUI window |

### Examples

Flip every page horizontally:

```sh
python main.py scan.pdf --flip-h
```

Rotate pages 1 and 4–6 by 180°:

```sh
python main.py scan.pdf --rotate-cw 2 --pages 1,4-6
```

Delete pages 2 and 3:

```sh
python main.py scan.pdf --delete --pages 2-3
```

Flip vertically, then rotate once clockwise, and save to a specific file:

```sh
python main.py scan.pdf --flip-v --rotate-cw 1 -o fixed.pdf
```

Apply an action and immediately view the saved result:

```sh
python main.py scan.pdf --rotate-cw 1 --preview
```

## GUI editor

Run `--preview` without any actions to edit a PDF interactively:

```sh
python main.py scan.pdf --preview
```

or start with an empty window and open a file from the menu:

```sh
python main.py --preview
```

In the editor, the action buttons (Flip Hori, Flip Vert, Rotate CW, Rotate CCW, Delete Page) apply to the currently shown page. Use the File menu to Open, Save, or Save As — Save writes to the input name plus the suffix (e.g. `scan_modified.pdf`) by default.

Keyboard shortcuts:

| Key | Action |
|---|---|
| Left / Right | Previous / next page |
| Home / End | First / last page |
| Ctrl+O / Ctrl+S | Open / Save |
| Escape | Close the window |

## License

See [LICENSE](LICENSE).
