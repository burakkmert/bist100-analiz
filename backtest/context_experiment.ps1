# Görev 7: bağlam uzunluğu deneyi (Windows PowerShell)
# Her bağlam için TimesFM + Chronos + kıyas modelleri; sonuçlar ayrı dosyalara yazılır.
# Kullanım (bist100-analiz klasöründe, .venv aktifken):
#     powershell -ExecutionPolicy Bypass -File backtest\context_experiment.ps1
$env:PYTHONIOENCODING = "utf-8"   # Türkçe karakterler ve ≈ işareti için
foreach ($ctx in 90, 120, 256, 512) {
    Write-Host "===== Bağlam: $ctx gün =====" -ForegroundColor Cyan
    python -m backtest.run_backtest --models timesfm chronos naive naive_drift --context $ctx --tag "ctx$ctx" |
        Tee-Object -FilePath "backtest\reports\context_$ctx.txt"
}
Write-Host "===== Karşılaştırma =====" -ForegroundColor Cyan
python -m backtest.compare_contexts | Tee-Object -FilePath "backtest\reports\context_comparison.txt"
