param(
    [Parameter(Mandatory=$true)]
    [string]$WavPath
)
$ErrorActionPreference = 'Stop'
try {
    if (-not [System.IO.File]::Exists($WavPath)) {
        throw "Audio file not found: $WavPath"
    }
    $player = New-Object System.Media.SoundPlayer
    $player.SoundLocation = $WavPath
    $player.Load()
    $player.PlaySync()
    $player.Dispose()
} catch {
    [Console]::Error.WriteLine($_.Exception.Message)
    exit 1
}
