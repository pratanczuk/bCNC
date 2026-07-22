#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{73AC3E4B-9142-46B5-A21B-B8F67908BE8B}
AppName=bCNC
AppVersion={#AppVersion}
AppPublisher=bCNC contributors
AppPublisherURL=https://github.com/vlachoudis/bCNC
DefaultDirName={localappdata}\Programs\bCNC
DefaultGroupName=bCNC
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=bCNC-{#AppVersion}-windows-x64-setup
SetupIconFile=..\..\bCNC\bCNC.ico
UninstallDisplayIcon={app}\bCNC.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Files]
Source: "..\..\dist\bCNC\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\bCNC"; Filename: "{app}\bCNC.exe"
Name: "{autodesktop}\bCNC"; Filename: "{app}\bCNC.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\bCNC.exe"; Description: "Launch bCNC"; Flags: nowait postinstall skipifsilent
