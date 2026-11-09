$ErrorActionPreference = 'Stop'

$Version = '1.2.0'
$PluginName = 'hermes-purge'
$PackageDir = (Resolve-Path $PSScriptRoot).Path
$HermesHome = if ($env:HERMES_HOME) { $env:HERMES_HOME } else { Join-Path $env:LOCALAPPDATA 'hermes' }
$Dest = Join-Path $HermesHome "src\$PluginName-export-$Version"

foreach ($CommandName in @('hermes', 'git')) {
    if (-not (Get-Command $CommandName -ErrorAction SilentlyContinue)) {
        throw "Missing required command: $CommandName"
    }
}

& hermes plugins validate $PackageDir
if ($LASTEXITCODE -ne 0) { throw 'Plugin validation failed.' }
if (Test-Path $Dest) { throw "Refusing to overwrite existing source directory: $Dest" }

$Parent = Split-Path -Parent $Dest
$InstalledPlugin = Join-Path $HermesHome "plugins\$PluginName"
if (Test-Path $InstalledPlugin) {
    throw "Plugin already exists at $InstalledPlugin; refusing to replace it."
}
New-Item -ItemType Directory -Force -Path $Parent | Out-Null
Copy-Item -Recurse -Path $PackageDir -Destination $Dest
if (Test-Path (Join-Path $Dest '.git')) { Remove-Item -Recurse -Force (Join-Path $Dest '.git') }

& git -C $Dest init -q
if ($LASTEXITCODE -ne 0) { throw 'git init failed.' }
& git -C $Dest add -A
if ($LASTEXITCODE -ne 0) { throw 'git add failed.' }
& git -C $Dest -c user.name=hermes-purge -c user.email=hermes-purge@localhost commit -qm "Export hermes-purge $Version"
if ($LASTEXITCODE -ne 0) { throw 'Creating the local source commit failed.' }

$PluginUrl = ([Uri]$Dest).AbsoluteUri.TrimEnd('/')
& hermes plugins install $PluginUrl --enable
if ($LASTEXITCODE -ne 0) { throw 'Hermes plugin installation failed.' }
& hermes plugins doctor $Dest --ci
if ($LASTEXITCODE -ne 0) { throw 'Plugin doctor failed.' }

Write-Output "Installed source: $Dest"
Write-Output 'Start a new chat session before checking the injected prompt section.'
