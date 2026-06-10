{ Charts In Motion installer license helpers — included from CiM.iss after generated_license_secret.pas }

function GetMachineCode: String;
var
  Guid: String;
begin
  Guid := '';
  if RegQueryStringValue(HKLM, 'SOFTWARE\Microsoft\Cryptography', 'MachineGuid', Guid) then
    Guid := Trim(Guid)
  else
    Guid := 'NO-GUID';
  Result := UpperCase(GetMD5OfString(Guid));
end;

function NormalizeInstallKey(const S: String): String;
var
  T: String;
  I: Integer;
begin
  T := '';
  for I := 1 to Length(S) do
    if ((S[I] >= '0') and (S[I] <= '9')) or
       ((S[I] >= 'A') and (S[I] <= 'F')) or
       ((S[I] >= 'a') and (S[I] <= 'f')) then
      T := T + UpperCase(S[I]);
  if Length(T) < 24 then
    Result := ''
  else
  begin
    Result := Copy(T, 1, 4) + '-' + Copy(T, 5, 4) + '-' + Copy(T, 9, 4) + '-' +
      Copy(T, 13, 4) + '-' + Copy(T, 17, 4) + '-' + Copy(T, 21, 4);
  end;
end;

function ComputeInstallKey(const MachineCode: String): String;
var
  Secret, HexDigest: String;
begin
  Secret := GetLicenseSecret;
  HexDigest := UpperCase(GetMD5OfString(Secret + UpperCase(MachineCode)));
  Result := Copy(HexDigest, 1, 4) + '-' + Copy(HexDigest, 5, 4) + '-' +
    Copy(HexDigest, 9, 4) + '-' + Copy(HexDigest, 13, 4) + '-' +
    Copy(HexDigest, 17, 4) + '-' + Copy(HexDigest, 21, 4);
end;

function ValidateInstallKey(const MachineCode, InstallKey: String): Boolean;
begin
  Result := CompareText(NormalizeInstallKey(InstallKey), ComputeInstallKey(MachineCode)) = 0;
end;

function GetCiMInstallDir: String;
begin
  Result := WizardDirValue;
  if Result = '' then
    Result := ExpandConstant('{app}');
  if (Result <> '') and (Result[Length(Result)] = '\') then
    SetLength(Result, Length(Result) - 1);
end;

function CiMLicenseFilePath: String;
begin
  Result := GetCiMInstallDir + '\data\.cim-license';
end;

function CiMLicenseFileExists: Boolean;
begin
  Result := FileExists(CiMLicenseFilePath);
end;

procedure WriteLicenseFile(const MachineCode, InstallKey: String);
var
  AppDir, Path: String;
  Lines: TArrayOfString;
begin
  AppDir := GetCiMInstallDir;
  if AppDir = '' then
  begin
    Log('Charts In Motion: WriteLicenseFile skipped - install dir unknown');
    Exit;
  end;
  ForceDirectories(AppDir + '\data');
  Path := AppDir + '\data\.cim-license';
  SetArrayLength(Lines, 3);
  Lines[0] := '# Charts In Motion license - do not share';
  Lines[1] := 'MachineCode=' + MachineCode;
  Lines[2] := 'InstallKey=' + NormalizeInstallKey(InstallKey);
  if SaveStringsToFile(Path, Lines, False) then
    Log('Charts In Motion license written: ' + Path)
  else
    Log('Charts In Motion: SaveStringsToFile failed: ' + Path);
end;

function EnsureCiMLicenseFile(const MachineCode, InstallKey: String): Boolean;
begin
  if CiMLicenseFileExists then
  begin
    Result := True;
    Exit;
  end;
  if (InstallKey = '') or (MachineCode = '') then
  begin
    Result := False;
    Exit;
  end;
  WriteLicenseFile(MachineCode, InstallKey);
  Result := CiMLicenseFileExists;
end;
