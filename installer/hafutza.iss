; Hafutza Typing - Windows installer (Inno Setup 6). Built by .github/workflows/build.yml:
;   ISCC.exe installer\hafutza.iss      (expects ..\dist\HafutzaTyping and ..\build\hafutza.ico)
#define MyAppName "Hafutza Typing"
#ifndef MyAppVersion
  #define MyAppVersion "1.0"
#endif

[Setup]
AppId={{8E3B6F7A-2C1D-4B8E-9F21-6A5D3C7E1B42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Hafutza Typing
DefaultDirName={autopf}\Hafutza Typing
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\Output
OutputBaseFilename=HafutzaTyping-Setup
SetupIconFile=..\build\hafutza.ico
UninstallDisplayIcon={app}\HafutzaTyping.exe
Compression=lzma2/fast
SolidCompression=no
LZMANumBlockThreads=4
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
ExtraDiskSpaceRequired=3200000000

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a Hafutza Typing icon on the desktop"

[Files]
Source: "..\dist\HafutzaTyping\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\HafutzaTyping.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\HafutzaTyping.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\HafutzaTyping.exe"; Description: "Open Hafutza Typing now"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\models"
