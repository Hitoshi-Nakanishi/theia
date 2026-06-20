# cython: language_level=3, boundscheck=False, wraparound=False
"""Cython-compiled hot helpers for ArrowSheetModel.

build_v_flat  -- construct row-major flat list at load time with C-level int
                 arithmetic (no Python boxing of r, c, n_cols).
get_display   -- display-string lookup from flat list with typed C locals.
"""


def build_v_flat(list cols, int n_rows, int n_cols):
    """Build a row-major flat list from column-major ``cols`` (list of lists).

    Pure Python equivalent:
        [cols[c][r] for r in range(n_rows) for c in range(n_cols)]

    With Cython typed C locals the inner ``r * n_cols + c`` multiply and the
    list assignment all run at C speed — no Python int boxing per iteration.
    """
    cdef int r, c
    cdef list flat = [None] * (n_rows * n_cols)
    for r in range(n_rows):
        for c in range(n_cols):
            flat[r * n_cols + c] = cols[c][r]
    return flat


def get_display(list v_flat, int r, int c, int n_cols):
    """Return the display string for cell (r, c) from the flat list."""
    cdef int idx = r * n_cols + c
    v = v_flat[idx]
    return v if v else ""
