[CmdletBinding()]
param(
    [ValidateSet('doctor', 'signature', 'backup', 'decompile', 'compile', 'flash')]
    [string]$Command = 'doctor',
    [string]$Port,
    [string]$Source,
    [string]$HexFile,
    [string]$OutputDirectory,
    [ValidateRange(1000000, 20000000)]
    [int]$CpuFrequency = 16000000,
    [ValidateRange(0.5, 250)]
    [double]$BitClockMicroseconds = 10
)

$ErrorActionPreference = 'Stop'
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $PSScriptRoot 'build\atmega128'
}
$packages = Join-Path $env:LOCALAPPDATA 'Arduino15\packages\arduino\tools'

function Find-Tool([string]$Name) {
    $tool = Get-ChildItem $packages -Recurse -Filter $Name -File -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending |
        Select-Object -First 1
    if (-not $tool) {
        throw "$Name was not found under $packages."
    }
    return $tool.FullName
}

function Resolve-OlimexPort([string]$RequestedPort) {
    if ($RequestedPort) {
        return $RequestedPort
    }

    $device = Get-CimInstance Win32_PnPEntity |
        Where-Object { $_.DeviceID -like 'USB\VID_15BA&PID_000C*' } |
        Select-Object -First 1
    if (-not $device -or $device.Name -notmatch '\((COM\d+)\)') {
        throw 'The Olimex AVR-ISP500-TINY (VID_15BA/PID_000C) was not found.'
    }
    return $Matches[1]
}

function Get-AvrdudeArguments([string]$ResolvedPort) {
    return @(
        '-C', $script:avrdudeConfig,
        '-p', 'm128',
        '-c', 'stk500v2',
        '-P', $ResolvedPort,
        '-B', $BitClockMicroseconds
    )
}

function Invoke-Avrdude([string[]]$Arguments) {
    & $script:avrdude @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "AVRDUDE failed with exit code $LASTEXITCODE. Power the programmer first, then the target; verify the ICSP cable and target power."
    }
}

$avrdude = Find-Tool 'avrdude.exe'
$avrdudeConfig = Join-Path (Split-Path (Split-Path $avrdude -Parent) -Parent) 'etc\avrdude.conf'
$avrGcc = Find-Tool 'avr-gcc.exe'
$avrObjcopy = Find-Tool 'avr-objcopy.exe'

switch ($Command) {
    'doctor' {
        $resolvedPort = Resolve-OlimexPort $Port
        Write-Host "Olimex AVR-ISP500-TINY: $resolvedPort (VID_15BA/PID_000C)"
        Write-Host "AVRDUDE: $avrdude"
        Write-Host "AVR-GCC: $avrGcc"
        Write-Host 'Target: ATmega128 (m128)'
        Write-Host "ISP bit clock: $BitClockMicroseconds microseconds"
        Write-Host 'Required order: power the programmer first, then power the AVR-MT128 separately.'
    }
    'signature' {
        $resolvedPort = Resolve-OlimexPort $Port
        Invoke-Avrdude ((Get-AvrdudeArguments $resolvedPort) + @('-v'))
    }
    'backup' {
        $resolvedPort = Resolve-OlimexPort $Port
        New-Item $OutputDirectory -ItemType Directory -Force | Out-Null
        $backupPath = Join-Path (Resolve-Path $OutputDirectory).Path 'atmega128-flash-backup.hex'
        Invoke-Avrdude ((Get-AvrdudeArguments $resolvedPort) + @('-U', "flash:r:${backupPath}:i"))
        Write-Host "Flash backup: $backupPath"
    }
    'decompile' {
        if (-not $HexFile) {
            $HexFile = Join-Path $PSScriptRoot 'build\atmega128\atmega128-flash-backup.hex'
        }
        $resolvedHex = (Resolve-Path $HexFile).Path
        $reconstructionTool = Join-Path $PSScriptRoot 'tools\avr_reconstruct.py'
        $reconstructionOutput = Join-Path $PSScriptRoot 'reconstructed\atmega128'
        & python $reconstructionTool $resolvedHex --output-dir $reconstructionOutput
        if ($LASTEXITCODE -ne 0) { throw "Firmware reconstruction failed with exit code $LASTEXITCODE." }
    }
    'compile' {
        if (-not $Source) { throw '-Source is required for compile.' }
        $resolvedSource = (Resolve-Path $Source).Path
        New-Item $OutputDirectory -ItemType Directory -Force | Out-Null
        $resolvedOutput = (Resolve-Path $OutputDirectory).Path
        $baseName = [System.IO.Path]::GetFileNameWithoutExtension($resolvedSource)
        $elfPath = Join-Path $resolvedOutput "$baseName.elf"
        $hexPath = Join-Path $resolvedOutput "$baseName.hex"

        & $avrGcc -mmcu=atmega128 "-DF_CPU=${CpuFrequency}UL" -Os -Wall -Wextra -ffunction-sections -fdata-sections $resolvedSource '-Wl,--gc-sections' -o $elfPath
        if ($LASTEXITCODE -ne 0) { throw "Compilation failed with exit code $LASTEXITCODE." }
        & $avrObjcopy -O ihex -R .eeprom $elfPath $hexPath
        if ($LASTEXITCODE -ne 0) { throw "HEX generation failed with exit code $LASTEXITCODE." }
        Write-Host "Firmware image: $hexPath"
    }
    'flash' {
        if (-not $HexFile) { throw '-HexFile is required for flash.' }
        $resolvedPort = Resolve-OlimexPort $Port
        $resolvedHex = (Resolve-Path $HexFile).Path
        Write-Host "Writing $resolvedHex to ATmega128 on $resolvedPort. Existing flash will be erased."
        Invoke-Avrdude ((Get-AvrdudeArguments $resolvedPort) + @('-U', "flash:w:${resolvedHex}:i"))
    }
}