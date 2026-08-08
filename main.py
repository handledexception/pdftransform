#!/usr/bin/env python3
"""pdf_transform - apply page transformations to a PDF from the CLI or a GUI editor.

Actions:
  --flip-h            Flip pages horizontally (mirror left/right)
  --flip-v            Flip pages vertically (mirror top/bottom)
  --rotate-cw N       Rotate pages clockwise N times (90 degrees each)
  --rotate-ccw N      Rotate pages counter-clockwise N times (90 degrees each)
  --delete            Delete the selected pages

Page selection:
  --pages PAGES       1-based page numbers: a single number (3), a comma
                      separated list (1,3,7), ranges (2-5 or 2..5), or any
                      combination (1,3-5,8..10). Without --pages, actions
                      apply to every page.

Flip/rotate actions are applied in the order given on the command line, to the
selected pages. The result is saved next to the input as <name>_modified.pdf
(configurable with --suffix), and the PDF metadata Title gets " (modified)"
appended.

Preview / editor:
  --preview           Open a GUI window. With actions, it shows the saved
                      result; standalone (no actions), it opens an interactive
                      editor where each action button applies to the currently
                      shown page. File menu: Open / Save / Save As / Exit.
                      Keys: Left/Right = prev/next page, Home/End = first/last
                      page, Escape = close.

Examples:
  python pdf_transform.py scan.pdf --flip-h
  python pdf_transform.py scan.pdf --rotate-cw 2 --pages 1,4-6
  python pdf_transform.py scan.pdf --delete --pages 2..3
  python pdf_transform.py scan.pdf --preview
  python pdf_transform.py --preview
"""

import argparse
import io
import sys
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation

DEFAULT_SUFFIX = "_modified"


class OrderedOpAction(argparse.Action):
    """Collect flip/rotate actions into a single list, preserving command-line order."""

    def __call__(self, parser, namespace, values, option_string=None):
        ops = getattr(namespace, "operations", None) or []
        # Flag-style ops (nargs=0) arrive as an empty list; store None instead.
        ops.append((self.dest, values if isinstance(values, int) else None))
        namespace.operations = ops


def flip_horizontal(page):
    box = page.mediabox
    # Mirror about the vertical centerline of the page box: x' = -x + (left + right)
    page.add_transformation(
        Transformation((-1, 0, 0, 1, float(box.left) + float(box.right), 0)),
        expand=False,
    )


def flip_vertical(page):
    box = page.mediabox
    page.add_transformation(
        Transformation((1, 0, 0, -1, 0, float(box.bottom) + float(box.top))),
        expand=False,
    )


def apply_operations(page, operations):
    for op, count in operations:
        if op == "flip_h":
            flip_horizontal(page)
        elif op == "flip_v":
            flip_vertical(page)
        elif op == "rotate_cw":
            page.rotate(90 * count)
        elif op == "rotate_ccw":
            page.rotate(-90 * count)


def modified_title(metadata, fallback):
    title = str(metadata.get("/Title") or fallback)
    if not title.endswith(" (modified)"):
        title += " (modified)"
    return title


def positive_int(value):
    n = int(value)
    if n < 1:
        raise argparse.ArgumentTypeError("rotation count must be at least 1")
    return n


def parse_page_spec(spec):
    """Parse a 1-based page spec like '3', '1,3,7', '2-5', '2..5', '1,3-5,8..10'."""
    pages = set()
    for part in spec.split(","):
        part = part.strip().replace("..", "-")
        try:
            if "-" in part:
                start, end = part.split("-", 1)
                start, end = int(start), int(end)
                if start < 1 or end < start:
                    raise ValueError
                pages.update(range(start, end + 1))
            else:
                page = int(part)
                if page < 1:
                    raise ValueError
                pages.add(page)
        except ValueError:
            raise argparse.ArgumentTypeError(
                f"invalid page spec {part!r} - use 1-based numbers, lists, and "
                "ranges like 3 or 1,3,7 or 2-5 or 2..5"
            )
    return pages


