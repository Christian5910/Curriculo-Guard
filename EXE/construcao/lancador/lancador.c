/*
 * Lançador do Currículo Guard (Windows).
 *
 * O que ele faz, em ordem:
 *   1. descobre a pasta onde o próprio CurriculoGuard.exe está;
 *   2. escolhe a pasta de dados: "dados" ao lado do programa (modo portátil) ou
 *      "Documentos\Curriculo Guard" quando o programa foi instalado (existe Desinstalar.exe);
 *   3. abre runtime\pythonw.exe (o Python embutido, sem janela preta) com app\app.py.
 *
 * Não instala nada, não mexe no registro e não precisa de permissão de administrador.
 * Compilação: ver compilar_lancador.sh (MinGW-w64, a partir do Linux).
 */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <shlobj.h>
#include <stdio.h>
#include <wchar.h>

#define CAP 1024

static void erro(const wchar_t *mensagem) {
    MessageBoxW(NULL, mensagem, L"Currículo Guard", MB_OK | MB_ICONERROR);
}

static int existe(const wchar_t *caminho) {
    return GetFileAttributesW(caminho) != INVALID_FILE_ATTRIBUTES;
}

int WINAPI wWinMain(HINSTANCE instancia, HINSTANCE anterior, PWSTR argumentos, int exibicao) {
    wchar_t self[CAP], pasta[CAP], python[CAP], script[CAP], dados[CAP], comando[CAP * 3], aviso[CAP * 2];
    wchar_t tcl[CAP], tk[CAP], instalador[CAP], documentos[CAP];
    DWORD n = GetModuleFileNameW(NULL, self, CAP);
    wchar_t *barra;

    if (n == 0 || n >= CAP) { erro(L"Não foi possível descobrir a pasta do programa."); return 1; }
    wcscpy(pasta, self);
    barra = wcsrchr(pasta, L'\\');
    if (barra) *barra = 0;

    _snwprintf(python, CAP, L"%ls\\runtime\\pythonw.exe", pasta);
    _snwprintf(script, CAP, L"%ls\\app\\app.py", pasta);
    if (!existe(python) || !existe(script)) {
        _snwprintf(aviso, CAP * 2, L"Os arquivos do programa não foram encontrados em:\n%ls\n\n"
                   L"Não mova o CurriculoGuard.exe para fora da sua pasta: ele precisa das pastas \"runtime\" e \"app\" ao lado dele.", pasta);
        erro(aviso);
        return 1;
    }

    /* Instalado (o instalador cria o Desinstalar.exe): dados em Documentos. Portátil: dados ao lado do programa. */
    _snwprintf(instalador, CAP, L"%ls\\Desinstalar.exe", pasta);
    if (existe(instalador) && SUCCEEDED(SHGetFolderPathW(NULL, CSIDL_PERSONAL, NULL, 0, documentos))) {
        _snwprintf(dados, CAP, L"%ls\\Curriculo Guard", documentos);
    } else {
        _snwprintf(dados, CAP, L"%ls\\dados", pasta);
    }
    CreateDirectoryW(dados, NULL);

    /* Tcl/Tk do Python embutido (a interface gráfica) e codificação UTF-8 para ler e gravar arquivos. */
    _snwprintf(tcl, CAP, L"%ls\\runtime\\tcl\\tcl8.6", pasta);
    _snwprintf(tk, CAP, L"%ls\\runtime\\tcl\\tk8.6", pasta);
    SetEnvironmentVariableW(L"TCL_LIBRARY", tcl);
    SetEnvironmentVariableW(L"TK_LIBRARY", tk);
    SetEnvironmentVariableW(L"PYTHONUTF8", L"1");

    if (argumentos && argumentos[0])
        _snwprintf(comando, CAP * 3, L"\"%ls\" \"%ls\" %ls", python, script, argumentos);
    else
        _snwprintf(comando, CAP * 3, L"\"%ls\" \"%ls\"", python, script);

    STARTUPINFOW inicio;
    PROCESS_INFORMATION processo;
    ZeroMemory(&inicio, sizeof(inicio));
    inicio.cb = sizeof(inicio);
    ZeroMemory(&processo, sizeof(processo));
    if (!CreateProcessW(python, comando, NULL, NULL, FALSE, 0, NULL, dados, &inicio, &processo)) {
        _snwprintf(aviso, CAP * 2, L"Não foi possível abrir o Python do programa (erro %lu).\n\n%ls", GetLastError(), python);
        erro(aviso);
        return 1;
    }
    CloseHandle(processo.hThread);
    CloseHandle(processo.hProcess);
    return 0;
}
