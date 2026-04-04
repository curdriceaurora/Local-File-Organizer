; Inno Setup Script for File Organizer
; Generates a Windows installer (.exe) from PyInstaller output.
;
; Usage:
;   iscc scripts/build_windows.iss
;
; Requires:
;   - Inno Setup 6+ (https://jrsoftware.org/isinfo.php)
;   - PyInstaller output in dist/

#define AppName "File Organizer"
#ifndef AppVersion
  #define AppVersion "2.0.0-alpha.1"
#endif
#define AppPublisher "File Organizer Team"
#define AppURL "https://github.com/curdriceaurora/Local-File-Organizer"
#ifndef AppExeName
  #define AppExeName "file-organizer.exe"
#endif
; Inno Download Plugin — required for downloading WebView2 at install time.
; Install from: https://mitrichsoftware.wordpress.com/inno-setup-tools/inno-download-plugin/
#include <idp.iss>

[Setup]
; AppId uniquely identifies this application. Do not reuse this GUID in other
; installers.  Generated with uuid4; the double brace is Inno Setup escaping.
AppId={{44CDBA25-4641-4909-9723-9E9B7E37EA0F}
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
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "addtopath"; Description: "Add to system PATH"; GroupDescription: "System integration:"

[Files]
; Main executable from PyInstaller dist/
Source: "..\dist\file-organizer-*-windows-*.exe"; DestDir: "{app}"; DestName: "{#AppExeName}"; Flags: ignoreversion

; WebView2 Bootstrapper - downloaded/included for offline install support
Source: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall external skipifsourcedoesntexist

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\{cm:UninstallProgram,{#AppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Registry]
; Add to PATH if selected
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; ValueData: "{olddata};{app}"; Tasks: addtopath; Check: NeedsAddPath(ExpandConstant('{app}'))

[Run]
; Install WebView2 Runtime silently if not already present
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Installing WebView2 Runtime..."; Flags: waituntilterminated skipifdoesntexist; Check: not IsWebView2Installed()
; Verify installation
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

function IsWebView2Installed(): Boolean;
var
  Value: string;
begin
  // Check machine-wide installation (WOW6432Node for 64-bit machines)
  Result := RegQueryStringValue(HKEY_LOCAL_MACHINE,
    'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
    'pv', Value);
  if not Result then
    // Check per-user installation
    Result := RegQueryStringValue(HKEY_CURRENT_USER,
      'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}',
      'pv', Value);
end;


procedure InitializeWizard();
begin
  if not IsWebView2Installed() then begin
    // Download WebView2 bootstrapper to temp location if not bundled
    if not FileExists(ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe')) then begin
      idpAddFile('https://go.microsoft.com/fwlink/p/?LinkId=2124703',
                 ExpandConstant('{tmp}\MicrosoftEdgeWebview2Setup.exe'));
      idpDownloadAfter(wpReady);
    end;
  end;
end;
