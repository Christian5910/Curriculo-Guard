; Instalador do Currículo Guard (NSIS). Gera EXE\CurriculoGuard-Setup.exe.
; Compilar:  makensis instalador.nsi   (ou: python EXE/construcao/construir.py)
;
; Instala para o usuário atual, SEM pedir permissão de administrador:
;   programa  ->  %LOCALAPPDATA%\Programs\Curriculo Guard
;   dados     ->  Documentos\Curriculo Guard (criada pelo programa; o desinstalador NÃO apaga)
Unicode true
!define NOME "Currículo Guard"
!define PASTA "Curriculo Guard"
!define VERSAO "2.11"
!define CHAVE_DESINSTALAR "Software\Microsoft\Windows\CurrentVersion\Uninstall\CurriculoGuard"

!include "MUI2.nsh"

Name "${NOME}"
OutFile "..\..\CurriculoGuard-Setup.exe"
InstallDir "$LOCALAPPDATA\Programs\${PASTA}"
InstallDirRegKey HKCU "Software\CurriculoGuard" "Pasta"
RequestExecutionLevel user
SetCompressor /SOLID lzma
BrandingText "${NOME} ${VERSAO}"
ShowInstDetails nevershow

!define MUI_ICON "..\..\..\assets\icon.ico"
!define MUI_UNICON "..\..\..\assets\icon.ico"
!define MUI_ABORTWARNING
!define MUI_FINISHPAGE_RUN "$INSTDIR\CurriculoGuard.exe"
!define MUI_FINISHPAGE_RUN_TEXT "Abrir o ${NOME} agora"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_COMPONENTS
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "PortugueseBR"

VIProductVersion "${VERSAO}.0.0"
VIAddVersionKey /LANG=1046 "ProductName" "${NOME}"
VIAddVersionKey /LANG=1046 "FileDescription" "Instalador do ${NOME}"
VIAddVersionKey /LANG=1046 "FileVersion" "${VERSAO}"
VIAddVersionKey /LANG=1046 "LegalCopyright" "Currículo Guard"

Section "${NOME} (obrigatório)" SecPrograma
  SectionIn RO
  ; Atualização: remove só o código e as bibliotecas da versão anterior (os seus dados ficam em Documentos).
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  SetOutPath "$INSTDIR"
  File /r "..\..\CurriculoGuard-Portatil\*.*"
  WriteUninstaller "$INSTDIR\Desinstalar.exe"

  CreateShortcut "$SMPROGRAMS\${NOME}.lnk" "$INSTDIR\CurriculoGuard.exe" "" "$INSTDIR\CurriculoGuard.exe" 0

  WriteRegStr HKCU "Software\CurriculoGuard" "Pasta" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "DisplayName" "${NOME}"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "DisplayVersion" "${VERSAO}"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "Publisher" "Currículo Guard"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "DisplayIcon" "$INSTDIR\CurriculoGuard.exe"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "InstallLocation" "$INSTDIR"
  WriteRegStr HKCU "${CHAVE_DESINSTALAR}" "UninstallString" '"$INSTDIR\Desinstalar.exe"'
  WriteRegDWORD HKCU "${CHAVE_DESINSTALAR}" "NoModify" 1
  WriteRegDWORD HKCU "${CHAVE_DESINSTALAR}" "NoRepair" 1
SectionEnd

Section "Atalho na Área de Trabalho" SecAtalho
  CreateShortcut "$DESKTOP\${NOME}.lnk" "$INSTDIR\CurriculoGuard.exe" "" "$INSTDIR\CurriculoGuard.exe" 0
SectionEnd

LangString DESC_Programa ${LANG_PORTUGUESEBR} "O programa e tudo o que ele precisa para funcionar."
LangString DESC_Atalho ${LANG_PORTUGUESEBR} "Cria um atalho do ${NOME} na Área de Trabalho."
!insertmacro MUI_FUNCTION_DESCRIPTION_BEGIN
  !insertmacro MUI_DESCRIPTION_TEXT ${SecPrograma} $(DESC_Programa)
  !insertmacro MUI_DESCRIPTION_TEXT ${SecAtalho} $(DESC_Atalho)
!insertmacro MUI_FUNCTION_DESCRIPTION_END

Section "Uninstall"
  Delete "$SMPROGRAMS\${NOME}.lnk"
  Delete "$DESKTOP\${NOME}.lnk"
  RMDir /r "$INSTDIR\app"
  RMDir /r "$INSTDIR\runtime"
  Delete "$INSTDIR\CurriculoGuard.exe"
  Delete "$INSTDIR\LEIA-ME.txt"
  Delete "$INSTDIR\Desinstalar.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "${CHAVE_DESINSTALAR}"
  DeleteRegKey HKCU "Software\CurriculoGuard"
  MessageBox MB_OK|MB_ICONINFORMATION "O ${NOME} foi removido.$\r$\n$\r$\nOs seus resultados continuam em Documentos\Curriculo Guard (não foram apagados)." /SD IDOK
SectionEnd
