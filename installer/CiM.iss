; Charts In Motion installer — unsigned, LZMA2
; OnlineOnlyActivation=1: no vendor install key (user signs in after install)
#define MyAppName "Charts In Motion"
; AppVersion and SourcePayload passed by build_installer.ps1 (/DAppVersion=...)
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif
#ifndef SourcePayload
  #define SourcePayload "Encrypted\CiM"
#endif
#ifndef InstallerOutputDir
  #define InstallerOutputDir "Encrypted"
#endif
; License secret: build_installer.ps1 writes generated_license_secret.pas (never use #define — # in secret breaks ISPP).

[Setup]
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
DefaultDirName={autopf}\CiM
DefaultGroupName=Charts In Motion
OutputDir={#InstallerOutputDir}
OutputBaseFilename=CiMSetup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\desktop\cim.ico
DisableProgramGroupPage=yes
ExtraDiskSpaceRequired=0

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
Source: "{#SourcePayload}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs; Excludes: "data\watchlists.json,data\portfolio.json,data\layout.json,data\saved_filters.json,data\screener_session.json,data\screener_profile\*"
Source: "{#SourcePayload}\data\watchlists.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist skipifsourcedoesntexist
Source: "{#SourcePayload}\data\portfolio.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist skipifsourcedoesntexist
Source: "{#SourcePayload}\data\layout.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist skipifsourcedoesntexist
Source: "{#SourcePayload}\data\saved_filters.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist skipifsourcedoesntexist
Source: "{#SourcePayload}\data\screener_session.json"; DestDir: "{app}\data"; Flags: ignoreversion onlyifdoesntexist skipifsourcedoesntexist
Source: "{#SourcePayload}\data\screener_profile\*"; DestDir: "{app}\data\screener_profile"; Flags: ignoreversion onlyifdoesntexist recursesubdirs createallsubdirs skipifsourcedoesntexist
Source: "{#InstallerOutputDir}\version.txt"; DestDir: "{app}"; Flags: ignoreversion skipifsourcedoesntexist
Source: "..\scripts\CiMApplyUpdate.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\CiMDownloadUpdate.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\Repair-CiMLicense.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\Repair-CiMLicense.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Repair-CiMLicense-Auto.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\Apply-Update.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\scripts\_Apply-LocalUpdate.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "..\scripts\Apply-LocalUpdate-Entry.ps1"; DestDir: "{app}\scripts"; Flags: ignoreversion
Source: "{#InstallerOutputDir}\UPDATE_README.txt"; DestDir: "{app}\UPDATE"; DestName: "README.txt"; Flags: ignoreversion onlyifdoesntexist skipifsourcedoesntexist

[Icons]
Name: "{group}\Charts In Motion"; Filename: "{app}\start_cim.bat"; WorkingDir: "{app}"
Name: "{autodesktop}\Charts In Motion"; Filename: "{app}\start_cim.bat"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\start_cim.bat"; Description: "Launch Charts In Motion"; Flags: nowait postinstall skipifsilent

[Code]
#ifdef OnlineOnlyActivation

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    SaveStringToFile(ExpandConstant('{app}\version.txt'), '{#AppVersion}', False);
  end;
end;

#else

var
  LicenseMachinePage, LicenseKeyPage: TWizardPage;
  MachineCodeEdit, KeyEdit: TNewEdit;
  CopyMachineBtn: TNewButton;
  MachineInstrLabel, KeyInstrLabel, KeyFormatLabel: TNewStaticText;
  StoredMachineCode, StoredInstallKey: String;

#include "{#InstallerOutputDir}\generated_license_secret.pas"
#include "{#InstallerOutputDir}\license_validate.pas"

procedure CopyMachineCodeClick(Sender: TObject);
var
  TempPath: String;
  ErrorCode: Integer;
begin
  if MachineCodeEdit.Text = '' then
    Exit;
  TempPath := ExpandConstant('{tmp}\cim-machine-code.txt');
  SaveStringToFile(TempPath, MachineCodeEdit.Text, False);
  if not Exec(ExpandConstant('{cmd}'), '/c type ' + AddQuotes(TempPath) + ' | clip', '', SW_HIDE, ewWaitUntilTerminated, ErrorCode) or (ErrorCode <> 0) then
  begin
    MsgBox('Could not copy to clipboard. Select the machine code and press Ctrl+C.', mbError, MB_OK);
    Exit;
  end;
  MsgBox(
    'Machine code copied to the clipboard.' + #13#10 + #13#10 +
    'Paste it in your message to Charts In Motion support. On the next screen, enter the install key you receive.',
    mbInformation,
    MB_OK);
end;

function InitializeSetup(): Boolean;
var
  MC, KeyParam: String;
begin
  Result := True;
  StoredMachineCode := '';
  StoredInstallKey := '';
  if WizardSilent() then
  begin
    KeyParam := Trim(ExpandConstant('{param:INSTALLKEY}'));
    if KeyParam = '' then
    begin
      MsgBox(
        'Silent install requires /INSTALLKEY=XXXX-XXXX-XXXX-XXXX-XXXX-XXXX' + #13#10 +
        'Generate the key with scripts\Generate-CiMInstallKey.ps1 on the build PC.',
        mbError,
        MB_OK);
      Result := False;
      Exit;
    end;
    MC := GetMachineCode;
    if not ValidateInstallKey(MC, KeyParam) then
    begin
      MsgBox('Invalid /INSTALLKEY for this PC.', mbError, MB_OK);
      Result := False;
      Exit;
    end;
    StoredMachineCode := MC;
    StoredInstallKey := NormalizeInstallKey(KeyParam);
  end;
end;

procedure InitializeWizard;
begin
  LicenseMachinePage := CreateCustomPage(
    wpSelectDir,
    'Activate Charts In Motion',
    'Request a one-time install key using your machine code.');

  MachineInstrLabel := TNewStaticText.Create(LicenseMachinePage);
  MachineInstrLabel.Parent := LicenseMachinePage.Surface;
  MachineInstrLabel.AutoSize := False;
  MachineInstrLabel.WordWrap := True;
  MachineInstrLabel.Caption :=
    'Before Charts In Motion can install on this PC, support must issue an install key for your machine.' + #13#10 + #13#10 +
    '1. Click Copy below and send the machine code to Charts In Motion support (email or chat).' + #13#10 +
    '2. Wait for your install key (format XXXX-XXXX-XXXX-XXXX-XXXX-XXXX).' + #13#10 +
    '3. Click Next and paste the install key on the following screen.';
  MachineInstrLabel.SetBounds(0, 0, LicenseMachinePage.SurfaceWidth, 88);

  MachineCodeEdit := TNewEdit.Create(LicenseMachinePage);
  MachineCodeEdit.Parent := LicenseMachinePage.Surface;
  MachineCodeEdit.ReadOnly := True;
  MachineCodeEdit.TabStop := True;
  MachineCodeEdit.SetBounds(0, 96, LicenseMachinePage.SurfaceWidth - 92, 23);
  MachineCodeEdit.Text := GetMachineCode;

  CopyMachineBtn := TNewButton.Create(LicenseMachinePage);
  CopyMachineBtn.Parent := LicenseMachinePage.Surface;
  CopyMachineBtn.Caption := 'Copy code';
  CopyMachineBtn.SetBounds(LicenseMachinePage.SurfaceWidth - 86, 94, 86, 27);
  CopyMachineBtn.OnClick := @CopyMachineCodeClick;

  LicenseKeyPage := CreateCustomPage(
    LicenseMachinePage.ID,
    'Install key',
    'Enter the key you received from Charts In Motion support.');

  KeyInstrLabel := TNewStaticText.Create(LicenseKeyPage);
  KeyInstrLabel.Parent := LicenseKeyPage.Surface;
  KeyInstrLabel.AutoSize := False;
  KeyInstrLabel.WordWrap := True;
  KeyInstrLabel.Caption :=
    'Paste the install key from Charts In Motion support into the box below.' + #13#10 +
    'Setup checks that the key matches this PC. If it does not match, installation will stop and no files will be changed.';
  KeyInstrLabel.SetBounds(0, 0, LicenseKeyPage.SurfaceWidth, 48);

  KeyEdit := TNewEdit.Create(LicenseKeyPage);
  KeyEdit.Parent := LicenseKeyPage.Surface;
  KeyEdit.SetBounds(0, 56, LicenseKeyPage.SurfaceWidth, 23);

  KeyFormatLabel := TNewStaticText.Create(LicenseKeyPage);
  KeyFormatLabel.Parent := LicenseKeyPage.Surface;
  KeyFormatLabel.AutoSize := False;
  KeyFormatLabel.WordWrap := True;
  KeyFormatLabel.Caption := 'Example format: A1B2-C3D4-E5F6-7890-ABCD-EF12 (dashes optional when pasting).';
  KeyFormatLabel.SetBounds(0, 84, LicenseKeyPage.SurfaceWidth, 32);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  MC, Key: String;
begin
  Result := True;
  if CurPageID = LicenseKeyPage.ID then
  begin
    MC := GetMachineCode;
    Key := KeyEdit.Text;
    if Trim(Key) = '' then
    begin
      MsgBox(
        'Please enter the install key you received from Charts In Motion support.' + #13#10 +
        'Click Back to copy your machine code again if needed.',
        mbError,
        MB_OK);
      Result := False;
      Exit;
    end;
    if not ValidateInstallKey(MC, Key) then
    begin
      MsgBox(
        'That install key is not valid for this machine.' + #13#10 + #13#10 +
        'Check for typos, confirm the key was issued for this PC''s machine code, and contact support if needed.',
        mbError,
        MB_OK);
      Result := False;
      Exit;
    end;
    StoredMachineCode := MC;
    StoredInstallKey := NormalizeInstallKey(Key);
  end;
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  NeedsRestart := False;
  if StoredInstallKey = '' then
    Result :=
      'Charts In Motion cannot install without a valid install key.' + #13#10 +
      'Click Back and enter the key from support on the Install key screen.';
end;

function ShouldSkipPage(PageID: Integer): Boolean;
begin
  Result := False;
  { Silent /INSTALLKEY= installs must not stop on empty custom license pages. }
  if (StoredInstallKey <> '') and Assigned(LicenseMachinePage) and Assigned(LicenseKeyPage) then
  begin
    if (PageID = LicenseMachinePage.ID) or (PageID = LicenseKeyPage.ID) then
      Result := True;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
  begin
    if (StoredInstallKey <> '') and (not CiMLicenseFileExists) then
      EnsureCiMLicenseFile(StoredMachineCode, StoredInstallKey);
  end;
  if CurStep = ssPostInstall then
  begin
    EnsureCiMLicenseFile(StoredMachineCode, StoredInstallKey);
    SaveStringToFile(GetCiMInstallDir + '\version.txt', '{#AppVersion}', False);
  end;
end;

procedure DeinitializeSetup;
begin
  if (StoredInstallKey <> '') and (not CiMLicenseFileExists) then
    EnsureCiMLicenseFile(StoredMachineCode, StoredInstallKey);
  if (StoredInstallKey <> '') and (not CiMLicenseFileExists) then
    MsgBox(
      'Charts In Motion installed files but could not write data\.cim-license.' + #13#10 +
      'Run Repair-CiMLicense.bat in the install folder or contact support.',
      mbError,
      MB_OK);
end;

#endif
