# JAV DB Downloader

A PyQt6 desktop application for browsing JavDB.com and downloading videos via magnet links.

## 功能 Features

- **網頁瀏覽**: 透過 Chrome DevTools Protocol (CDP) 連線至已開啟的瀏覽器
- **專輯掃描**: 自動瀏覽分頁並檢視每個專輯的 magnet 連結
- **多條件過濾**:
  - `-nl` 新片/老片過濾
  - `-nc` 單人/合集過濾  
  - `-fda` 強制重新下載
  - `-uc` 含中文字幕 (-c) 或無碼 (-u/-uc) 過濾
  - `-4k` 4K 影片過濾
- **下載方式**: 支援 aria2 和 PikPak 兩種下載方式
- **剪貼簿監控**: 自動偵測剪貼簿中的 magnet 連結並下載
- **本地檔案掃描**: 掃描本機影片資料夾，自動比對 JavDB 資料庫
- **資料庫管理**: 將專輯資料儲存至 JSON 檔案

## 環境需求 Requirements

- Python 3.11+
- Windows OS
- Chrome 瀏覽器 (需開啟遠端除錯連接埠 `chrome --remote-debugging-port=9222`)
- 已安裝的 Python 套件:
  - pandas
  - pyperclip
  - beautifulsoup4
  - playwright
  - aria2p
  - pikpakapi
  - PyQt6

## 安裝 Installation

```bash
pip install pandas pyperclip beautifulsoup4 playwright aria2p pikpakapi PyQt6
playwright install chromium
```

## 使用方法 Usage

### 1. 啟動 Chrome 瀏覽器

```bash
chrome --remote-debugging-port=9222
```

### 2. 啟動程式

```bash
python jdb_download.py
```

### 3. 操作說明

#### 頁面範圍設定
- **All Pages**: 掃描所有頁面
- **Single Page**: 只掃描單一頁面
- **Page Range**: 輸入範圍 (如 3-5 頁)

#### 搜尋類型
- `censored`: 有碼片
- `uncensored`: 無碼片
- `search`: 關鍵字搜尋
- `actor`: 演員搜尋

#### 過濾選項
- `-nl 新瓶舊酒/全部`: 是否只檢視舊片 (270 天前)
- `-nc 單人/含合集`: 是否跳過多位演員的合集
- `-fda 重下載/未下載`: 已下載過的是否仍要處理
- `-uc 只停在-u/-c/-uc`: 是否只停在有中文字幕或無碼的影片
- `-4k 只停在-4k`: 是否只停在 4K 影片

#### 控制按鈕
- **Continue to Next**: 繼續處理下一個專輯
- **Skip This Album**: 跳過目前專輯
- **Save to W:/**: 儲存資料至網路磁碟
- **STOP**: 停止掃描

### 4. 下載專輯

在專輯檢視畫面中:
1. 表格會顯示所有可用的 magnet 連結
2. 雙擊任一列即可開始下載
3. 選擇下載方式: aria2 或 pikpak
4. 亦可複製 magnet 連結至剪貼簿，程式會自動偵測並下載

## 資料檔案 Data Files

| 檔案 | 說明 |
|------|------|
| `my javdb.json` | 所有影片資料庫 |
| `my collection.json` | 已在庫的片單及檔案路徑 |
| `maglink_added.json` | 已在 aria2 下載過的 magnet 連結 |
| `check.json` | 最近檢查過的專輯記錄 |

## 配置 Configuration

在 `jdb_download.py` 中可調整以下設定:

```python
ARIA2_SERVER = 'http://192.168.50.7'  # aria2 伺服器位址
PIKPAK_TOKEN = '...'                   # PikPak 授權碼
PATH_MAP = {...}                       # Linux 對應 Windows 路徑
```

## 資料流程 Data Flow

```
JavDB.com ─→ Playwright ─→ PyQt6 UI ─→ 用戶決策 ─→ aria2/PikPak 下載
                        │
                        └─→ JSON 資料庫儲存
```

## 授權 License

僅供個人學習使用，請尊重智慧財產權。