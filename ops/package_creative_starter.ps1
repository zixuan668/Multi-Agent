$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss-fff'
$target = Join-Path $projectRoot "artifacts/handoff/creative-starter-$stamp"
$zipPath = "$target.zip"
if ((Test-Path -LiteralPath $target) -or (Test-Path -LiteralPath $zipPath)) { throw '交接包目标已存在，不覆盖' }
$paths = @(
    'docs/01-strategy-agent.md','docs/02-creative-agent.md','docs/03-evaluation-agent.md',
    'docs/02-creative-handoff-guide.md','docs/strategy-human-review.md','docs/team-collaboration.md',
    'packages/contracts/creative-request.schema.json','packages/contracts/strategy-request.schema.json',
    'packages/contracts/strategy-response.schema.json',
    'src/__init__.py','src/agents/__init__.py','src/agents/creative/README.md',
    'src/agents/evaluation/README.md','prompts/evaluation/README.md',
    'ops/__init__.py','ops/validate_creative_handoff.py','ops/strategy_cases.py','ops/run_strategy_acceptance.py',
    'tests/__init__.py','tests/integration/__init__.py','tests/integration/test_creative_handoff_pack.py',
    'tests/fixtures/strategy/guided_intakes.cjs','tests/fixtures/strategy/workspace_examples.cjs','web/brief.js','web/examples.js',
    'prompts/README.md','prompts/strategy/v1.8.txt','prompts/strategy/v1.9.txt','prompts/strategy/v1.9-review.txt','prompts/strategy/v1.10.txt','prompts/strategy/v1.10-review.txt','prompts/creative/README.md'
)
$paths += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'src/agents/strategy') -Filter '*.py' -File | ForEach-Object { 'src/agents/strategy/' + $_.Name })
$paths += @(Get-ChildItem -LiteralPath (Join-Path $projectRoot 'tests/fixtures/creative') -File | Where-Object { $_.Extension -eq '.json' -or $_.Name -eq 'README.md' } | ForEach-Object { 'tests/fixtures/creative/' + $_.Name })
foreach ($relativePath in $paths) {
    $source = Join-Path $projectRoot $relativePath
    $destination = Join-Path $target $relativePath
    New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
    Copy-Item -LiteralPath $source -Destination $destination
}
Copy-Item -LiteralPath (Join-Path $projectRoot 'docs/creative-starter-README.md') -Destination (Join-Path $target 'README.md')
Compress-Archive -LiteralPath $target -DestinationPath $zipPath
Write-Output $zipPath
