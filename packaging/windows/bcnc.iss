#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{73AC3E4B-9142-46B5-A21B-B8F67908BE8B}
AppName=Foil Studio Classic
AppVersion={#AppVersion}
AppPublisher=Foil Studio contributors; based on bCNC
AppPublisherURL=https://github.com/pratanczuk/FoilStudio
DefaultDirName={localappdata}\Programs\bCNC
DefaultGroupName=Foil Studio Classic
DisableProgramGroupPage=yes
OutputDir=..\..\release
OutputBaseFilename=FoilStudio-Classic-{#AppVersion}-windows-x64-setup
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
Name: "{autoprograms}\Foil Studio Classic"; Filename: "{app}\bCNC.exe"
Name: "{autodesktop}\Foil Studio Classic"; Filename: "{app}\bCNC.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\bCNC.exe"; Description: "Launch Foil Studio Classic"; Flags: nowait postinstall skipifsilent
