; Instalador de Windows para Vortex Studio (Inno Setup 6).
;
; Empaca lo que dejó PyInstaller en dist\vortex-studio\ y crea la entrada en
; el menú Inicio. Se instala por usuario, sin pedir permisos de administrador;
; quien quiera instalarlo para todos lo puede elegir en el primer paso.
;
; Compilar: ISCC.exe /DAppVersion=0.1.0b1 empaquetado\windows\vortex-studio.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1C3A52-8E0B-4D7A-9C21-5B7E2A94D013}
AppName=Vortex Studio
AppVersion={#AppVersion}
AppVerName=Vortex Studio {#AppVersion}
AppPublisher=MikePianoXD777
AppPublisherURL=https://github.com/MikePianoXD777/vortex-studio
AppSupportURL=https://github.com/MikePianoXD777/vortex-studio/issues
DefaultDirName={autopf}\Vortex Studio
DefaultGroupName=Vortex Studio
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\..\dist
OutputBaseFilename=VortexStudio-{#AppVersion}-windows-x64-instalador
SetupIconFile=..\..\src\vortex_studio\assets\vortex-studio.ico
UninstallDisplayIcon={app}\vortex-studio.exe
LicenseFile=..\..\LICENSE
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\..\dist\vortex-studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Vortex Studio"; Filename: "{app}\vortex-studio.exe"
Name: "{group}\{cm:UninstallProgram,Vortex Studio}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\Vortex Studio"; Filename: "{app}\vortex-studio.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\vortex-studio.exe"; Description: "{cm:LaunchProgram,Vortex Studio}"; Flags: nowait postinstall skipifsilent
