; Copyright (c) 2026 Obeo
;
; This program and the accompanying materials are made available under the
; terms of the Eclipse Public License 2.0 which is available at
; https://www.eclipse.org/legal/epl-2.0.
;
; SPDX-License-Identifier: EPL-2.0

#define MyAppName "BD-1"
#define MyAppVersion "0.1.0"
#define MyAppPublisher "Obeo"
#define MyAppExeName "BD-1.exe"

[Setup]
AppId={{7A80A08B-B34A-4A99-8093-88B5A2E4CA63}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL=https://github.com/Obeo/bd1-timekeeper
AppSupportURL=https://github.com/Obeo/bd1-timekeeper/issues
AppUpdatesURL=https://github.com/Obeo/bd1-timekeeper/releases
LicenseFile=..\LICENSE
DefaultDirName={autopf}\BD-1
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=bd1-windows-x86_64
Compression=lzma
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayName={#MyAppName}

[Files]
Source: "..\dist\BD-1\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';
  RunValueName = 'BD-1';

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and RegValueExists(HKCU, RunKey, RunValueName) then
  begin
    { Preserve the user's choice while replacing a stale path from a previous install. }
    RegWriteStringValue(
      HKCU,
      RunKey,
      RunValueName,
      '"' + ExpandConstant('{app}\{#MyAppExeName}') + '"'
    );
  end;
end;
