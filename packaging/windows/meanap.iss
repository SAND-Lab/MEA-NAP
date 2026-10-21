; Inno Setup script for the MEA-NAP Windows installer.
;
;   iscc /DAppVersion=1.13.0 /DSourceDir=packaging\dist\MEA-NAP /DOutputDir=out packaging\windows\meanap.iss
;
; Installs for the current user only (no administrator rights, which many
; university-managed PCs don't give), into %LOCALAPPDATA%\Programs\MEA-NAP.
; Installing a newer version over an older one replaces it in place.

#ifndef AppVersion
  #error AppVersion must be defined (/DAppVersion=1.2.3)
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\MEA-NAP"
#endif
#ifndef OutputDir
  #define OutputDir "..\dist"
#endif

[Setup]
; Never change AppId: it is how Windows knows a new installer upgrades this app.
AppId={{35AB158D-6C41-4355-A820-B4B3B18C7EDF}
AppName=MEA-NAP
AppVersion={#AppVersion}
AppVerName=MEA-NAP {#AppVersion}
AppPublisher=SAND Lab
AppPublisherURL=https://github.com/SAND-Lab/MEA-NAP
AppSupportURL=https://github.com/SAND-Lab/MEA-NAP/issues
AppUpdatesURL=https://github.com/SAND-Lab/MEA-NAP/releases
DefaultDirName={localappdata}\Programs\MEA-NAP
DefaultGroupName=MEA-NAP
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
; No version: the docs link to releases/latest/download/<this name>.
OutputBaseFilename=MEA-NAP-Windows-x64-Setup
SetupIconFile=..\build\icon.ico
UninstallDisplayIcon={app}\MEA-NAP.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Close a running MEA-NAP before replacing its files.
CloseApplications=yes

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[InstallDelete]
; An upgrade must not leave the previous version's libraries beside the new.
Type: filesandordirs; Name: "{app}\_internal"

[Icons]
Name: "{autoprograms}\MEA-NAP"; Filename: "{app}\MEA-NAP.exe"
Name: "{autodesktop}\MEA-NAP"; Filename: "{app}\MEA-NAP.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\MEA-NAP.exe"; Description: "{cm:LaunchProgram,MEA-NAP}"; Flags: nowait postinstall skipifsilent
