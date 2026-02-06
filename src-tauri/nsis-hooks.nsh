!macro NSIS_HOOK_PREINSTALL
  nsExec::ExecToLog 'taskkill /F /T /IM "sidecar-x86_64-pc-windows-msvc.exe"'
  Sleep 1000
!macroend
