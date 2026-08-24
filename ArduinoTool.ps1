[CmdletBinding()]
param(
    [ValidateSet('doctor', 'detect', 'compile', 'upload', 'monitor')]
    [string]$Command = 'doctor',
    [string]$Sketch,
    [string]$Port,
    [string]$Board = 'arduino:avr:uno',
    [ValidateRange(300, 2000000)]
    [int]$BaudRate = 9600
)

$ErrorActionPreference = 'Stop'
if (-not $Sketch) {
    $Sketch = Join-Path $PSScriptRoot 'Blink'
}

function Find-ArduinoCli {
    $onPath = Get-Command arduino-cli -ErrorAction SilentlyContinue
    if ($onPath) {
        return $onPath.Source
    }

    $candidates = @(
        (Join-Path $env:ProgramFiles 'Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe'),
        (Join-Path $env:LOCALAPPDATA 'Programs\Arduino IDE\resources\app\lib\backend\resources\arduino-cli.exe')
    )
    $found = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $found) {
        throw 'arduino-cli was not found on PATH or inside Arduino IDE.'
    }
    return $found
}

function Get-SerialPorts {
    return @([System.IO.Ports.SerialPort]::GetPortNames() | Sort-Object)
}

function Resolve-Port([string]$RequestedPort) {
    if ($RequestedPort) {
        return $RequestedPort
    }

    $ports = Get-SerialPorts
    if ($ports.Count -eq 1) {
        return $ports[0]
    }
    if ($ports.Count -eq 0) {
        throw 'No serial ports were found. Connect the Arduino and retry.'
    }
    throw "Multiple serial ports were found ($($ports -join ', ')). Specify -Port COMx."
}

$cli = Find-ArduinoCli

switch ($Command) {
    'doctor' {
        Write-Host "Arduino CLI: $cli"
        & $cli version
        Write-Host "`nInstalled cores:"
        & $cli core list
        Write-Host "`nConnected boards and serial ports:"
        & $cli board list
    }
    'detect' {
        & $cli board list
        $ports = Get-SerialPorts
        if ($ports.Count -eq 0) {
            throw 'No serial ports were found.'
        }
        Write-Host "`nSerial ports: $($ports -join ', ')"
    }
    'compile' {
        $resolvedSketch = (Resolve-Path $Sketch).Path
        & $cli compile --fqbn $Board $resolvedSketch
        if ($LASTEXITCODE -ne 0) { throw "Compilation failed with exit code $LASTEXITCODE." }
    }
    'upload' {
        $resolvedPort = Resolve-Port $Port
        $resolvedSketch = (Resolve-Path $Sketch).Path
        Write-Host "Compiling and uploading $resolvedSketch to $Board on $resolvedPort"
        & $cli compile --upload --fqbn $Board --port $resolvedPort $resolvedSketch
        if ($LASTEXITCODE -ne 0) { throw "Upload failed with exit code $LASTEXITCODE." }
    }
    'monitor' {
        $resolvedPort = Resolve-Port $Port
        & $cli monitor --port $resolvedPort --config "baudrate=$BaudRate"
        if ($LASTEXITCODE -ne 0) { throw "Serial monitor exited with code $LASTEXITCODE." }
    }
}