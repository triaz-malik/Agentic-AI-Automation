import time
from pathlib import Path

import pythoncom
import win32com.client


SUPPORTED_EXTENSIONS = {".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"}


def start_office_apps():
    """Start Word, Excel, and PowerPoint COM applications."""
    pythoncom.CoInitialize()

    word = win32com.client.Dispatch("Word.Application")
    excel = win32com.client.Dispatch("Excel.Application")
    powerpoint = win32com.client.Dispatch("PowerPoint.Application")

    word.Visible = False
    excel.Visible = False
    powerpoint.Visible = True  # safer for PowerPoint COM

    word.DisplayAlerts = 0
    excel.DisplayAlerts = False

    return word, excel, powerpoint


def stop_office_apps(word, excel, powerpoint):
    """Close Word, Excel, and PowerPoint safely."""
    try:
        if word is not None:
            word.Quit()
    except Exception:
        pass

    try:
        if excel is not None:
            excel.Quit()
    except Exception:
        pass

    try:
        if powerpoint is not None:
            powerpoint.Quit()
    except Exception:
        pass

    try:
        pythoncom.CoUninitialize()
    except Exception:
        pass


def convert_word(word, input_path: str, output_path: str) -> bool:
    """Convert a Word file to PDF."""
    doc = None
    try:
        doc = word.Documents.Open(str(input_path), ReadOnly=True)
        doc.SaveAs(str(output_path), FileFormat=17)  # 17 = PDF
        return True
    except Exception as e:
        print(f"[WORD ERROR] {input_path} -> {e}")
        return False
    finally:
        try:
            if doc is not None:
                doc.Close(False)
        except Exception:
            pass


def convert_excel(excel, input_path: str, output_path: str) -> bool:
    """Convert an Excel file to PDF."""
    wb = None
    try:
        wb = excel.Workbooks.Open(str(input_path), ReadOnly=True)

        # Optional: fit each sheet to page width
        for sheet in wb.Worksheets:
            try:
                sheet.PageSetup.Zoom = False
                sheet.PageSetup.FitToPagesWide = 1
                sheet.PageSetup.FitToPagesTall = False
            except Exception:
                pass

        wb.ExportAsFixedFormat(0, str(output_path))  # 0 = PDF
        return True
    except Exception as e:
        print(f"[EXCEL ERROR] {input_path} -> {e}")
        return False
    finally:
        try:
            if wb is not None:
                wb.Close(False)
        except Exception:
            pass


def convert_powerpoint(powerpoint, input_path: str, output_path: str) -> bool:
    """Convert a PowerPoint file to PDF."""
    presentation = None
    try:
        presentation = powerpoint.Presentations.Open(
            str(input_path),
            ReadOnly=True,
            Untitled=False,
            WithWindow=False
        )
        presentation.SaveAs(str(output_path), 32)  # 32 = PDF
        return True
    except Exception as e:
        print(f"[POWERPOINT ERROR] {input_path} -> {e}")
        return False
    finally:
        try:
            if presentation is not None:
                presentation.Close()
        except Exception:
            pass


def bulk_convert(folder_path: str, restart_every: int = 100, skip_existing: bool = True):
    """
    Convert all supported Office files in a folder and subfolders to PDF.

    Args:
        folder_path: Root folder to scan.
        restart_every: Restart Office apps after this many processed files.
        skip_existing: Skip files if corresponding PDF already exists.
    """
    folder = Path(folder_path)

    if not folder.exists():
        print(f"Folder not found: {folder}")
        return

    word, excel, powerpoint = start_office_apps()

    processed = 0
    success = 0
    failed = 0
    skipped = 0

    try:
        for file_path in folder.rglob("*"):
            if not file_path.is_file():
                continue

            ext = file_path.suffix.lower()
            if ext not in SUPPORTED_EXTENSIONS:
                continue

            output_path = file_path.with_suffix(".pdf")

            if skip_existing and output_path.exists():
                print(f"[SKIPPED] PDF already exists: {output_path.name}")
                skipped += 1
                continue

            print(f"[PROCESSING] {file_path}")

            ok = False

            if ext in {".doc", ".docx"}:
                ok = convert_word(word, str(file_path), str(output_path))

            elif ext in {".xls", ".xlsx"}:
                ok = convert_excel(excel, str(file_path), str(output_path))

            elif ext in {".ppt", ".pptx"}:
                ok = convert_powerpoint(powerpoint, str(file_path), str(output_path))

            processed += 1

            if ok:
                success += 1
                print(f"[DONE] {output_path}")
            else:
                failed += 1

            # Restart Office apps periodically for better stability
            if processed % restart_every == 0:
                print(f"[INFO] Restarting Office apps after {processed} files...")
                stop_office_apps(word, excel, powerpoint)
                time.sleep(2)
                word, excel, powerpoint = start_office_apps()

    finally:
        stop_office_apps(word, excel, powerpoint)

    print("\n===== SUMMARY =====")
    print(f"Processed : {processed}")
    print(f"Successful: {success}")
    print(f"Failed    : {failed}")
    print(f"Skipped   : {skipped}")


if __name__ == "__main__":
    # CHANGE THIS PATH
    folder_path = r"C:\Working\Telecom RAG\5G Hedex Files"

    bulk_convert(
        folder_path=folder_path,
        restart_every=100,
        skip_existing=True
    )