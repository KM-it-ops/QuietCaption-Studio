#define MyAppName "QuietCaption Studio"
#define MyAppVersion "1.0.0"
#define MyAppExeName "QuietCaption Studio.exe"

[Setup]
AppId={{4B61D949-8E67-4F7D-90E6-58A3559B1374}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\QuietCaption Studio
DefaultGroupName=QuietCaption Studio
OutputDir=..\dist
OutputBaseFilename=QuietCaption-Studio-Setup-1.0.0
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
LicenseFile=..\LICENSE

[Files]
Source: "..\dist\QuietCaption Studio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\QuietCaption Studio"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\QuietCaption Studio"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch QuietCaption Studio"; Flags: nowait postinstall skipifsilent

