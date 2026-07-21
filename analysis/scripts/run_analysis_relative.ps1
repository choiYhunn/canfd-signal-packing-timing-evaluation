
param(
  [Parameter(Mandatory=$true)][string]$InputDir,
  [Parameter(Mandatory=$true)][string]$OutputDir,
  [Parameter(Mandatory=$true)][string]$Manifest
)
$ErrorActionPreference = 'Stop'
python "$PSScriptRootnalyze_fixed2_64b_n10.py" --input $InputDir --output $OutputDir --manifest $Manifest --bootstrap 20000 --seed 20260721