def build_parser():
    parser = argparse.ArgumentParser(
        prog="pdf_transform",
        description="Apply flip/rotate/delete actions to selected pages of a PDF, "
                    "or edit one interactively with --preview.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", type=Path, nargs="?", default=None,
                        help="path to the input PDF file (optional with --preview)")
    parser.add_argument(
        "--flip-h", dest="flip_h", action=OrderedOpAction, nargs=0,
        help="flip the selected pages horizontally (mirror left/right)",
    )
    parser.add_argument(
        "--flip-v", dest="flip_v", action=OrderedOpAction, nargs=0,
        help="flip the selected pages vertically (mirror top/bottom)",
    )
    parser.add_argument(
        "--rotate-cw", dest="rotate_cw", action=OrderedOpAction,
        type=positive_int, metavar="N",
        help="rotate the selected pages clockwise N times (90 degrees per rotation)",
    )
    parser.add_argument(
        "--rotate-ccw", dest="rotate_ccw", action=OrderedOpAction,
        type=positive_int, metavar="N",
        help="rotate the selected pages counter-clockwise N times (90 degrees per rotation)",
    )
    parser.add_argument(
        "--delete", action="store_true",
        help="delete the selected pages; the output contains only the pages "
             "that were not deleted",
    )
    parser.add_argument(
        "--pages", type=parse_page_spec, metavar="PAGES", default=None,
        help="pages to apply the actions to: a number (3), a list (1,3,7), "
             "ranges (2-5 or 2..5), or a combination (1,3-5,8..10); "
             "default is every page",
    )
    parser.add_argument(
        "--suffix", default=DEFAULT_SUFFIX,
        help=f"suffix appended to the output file name (default: {DEFAULT_SUFFIX})",
    )
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="explicit output path (overrides --suffix naming)",
    )
    parser.add_argument(
        "--preview", action="store_true",
        help="open the GUI: shows the result after batch actions, or opens the "
             "interactive editor when used without actions",
    )
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    operations = getattr(args, "operations", None) or []
    has_actions = bool(operations) or args.delete

    if args.input is None:
        if not args.preview:
            parser.error("an input PDF is required unless --preview is used standalone")
        preview(None, suffix=args.suffix)
        return 0

    if not args.input.is_file():
        parser.error(f"input file not found: {args.input}")

    if not has_actions:
        if args.preview:
            preview(args.input, suffix=args.suffix)
            return 0
        parser.error("no actions given - use one or more of --flip-h, --flip-v, "
                     "--rotate-cw N, --rotate-ccw N, --delete (or --preview to edit "
                     "interactively)")

    output = args.output or args.input.with_name(
        args.input.stem + args.suffix + args.input.suffix
    )
    if output.resolve() == args.input.resolve():
        parser.error("output path would overwrite the input file")

    reader = PdfReader(args.input)
    writer = PdfWriter()

    total = len(reader.pages)
    selected = args.pages or set(range(1, total + 1))
    out_of_range = sorted(p for p in selected if p > total)
    if out_of_range:
        parser.error(f"page(s) {out_of_range} out of range - the PDF has only {total} page(s)")
    if args.delete and len(selected) >= total:
        parser.error("refusing to delete every page - the output would be empty; "
                     "use --pages to select which pages to delete")

    kept = 0
    touched = 0
    for index, page in enumerate(reader.pages, start=1):
        if index in selected:
            if args.delete:
                print(f"  deleted page {index}/{total}   ", end="\r", flush=True)
                continue
            apply_operations(page, operations)
            touched += 1
        writer.add_page(page)
        kept += 1
        print(f"  processed page {index}/{total} ", end="\r", flush=True)
    print()

    # Carry metadata over, appending " (modified)" to the title.
    metadata = dict(reader.metadata or {})
    metadata["/Title"] = modified_title(metadata, args.input.stem)
    writer.add_metadata(metadata)

    with open(output, "wb") as handle:
        writer.write(handle)

    applied = ", ".join(
        f"{op.replace('_', '-')}" + (f" x{count}" if count is not None else "")
        for op, count in operations
    )
    if applied:
        print(f"Applied [{applied}] to {touched} page(s)")
    if args.delete:
        print(f"Deleted {len(selected)} page(s): {', '.join(map(str, sorted(selected)))}")
    print(f"Saved: {output} ({kept} page(s))")

    if args.preview:
        preview(output, suffix=args.suffix)
    return 0


# --------------------------------------------------------------------------
# GUI preview / editor
# --------------------------------------------------------------------------

def preview(pdf_path=None, suffix=DEFAULT_SUFFIX, auto_close_ms=None):
    """Open the GUI editor on pdf_path (or empty, ready for File > Open).

    Uses PySide6 (Qt). Falls back to a view-only tkinter window if PySide6 is
    not installed.
    """
    try:
        import pymupdf
    except ImportError:
        print("Preview requires PyMuPDF - install it with: python -m pip install pymupdf")
        return

    try:
        _preview_qt(pymupdf, pdf_path, suffix, auto_close_ms)
        return
    except ImportError:
        pass
    if pdf_path is None:
        print("The interactive editor requires PySide6 - install it with: "
              "python -m pip install PySide6-Essentials")
        return
    try:
        _preview_tk(pymupdf, pdf_path, auto_close_ms)
    except ImportError:
        print("Preview requires a GUI toolkit - install one with: "
              "python -m pip install PySide6-Essentials")


