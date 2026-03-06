from __future__ import annotations

import io
import tempfile
from pathlib import Path

from fpdf import FPDF

from bot.keyboards.inline import CATEGORIES

ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"


class LogPDF(FPDF):
    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title
        font_dir = ASSETS_DIR
        self.add_font("DejaVu", "", str(font_dir / "DejaVuSans.ttf"))
        self.add_font("DejaVu", "B", str(font_dir / "DejaVuSans-Bold.ttf"))
        self.set_auto_page_break(auto=True, margin=15)

    def header(self) -> None:
        self.set_font("DejaVu", "B", 12)
        self.cell(0, 10, self._title, align="C", new_x="LMARGIN", new_y="NEXT")
        self.ln(2)

    def footer(self) -> None:
        self.set_y(-15)
        self.set_font("DejaVu", "", 8)
        self.cell(0, 10, f"Стр. {self.page_no()}/{{nb}}", align="C")


def build_board_pdf(
    serial: str,
    logs: list[dict],
    photo_paths: dict[int, list[str]],
) -> bytes:
    """Generate PDF for a single board history.

    Args:
        serial: Board serial number.
        logs: List of work log dicts (with full_name, position, category, etc.).
        photo_paths: Mapping log_id -> list of local file paths for photos.

    Returns:
        PDF content as bytes.
    """
    pdf = LogPDF(f"История борта {serial}")
    pdf.alias_nb_pages()
    pdf.add_page()

    for entry in logs:
        cat_name = CATEGORIES.get(entry["category"], entry["category"])
        author = entry.get("full_name", "")
        position = entry.get("position", "")
        author_str = f" | {author}" if author else ""
        if position:
            author_str += f" ({position})"

        # Entry header
        pdf.set_font("DejaVu", "B", 10)
        pdf.cell(
            0, 7,
            f"#{entry['id']} | {entry['created_at']}{author_str}",
            new_x="LMARGIN", new_y="NEXT",
        )

        # Category
        pdf.set_font("DejaVu", "", 9)
        pdf.cell(0, 6, f"Категория: {cat_name}", new_x="LMARGIN", new_y="NEXT")

        # Description
        pdf.multi_cell(0, 5, f"Описание: {entry['description']}")

        # Photos
        paths = photo_paths.get(entry["id"], [])
        if paths:
            pdf.set_font("DejaVu", "", 8)
            pdf.cell(0, 5, f"Фото ({len(paths)}):", new_x="LMARGIN", new_y="NEXT")
            for p in paths:
                try:
                    # Fit photo within page width with some margin
                    available_w = pdf.w - pdf.l_margin - pdf.r_margin
                    img_w = min(available_w, 80)
                    pdf.image(p, w=img_w)
                    pdf.ln(3)
                except Exception:
                    pdf.cell(0, 5, f"  [не удалось загрузить фото]", new_x="LMARGIN", new_y="NEXT")

        # Separator line
        pdf.set_draw_color(200, 200, 200)
        y = pdf.get_y()
        pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
        pdf.ln(5)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()


def build_full_pdf(
    all_logs: dict[str, list[dict]],
    photo_paths: dict[int, list[str]],
) -> bytes:
    """Generate PDF for all boards.

    Args:
        all_logs: Mapping serial -> list of log dicts.
        photo_paths: Mapping log_id -> list of local file paths.
    """
    pdf = LogPDF("Журнал техобслуживания БПЛА")
    pdf.alias_nb_pages()

    for serial, logs in all_logs.items():
        pdf.add_page()
        pdf.set_font("DejaVu", "B", 11)
        pdf.cell(0, 8, f"Борт: {serial}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)

        for entry in logs:
            cat_name = CATEGORIES.get(entry["category"], entry["category"])
            author = entry.get("full_name", "")
            position = entry.get("position", "")
            author_str = f" | {author}" if author else ""
            if position:
                author_str += f" ({position})"

            pdf.set_font("DejaVu", "B", 10)
            pdf.cell(
                0, 7,
                f"#{entry['id']} | {entry['created_at']}{author_str}",
                new_x="LMARGIN", new_y="NEXT",
            )
            pdf.set_font("DejaVu", "", 9)
            pdf.cell(0, 6, f"Категория: {cat_name}", new_x="LMARGIN", new_y="NEXT")
            pdf.multi_cell(0, 5, f"Описание: {entry['description']}")

            paths = photo_paths.get(entry["id"], [])
            if paths:
                pdf.set_font("DejaVu", "", 8)
                pdf.cell(0, 5, f"Фото ({len(paths)}):", new_x="LMARGIN", new_y="NEXT")
                for p in paths:
                    try:
                        available_w = pdf.w - pdf.l_margin - pdf.r_margin
                        img_w = min(available_w, 80)
                        pdf.image(p, w=img_w)
                        pdf.ln(3)
                    except Exception:
                        pdf.cell(
                            0, 5, f"  [не удалось загрузить фото]",
                            new_x="LMARGIN", new_y="NEXT",
                        )

            pdf.set_draw_color(200, 200, 200)
            y = pdf.get_y()
            pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
            pdf.ln(5)

    buf = io.BytesIO()
    pdf.output(buf)
    return buf.getvalue()
