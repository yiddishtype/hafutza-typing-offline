; Hafutza Typing - Windows installer (Inno Setup 6). Built by .github/workflows/build.yml:
;   ISCC.exe /DMyAppVersion=1.1 installer\hafutza.iss              full installer (program + Yiddish speech), HafutzaTyping-Setup.exe
;   ISCC.exe /DMyAppVersion=1.1 /DAppOnly installer\hafutza.iss    update installer (program only, no speech model), HafutzaTyping-Update.exe
;   (expects ..\dist\HafutzaTyping incl. version.txt, and ..\build\hafutza.ico)
; The Update button runs the update installer with /SILENT /FROMAPP=1: it waits until the program has closed
; (mutex HafutzaTypingRunning), installs over it, keeps {app}\models (downloaded parts), and opens the program again.
#define MyAppName "Hafutza Typing"
#ifndef MyAppVersion
  #define MyAppVersion "1.1"
#endif
#ifndef OutName
  #ifdef AppOnly
    #define OutName "HafutzaTyping-Update"
  #else
    #define OutName "HafutzaTyping-Setup"
  #endif
#endif

[Setup]
AppId={{8E3B6F7A-2C1D-4B8E-9F21-6A5D3C7E1B42}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
VersionInfoVersion={#MyAppVersion}
AppPublisher=Hafutza Typing
DefaultDirName={autopf}\Hafutza Typing
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\Output
OutputBaseFilename={#OutName}
SetupIconFile=..\build\hafutza.ico
UninstallDisplayIcon={app}\HafutzaTyping.exe
Compression=lzma2/fast
SolidCompression=no
LZMANumBlockThreads=4
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
WizardStyle=modern
ChangesAssociations=yes
#ifndef AppOnly
ExtraDiskSpaceRequired=3200000000
#endif

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Put a Hafutza Typing icon on the desktop"

[InstallDelete]
; the old program files (a clean copy of the new ones follows); NOT the models folder with the downloaded parts
Type: filesandordirs; Name: "{app}\_internal"

[Files]
#ifdef AppOnly
Source: "..\dist\HafutzaTyping\*"; DestDir: "{app}"; Excludes: "\models\yi\model.bin"; Flags: recursesubdirs ignoreversion createallsubdirs
#else
Source: "..\dist\HafutzaTyping\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs
#endif

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\HafutzaTyping.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\HafutzaTyping.exe"; Tasks: desktopicon

[Registry]
; "Open with > Hafutza Typing" on a right-click of a video or sound file (this user only; the normal player stays the default)
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Hafutza Typing"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\shell\open"; ValueType: string; ValueName: "FriendlyAppName"; ValueData: "Hafutza Typing"
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\HafutzaTyping.exe"" ""%1"""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\HafutzaTyping.exe,0"
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mp4"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mov"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mkv"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".avi"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".wmv"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".webm"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".m4v"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".3gp"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".flv"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mpg"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mpeg"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".ts"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mts"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mp3"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".m4a"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".wav"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".ogg"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".oga"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".opus"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".flac"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".aac"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".wma"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".amr"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".aiff"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".aif"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\HafutzaTyping.exe\SupportedTypes"; ValueType: string; ValueName: ".mka"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\.mp4\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mov\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mkv\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.avi\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.wmv\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.webm\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.m4v\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.3gp\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.flv\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mpg\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mpeg\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.ts\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mts\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mp3\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.m4a\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.wav\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.ogg\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.oga\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.opus\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.flac\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.aac\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.wma\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.amr\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.aiff\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.aif\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\.mka\OpenWithList\HafutzaTyping.exe"; ValueType: none; Flags: uninsdeletekey

[Run]
Filename: "{app}\HafutzaTyping.exe"; Description: "Open Hafutza Typing now"; Flags: nowait postinstall skipifsilent
Filename: "{app}\HafutzaTyping.exe"; Flags: nowait; Check: FromApp

[UninstallDelete]
Type: filesandordirs; Name: "{app}\models"
Type: filesandordirs; Name: "{app}\_internal"

[Code]
function FromApp: Boolean;
begin
  Result := ExpandConstant('{param:FROMAPP|0}') = '1';
end;

function InitializeSetup: Boolean;
var
  i: Integer;
begin
  Result := True;
  if FromApp then
  begin
    { started by the program's Update button: wait (up to 2 minutes) until the program has closed }
    i := 0;
    while CheckForMutexes('HafutzaTypingRunning') and (i < 240) do
    begin
      Sleep(500);
      i := i + 1;
    end;
    Log(Format('waited %d half-seconds for the program to close', [i]));
  end;
end;