def _preview_qt(pymupdf, pdf_path, suffix=DEFAULT_SUFFIX, auto_close_ms=None):
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtGui import QAction, QKeySequence, QPixmap
    from PySide6.QtWidgets import (
        QApplication, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
        QMessageBox, QPushButton, QVBoxLayout, QWidget,
    )

    app = QApplication.instance() or QApplication(sys.argv[:1])

    class Editor(QMainWindow):
        def __init__(self):
            super().__init__()
            self.pages = []          # pypdf page objects (the in-memory document)
            self.meta = {}
            self.index = 0
            self.source_path = None
            self.save_path = None
            self.render_doc = None   # pymupdf doc rebuilt from self.pages for display

            self.page_label = QLabel("No file open - use File > Open...",
                                     alignment=Qt.AlignCenter)
            self.page_label.setMinimumSize(400, 300)
            self.status = QLabel(alignment=Qt.AlignCenter)

            self.action_buttons = []

            def action_button(text, handler):
                button = QPushButton(text)
                button.clicked.connect(handler)
                button.setFocusPolicy(Qt.NoFocus)
                self.action_buttons.append(button)
                return button

            actions_bar = QHBoxLayout()
            actions_bar.addStretch()
            actions_bar.addWidget(action_button("Flip Hori", lambda: self.apply_op("flip_h")))
            actions_bar.addWidget(action_button("Flip Vert", lambda: self.apply_op("flip_v")))
            actions_bar.addWidget(action_button("Rotate CW", lambda: self.apply_op("rotate_cw")))
            actions_bar.addWidget(action_button("Rotate CCW", lambda: self.apply_op("rotate_ccw")))
            actions_bar.addWidget(action_button("Delete Page", self.delete_current))
            actions_bar.addStretch()

            self.prev_button = QPushButton("< Prev")
            self.next_button = QPushButton("Next >")
            for button in (self.prev_button, self.next_button):
                button.setFocusPolicy(Qt.NoFocus)
                self.action_buttons.append(button)
            self.prev_button.clicked.connect(lambda: self.show_page(self.index - 1))
            self.next_button.clicked.connect(lambda: self.show_page(self.index + 1))

            nav_bar = QHBoxLayout()
            nav_bar.addStretch()
            nav_bar.addWidget(self.prev_button)
            nav_bar.addWidget(self.status)
            nav_bar.addWidget(self.next_button)
            nav_bar.addStretch()

            layout = QVBoxLayout()
            layout.addLayout(actions_bar)
            layout.addWidget(self.page_label, stretch=1)
            layout.addLayout(nav_bar)
            container = QWidget()
            container.setLayout(layout)
            self.setCentralWidget(container)

            file_menu = self.menuBar().addMenu("&File")

            def menu_action(text, shortcut, handler):
                action = QAction(text, self)
                if shortcut:
                    action.setShortcut(QKeySequence(shortcut))
                action.triggered.connect(handler)
                file_menu.addAction(action)
                return action

            menu_action("&Open...", QKeySequence.Open, self.open_dialog)
            menu_action("&Save", QKeySequence.Save, self.save_current)
            menu_action("Save &As...", QKeySequence.SaveAs, self.save_as_dialog)
            file_menu.addSeparator()
            menu_action("E&xit", "Alt+F4", self.close)

            self.update_ui_state()

        # ----- document state -----

        def load(self, path):
            path = Path(path)
            try:
                reader = PdfReader(path)
            except Exception as exc:
                QMessageBox.critical(self, "Open failed", f"Could not open {path}:\n{exc}")
                return
            self.pages = list(reader.pages)
            self.meta = dict(reader.metadata or {})
            self.source_path = path
            self.save_path = path.with_name(path.stem + suffix + path.suffix)
            self.index = 0
            self.refresh(rebuild=True)

        def document_bytes(self):
            writer = PdfWriter()
            for page in self.pages:
                writer.add_page(page)
            metadata = dict(self.meta)
            fallback = self.source_path.stem if self.source_path else "Untitled"
            metadata["/Title"] = modified_title(metadata, fallback)
            writer.add_metadata(metadata)
            buffer = io.BytesIO()
            writer.write(buffer)
            return buffer.getvalue()

        # ----- display -----

        def refresh(self, rebuild=False):
            if rebuild and self.pages:
                self.render_doc = pymupdf.open(stream=self.document_bytes(), filetype="pdf")
            self.update_ui_state()
            if not self.pages:
                return
            self.show_page(self.index)

        def show_page(self, index):
            if not self.pages:
                return
            self.index = index % len(self.pages)
            page = self.render_doc[self.index]
            screen = app.primaryScreen().availableGeometry()
            zoom = min(screen.width() * 0.6 / page.rect.width,
                       screen.height() * 0.75 / page.rect.height, 2.0)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            pixmap = QPixmap()
            pixmap.loadFromData(pix.tobytes("png"))
            self.page_label.setPixmap(pixmap)
            self.status.setText(f"Page {self.index + 1} / {len(self.pages)}")

        def update_ui_state(self):
            has_doc = bool(self.pages)
            for button in self.action_buttons:
                button.setEnabled(has_doc)
            name = self.source_path.name if self.source_path else "no file"
            self.setWindowTitle(f"PDF Transform - {name}")
            if not has_doc:
                self.status.setText("")
                self.page_label.setText("No file open - use File > Open...")

        # ----- page actions -----

        def apply_op(self, op):
            if not self.pages:
                return
            count = 1 if op in ("rotate_cw", "rotate_ccw") else None
            apply_operations(self.pages[self.index], [(op, count)])
            self.refresh(rebuild=True)

        def delete_current(self):
            if not self.pages:
                return
            if len(self.pages) == 1:
                QMessageBox.warning(self, "Delete Page",
                                    "Cannot delete the last remaining page.")
                return
            del self.pages[self.index]
            self.index = min(self.index, len(self.pages) - 1)
            self.refresh(rebuild=True)

        # ----- file menu -----

        def open_dialog(self):
            path, _filter = QFileDialog.getOpenFileName(
                self, "Open PDF", str(self.source_path.parent) if self.source_path else "",
                "PDF files (*.pdf);;All files (*.*)",
            )
            if path:
                self.load(path)

        def save_current(self):
            if not self.pages:
                return
            if self.save_path is None:
                self.save_as_dialog()
                return
            self.write_to(self.save_path)

        def save_as_dialog(self):
            if not self.pages:
                return
            start = str(self.save_path) if self.save_path else ""
            path, _filter = QFileDialog.getSaveFileName(
                self, "Save PDF As", start, "PDF files (*.pdf);;All files (*.*)",
            )
            if path:
                self.save_path = Path(path)
                self.write_to(self.save_path)

        def write_to(self, path):
            try:
                with open(path, "wb") as handle:
                    handle.write(self.document_bytes())
            except Exception as exc:
                QMessageBox.critical(self, "Save failed", f"Could not save {path}:\n{exc}")
                return
            self.statusBar().showMessage(f"Saved: {path}", 5000)

        # ----- keyboard -----

        def keyPressEvent(self, event):
            key = event.key()
            if key == Qt.Key_Left:
                self.show_page(self.index - 1)
            elif key == Qt.Key_Right:
                self.show_page(self.index + 1)
            elif key == Qt.Key_Home:
                self.show_page(0)
            elif key == Qt.Key_End:
                self.show_page(len(self.pages) - 1)
            elif key == Qt.Key_Escape:
                self.close()
            else:
                super().keyPressEvent(event)

    editor = Editor()
    if pdf_path is not None:
        editor.load(pdf_path)
    editor.show()
    if auto_close_ms is not None:
        QTimer.singleShot(auto_close_ms, app.quit)
    app.exec()


