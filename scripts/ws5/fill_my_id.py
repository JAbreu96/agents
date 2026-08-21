#!/usr/bin/env python3
"""Stamp your NYS ID (or last-4 SSN) onto every WS-5 form in this folder.

Run it yourself so the number never leaves your machine:

    python3 fill_my_id.py

Requires pypdf:  python3 -m pip install pypdf
"""
import glob
import os
import sys
from getpass import getpass

try:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import BooleanObject, NameObject, TextStringObject
except ImportError:
    sys.exit("Missing dependency. Run:  python3 -m pip install pypdf")

HERE = os.path.dirname(os.path.abspath(__file__))

# The ID boxes are 14x18pt and hold a single digit. 10pt fits with room to
# spare; we set it explicitly because pypdf renders an "auto" size as a
# hardcoded 12pt, which would overflow and be clipped.
ID_FONT = "/Helvetica 10 Tf 0 g"


def main():
    print("WS-5 ID stamper")
    print("The form takes EITHER your 9-digit NYS ID OR the last 4 of your SSN.")
    print("Input is hidden as you type.\n")

    nyid = getpass("9-digit NYS ID (press Enter to skip): ").strip()
    ssn4 = ""
    if not nyid:
        ssn4 = getpass("Last 4 digits of SSN: ").strip()

    fields = {}
    if nyid:
        digits = [c for c in nyid if c.isdigit()]
        if len(digits) != 9:
            sys.exit(f"NYS ID must be exactly 9 digits (got {len(digits)}).")
        for i, ch in enumerate(digits, start=1):
            fields[f"Contact_NYIDNumber{i}"] = ch
    elif ssn4:
        digits = [c for c in ssn4 if c.isdigit()]
        if len(digits) != 4:
            sys.exit(f"Need exactly 4 digits (got {len(digits)}).")
        # Form labels these boxes SSN6..SSN9.
        for i, ch in zip(range(6, 10), digits):
            fields[f"Contact_SSN{i}"] = ch
    else:
        sys.exit("Nothing entered - no changes made.")

    pdfs = sorted(glob.glob(os.path.join(HERE, "WS5_week_ending_*.pdf")))
    if not pdfs:
        sys.exit("No WS5_week_ending_*.pdf files found next to this script.")

    for path in pdfs:
        reader = PdfReader(path)
        writer = PdfWriter(clone_from=reader)

        for page in writer.pages:
            for annot in (page.get("/Annots") or []):
                obj = annot.get_object()
                name = obj.get("/T")
                if name is not None and str(name) in fields:
                    obj[NameObject("/DA")] = TextStringObject(ID_FONT)
            writer.update_page_form_field_values(
                page, fields, auto_regenerate=True)

        acro = writer._root_object.get("/AcroForm")
        if acro is not None:
            acro.get_object()[NameObject("/NeedAppearances")] = \
                BooleanObject(False)

        with open(path, "wb") as fh:
            writer.write(fh)
        print("  stamped", os.path.basename(path))

    print(f"\nDone - {len(pdfs)} forms updated in place.")
    print("Remaining by hand: sign/date if your office asks, and add anything")
    print("to the 'Other Work Search Activities' box (especially week 5/17).")


if __name__ == "__main__":
    main()
