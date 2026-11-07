param(
  [ValidateSet('voices','speak','render')][string] $Mode = 'voices',
  [string] $TextPath = '',
  [string] $OutputPath = '',
  [string] $VoiceName = '',
  [int] $Rate = 0,
  [int] $Volume = 100
)
$ErrorActionPreference = 'Stop'
try {
  [Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
  Add-Type -AssemblyName System.Speech
  $synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
  if ($Mode -eq 'voices') {
    $names = @($synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name })
    ConvertTo-Json -InputObject $names -Compress -Depth 3
    exit 0
  }
  if (-not (Test-Path -LiteralPath $TextPath -PathType Leaf)) {
    throw 'Input text file was not found'
  }
  if ($VoiceName) {
    $matches = @($synth.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Name.IndexOf($VoiceName, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 })
    if ($matches.Count -eq 0) { throw "SAPI voice not found: $VoiceName" }
    $synth.SelectVoice($matches[0].VoiceInfo.Name)
  }
  $synth.Rate = [Math]::Max(-10, [Math]::Min(10, $Rate))
  $synth.Volume = [Math]::Max(0, [Math]::Min(100, $Volume))
  $speechText = [System.IO.File]::ReadAllText($TextPath, [System.Text.Encoding]::UTF8)
  if ($Mode -eq 'render') {
    if (-not $OutputPath) { throw 'OutputPath is required for rendering' }
    $synth.SetOutputToWaveFile($OutputPath)
  }
  if ($speechText.Trim().Length -gt 0) { $synth.Speak($speechText) }
  $synth.Dispose()
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
