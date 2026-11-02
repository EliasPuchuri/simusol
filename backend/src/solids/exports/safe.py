"""Neutralise spreadsheet formulas in exported text.

Excel and LibreOffice evaluate a cell that starts with ``=``, ``+``, ``-`` or ``@`` (or a tab / carriage return)
as a formula. Anything a user can type or upload (file names, period labels, comments, reviewer names, methods)
is exported through ``text_cell``. Numbers are never passed through it: a negative number must keep its sign.
"""

_DANGEROUS = ("=", "+", "-", "@", "\t", "\r")


def text_cell(value: str) -> str:
    return "'" + value if value.startswith(_DANGEROUS) else value