def _preview_tk(pymupdf, pdf_path, auto_close_ms=None):
    """View-only fallback for systems without PySide6."""
    import tkinter as tk

    doc = pymupdf.open(pdf_path)
    root = tk.Tk()
    root.title(f"Preview - {Path(pdf_path).name}")

    page_label = tk.Label(root)
    page_label.pack(padx=8, pady=8)
    toolbar = tk.Frame(root)
    toolbar.pack(pady=(0, 8))
    status = tk.StringVar()
    state = {"index": 0, "image": None}

    def show_page(index):
        state["index"] = index % doc.page_count
        page = doc[state["index"]]
        max_w = root.winfo_screenwidth() * 0.6
        max_h = root.winfo_screenheight() * 0.8
        zoom = min(max_w / page.rect.width, max_h / page.rect.height, 2.0)
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
        # PhotoImage reads PPM data natively, so no Pillow dependency needed.
        state["image"] = tk.PhotoImage(data=pix.tobytes("ppm"))
        page_label.configure(image=state["image"])
        status.set(f"Page {state['index'] + 1} / {doc.page_count}")

    tk.Button(toolbar, text="< Prev", command=lambda: show_page(state["index"] - 1)).pack(side=tk.LEFT, padx=4)
    tk.Label(toolbar, textvariable=status).pack(side=tk.LEFT, padx=8)
    tk.Button(toolbar, text="Next >", command=lambda: show_page(state["index"] + 1)).pack(side=tk.LEFT, padx=4)
    root.bind("<Left>", lambda _e: show_page(state["index"] - 1))
    root.bind("<Right>", lambda _e: show_page(state["index"] + 1))
    root.bind("<Home>", lambda _e: show_page(0))
    root.bind("<End>", lambda _e: show_page(doc.page_count - 1))
    root.bind("<Escape>", lambda _e: root.destroy())

    show_page(0)
    if auto_close_ms is not None:
        root.after(auto_close_ms, root.destroy)
    root.mainloop()
    doc.close()


if __name__ == "__main__":
    sys.exit(main())
