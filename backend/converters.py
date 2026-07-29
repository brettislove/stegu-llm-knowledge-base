"""
File conversion hub for the knowledge base backend.
Handles translation of multiple formats into Claude-digestible markdown or raw PDF.
"""
import base64
import io
import mammoth
import pandas as pd

# Per Design Notes / SCHEMA.md §3: images get no OCR/vision pass — the
# generated page just links to the paired image file. So these extensions
# don't get their pixels extracted or sent to Claude's vision input; the
# LLM only sees a short placeholder telling it what kind of file this is,
# same shape as every other convert_file() branch (a markdown-ish string).
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif"}

def convert_file(filename: str, file_base64: str) -> tuple[str | None, str | None]:
    """
    Inspects file extension, decodes the base64 string, and extracts contents.
    
    Returns:
        tuple: (pdf_base64, markdown_text)
        Exactly one of these will be populated; the other will be None.
        
    Raises:
        ValueError: For unsupported formats, decoding errors, or corrupted files.
    """
    ext = filename.lower().split('.')[-1]
    
    try:
        file_bytes = base64.b64decode(file_base64)
    except Exception as e:
        raise ValueError(f"Malformed base64 encoding: {str(e)}")

    # 1. Native PDF Pass-through
    if ext == "pdf":
        return file_base64, None

    # 2. Raw Text / Markdown files
    elif ext in ("md", "markdown", "txt"):
        try:
            return None, file_bytes.decode("utf-8")
        except Exception as e:
            raise ValueError(f"Failed to decode text file as UTF-8: {str(e)}")

    # 3. Microsoft Word (.docx) via Mammoth
    elif ext == "docx":
        try:
            result = mammoth.convert_to_markdown(io.BytesIO(file_bytes))
            return None, result.value
        except Exception as e:
            raise ValueError(f"Failed to convert Word (.docx) document: {str(e)}")

    # 4. Microsoft Excel (.xlsx) via Pandas + openpyxl
    elif ext == "xlsx":
        try:
            excel_file = pd.ExcelFile(io.BytesIO(file_bytes), engine="openpyxl")
            markdown_sheets = []
            
            for sheet_name in excel_file.sheet_names:
                df = pd.read_excel(excel_file, sheet_name=sheet_name)
                markdown_sheets.append(f"## Sheet: {sheet_name}\n")
                # df.to_markdown() requires 'tabulate' dependency
                markdown_sheets.append(df.to_markdown(index=False))
                markdown_sheets.append("\n")
                
            return None, "\n".join(markdown_sheets)
        except Exception as e:
            raise ValueError(f"Failed to parse Excel (.xlsx) workbook: {str(e)}")

    # 5. CSV Files via Pandas
    elif ext == "csv":
        try:
            df = pd.read_csv(io.BytesIO(file_bytes))
            return None, df.to_markdown(index=False)
        except Exception as e:
            raise ValueError(f"Failed to parse CSV file: {str(e)}")

    # 6. Images — no OCR/vision pass (see IMAGE_EXTENSIONS note above).
    elif ext in IMAGE_EXTENSIONS:
        return None, (
            f"[Obrázek: {filename}]\n\n"
            "Toto je obrázek bez textového obsahu — nebyl proveden OCR/vision "
            "rozbor (dle SCHEMA.md §3). Stránka by měla pouze odkazovat na "
            "přiložený soubor obrázku, ne popisovat jeho vizuální obsah."
        )

    else:
        raise ValueError(f"Unsupported file type extension: .{ext}")