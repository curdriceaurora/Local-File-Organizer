; Inno Setup Script for File Organizer
; Generates a Windows installer (.exe) from PyInstaller output.
;
; Usage:
;   iscc scripts/build_windows.iss
;
; Requires:
;   - Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;   - PyInstaller build output in dist/

#define AppName "File Organizer"
#define AppVersion "2.0.0-alpha.1"
#define AppPublisher "File Organizer Team"
#define AppURL "https://github.com/curdriceaurora/Local-File-Organizer"
#define AppExeName "file-organizer.exe"

[Setup]
AppId={{A7B3E2F1-4D5C-6E7F-8A9B-0C1D2E3F4A5B}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}/issues
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
AllowNoIcons=yes
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=file-organizer-{#AppVersion}-windows-setup
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Add to system PATH"; GroupDescription: "System integration:"

[Files]
; Main executable from PyInstaller dist/
Source: "..\dist\file-organizer-*-windows-*.exe"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Add to PATH if selected
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
Filename: "{app}\{#AppExeName}"; Parameters: "version"; Description: "Verify installation"; Flags: nowait postinstall skipifsilent runhidden

[Code]
function NeedsAddPath(Param: string): Boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER,
    'Environment', 'Path', OrigPath)
  then begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;
