Set objShell = CreateObject("WScript.Shell")
Set objFSO = CreateObject("Scripting.FileSystemObject")
strPath = objFSO.GetParentFolderName(WScript.ScriptFullName)

' Si el entorno (venv + dependencias) todavia no esta listo en esta
' computadora, mostramos una ventana visible con el progreso de la
' instalacion (tarda 1-2 minutos la primera vez). Si ya esta listo,
' arrancamos directo y oculto, como uso normal del dia a dia.
marcador = strPath & "\venv\.deps_ok"

If objFSO.FileExists(marcador) Then
    objShell.Run """" & strPath & "\iniciar_facturacion.bat""", 0, False
Else
    objShell.Run "cmd /c """ & strPath & "\iniciar_facturacion.bat""", 1, False
End If
