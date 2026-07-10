#!/usr/bin/env bash
#
#  One-shot installer for the NCAR MPAS-Limited-Area tool (`create_region`),
#  needed by create_regional_grid.py to cut regional meshes out of a global one.
#
#  Why a script? Upstream (MPAS-Dev/MPAS-Limited-Area) ships no
#  setup.py/pyproject.toml, so `pip install git+<url>` does NOT work. This script
#  clones it, drops a minimal local setup.py and installs it editable into the
#  conda env that is currently active.
#
#  Usage:
#      conda activate cgfd-usp-mpas      # activate the grid-tools env first
#      bash install_limited_area.sh [INSTALL_DIR]
#
#  INSTALL_DIR defaults to ~/tools/MPAS-Limited-Area
#
set -euo pipefail

REPO_URL="https://github.com/MPAS-Dev/MPAS-Limited-Area.git"
INSTALL_DIR="${1:-$HOME/tools/MPAS-Limited-Area}"

echo "==> Target install dir: $INSTALL_DIR"

# --- Sanity check: are we in the grid-tools env? -----------------------------
if ! python -c "import jigsawpy, mpas_tools" >/dev/null 2>&1; then
    echo "WARNING: 'jigsawpy'/'mpas_tools' not importable in the current python."
    echo "         You probably forgot to: conda activate cgfd-usp-mpas"
    read -r -p "Continue anyway? [y/N] " ans || ans="N"   # || ans=N: avoid set -e exit on EOF (non-interactive)
    [ "${ans:-N}" = "y" ] || [ "${ans:-N}" = "Y" ] || { echo "Aborted."; exit 1; }
fi

# --- 1) Clone (or update) ----------------------------------------------------
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "==> Already cloned; updating with git pull ..."
    git -C "$INSTALL_DIR" pull --ff-only || echo "    (pull skipped/failed; keeping existing checkout)"
else
    echo "==> Cloning $REPO_URL ..."
    mkdir -p "$(dirname "$INSTALL_DIR")"
    git clone "$REPO_URL" "$INSTALL_DIR"
fi

# --- 2) Minimal local setup.py (only if upstream still has none) --------------
if [ ! -f "$INSTALL_DIR/setup.py" ] && [ ! -f "$INSTALL_DIR/pyproject.toml" ]; then
    echo "==> Writing a minimal local setup.py (upstream has no packaging) ..."
    cat > "$INSTALL_DIR/setup.py" <<'PY'
"""Minimal LOCAL packaging so MPAS-Limited-Area is pip-installable.
Not part of the upstream repo; added by usp-utils install_limited_area.sh."""
from setuptools import setup

setup(
    name="mpas-limited-area",
    version="0.0.0",
    description="NCAR MPAS-Limited-Area regional grid tool (local packaging)",
    packages=["limited_area"],
    scripts=["create_region"],
    install_requires=["numpy", "netCDF4"],
)
PY
else
    echo "==> Packaging already present; not overwriting."
fi

# --- 3) Editable install into the active env ---------------------------------
echo "==> python -m pip install -e $INSTALL_DIR"
# Use 'python -m pip' so it installs into the same interpreter validated above
# (a bare 'pip' on PATH may point at a different Python/env).
python -m pip install -e "$INSTALL_DIR"

# --- 4) Verify ---------------------------------------------------------------
echo "==> Verifying ..."
python -c "import limited_area; print('    import limited_area OK')"
if command -v create_region >/dev/null 2>&1; then
    echo "    create_region found at: $(command -v create_region)"
    echo ""
    echo "Done. You can now run create_regional_grid.py."
else
    echo "ERROR: create_region not on PATH after install. Check the pip output above."
    exit 1
fi
