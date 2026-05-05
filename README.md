# 司法文件處理自動化工具

此專案用於自動化擷取台灣司法院公開資料，並將文件存儲至資料庫中。

## 功能

- 每日自動從司法院API獲取最新司法文件列表
- 將文件資訊儲存至PostgreSQL資料庫
- 使用GitHub Actions自動排程執行

## 設置步驟

### 1. Fork或Clone此儲存庫

將此專案複製到您的GitHub帳戶中。

### 2. 設置GitHub Secrets

您需要在儲存庫的Settings > Secrets and variables > Actions中添加以下密鑰：

- `DB_HOST`: 資料庫主機地址
- `DB_PORT`: 資料庫端口
- `DB_NAME`: 資料庫名稱
- `DB_USER`: 資料庫用戶名
- `DB_PASSWORD`: 資料庫密碼
- `API_USER`: 司法院API用戶名
- `API_PASSWORD`: 司法院API密碼

### 3. 確認workflow檔案

確保`.github/workflows/judicial_processing.yml`檔案已正確設置。此檔案定義了自動執行的排程（每天凌晨5點台灣時間）。

### 4. 測試工作流程

您可以通過GitHub repository頁面的Actions標籤手動觸發工作流程進行測試。

## 排程設置

目前工作流程設定為每天凌晨0點5分（台灣時間）自動執行。若需修改執行時間，請編輯`.github/workflows/judicial_processing.yml`檔案中的cron表達式。

```yaml
schedule:
  # 格式: '分鐘 小時 日 月 星期'
  # 目前設定: 每天UTC 16:05 (台灣時間 0:05)
  - cron: '5 16 * * *'
```

## GitHub Actions 限制

- GitHub Actions 對免費帳戶有使用限制：
  - 2,000分鐘/月的執行時間（私有儲存庫）
  - 公開儲存庫則不受分鐘限制
- 每個工作執行最長可持續6小時
- 工作可能會在閒置10分鐘後自動中止

如果需要更長時間或更頻繁的執行，可能需要考慮付費GitHub計劃或其他排程服務。

## 疑難排解

如遇到執行問題，請查看GitHub Actions的日誌輸出，通常可在Actions頁面的工作執行詳情中找到錯誤信息。

## 注意事項

- 請確保您的資料庫可以從GitHub Actions的運行環境（通常是AWS或Azure的雲端服務器）訪問
- 建議定期檢查GitHub Actions的執行記錄，確保自動化工作正常運作
