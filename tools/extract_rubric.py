#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Extrae las páginas 33–36 (índices 32–35) del B2 First Handbook oficial.

Uso manual de desarrollo (NO importado por server.py):
  uv run --with pypdf python tools/extract_rubric.py
"""
from pypdf import PdfReader

PDF_PATH = "/home/juan/Descargas/b2-first/05-Handbooks/b2-first-handbook.pdf"

if __name__ == "__main__":
    r = PdfReader(PDF_PATH)
    for i in (32, 33, 34, 35):
        print("=== PDF PAGE", i + 1)
        print(r.pages[i].extract_text())
