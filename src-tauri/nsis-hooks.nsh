!macro NSIS_HOOK_PREINSTALL
  ; Kill the sidecar process (Python backend)
  nsExec::ExecToLog 'taskkill /F /T /IM "sidecar.exe"'
  ; Kill the main app process
  nsExec::ExecToLog 'taskkill /F /T /IM "Explify.exe"'
  ; Wait for processes to fully terminate
  Sleep 2000
!macroend
