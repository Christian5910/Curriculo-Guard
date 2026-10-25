#!/usr/bin/env bash
# Compila o CurriculoGuard.exe (lançador) a partir do Linux, com o MinGW-w64.
#   Ubuntu/Debian:  sudo apt install gcc-mingw-w64-x86-64 binutils-mingw-w64-x86-64
# No Windows não é preciso compilar: o CurriculoGuard.exe já compilado está nesta pasta.
set -euo pipefail
cd "$(dirname "$0")"
x86_64-w64-mingw32-windres lancador.rc -O coff -o lancador.res.o
x86_64-w64-mingw32-gcc -O2 -s -mwindows -municode -static -o CurriculoGuard.exe lancador.c lancador.res.o -lshell32
rm -f lancador.res.o
echo "Gerado: $(pwd)/CurriculoGuard.exe ($(du -h CurriculoGuard.exe | cut -f1))"
