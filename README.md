# כלי ניטור ובקרה לשרתי SAP Replication Server 15.7 (SRSMon)
## Operational Health, Partitions & Queues Monitoring Dashboard for DBA Teams

מערכת ניטור ובקרה בזמן אמת עבור צוותי DBA, שפותחה בהתאם למסמכי האפיון והמפרט ההנדסי עבור **SAP Replication Server 15.7 ומעלה** ושרתי **SAP Adaptive Server Enterprise (ASE)**.

---

## 🌟 עיקרי המערכת (Key Features)

### 1. ניטור שטח אחסון יציב (Stable Storage Partitions)
* **מקור המידע**: הרצת פקודת `admin disk_space` מול שרת ה-Replication Server.
* **חישוב מתמטי**: המרת סגמנטים ל-MB לפי נוסחת SRS 15.7:
  $$\text{Size (MB)} = \text{Segments} \times 1\text{ MB} \quad (\text{כל סגמנט} = 64 \text{ בלוקים של } 16\text{KB})$$
* **התראות קיבולת**:
  * 🟡 **אזהרה (Warning)**: מקום פנוי נמוך מ-15% (עם מנגנון Debounce של 2 דגימות).
  * 🔴 **קריטי (Critical)**: מקום פנוי נמוך מ-5% (התראה מיידית למניעת קריסת השרת).
* **חיזוי קצב התמלאות בזמן אמת**: חישוב מגמת ה-15 דקות האחרונות והצגת התראה חזותית:
  > *"⚠️ בקצב הנוכחי, המחיצה תתמלא בתוך 1.2 שעות"*

### 2. תורי הודעות פעילים (Inbound & Outbound Queues)
* **מקור המידע**: הרצת `admin who, sqm` ו-`admin who, sqt`.
* **זיהוי סוג התור לפי מזהה ה-Info**:
  * סיומת `:1` &larr; **תור נכנס (Inbound)**
  * סיומת `:0` &larr; **תור יוצא (Outbound)**
* **חישוב מדויק של נפח התור ב-MB**:
  $$\text{Queue MB} = (\Delta\text{Segs} \times 64 + \Delta\text{Blocks}) \times \frac{16}{1024}$$
* **סינון מתקדם**: צפייה בכלל התורים, תורים נכנסים בלבד, יוצאים בלבד, או תורים בעייתיים (Suspended / Lag גבוה / מעל 10GB).

### 3. איתור טרנזקציה חוסמת בשרת המקור (Primary ASE Lead Blocker)
* **הסבר תפעולי**: כאשר תור Inbound מתנפח, הגורם העיקרי הוא טרנזקציה ארוכה ב-Primary DB החוסמת את ה-Secondary Truncation Point ביומן.
* **חילוץ הנתונים מה-Primary ASE**:
  ```sql
  SELECT p.spid, p.status, p.loggedindatetime, p.hostname, p.program_name, p.cmd, t.name AS transaction_name
  FROM master..sysprocesses p
  JOIN master..syslogshold h ON p.spid = h.spid
  LEFT JOIN master..systransactions t ON p.spid = t.spid
  WHERE h.dbid = db_id('YOUR_PRIMARY_DB');
  ```
* **חלון תחקור ממוקד (Drill-Down Modal)**: לחיצה על כפתור `🔍 Lead Blocker` מציגה את ה-SPID החוסם, שם הטרנזקציה, משך הזמן שהיא פתוחה (Duration), התוכנית היוזמת, והמלצות טיפול ל-DBA (כולל סימולציית `KILL SPID`).

### 4. גרף מגמות רב-ממדי (Interactive Dual-Axis Trend Canvas)
* השוואה סימולטנית בין **נפח התורים המצטבר (Queue MB)** בציר הימני לבין **קצב התעבורה הנכנסת והיוצאת (Inbound & Outbound Throughput ב-MB/s)** בציר השמאלי.
* Tooltip אינטראקטיבי במעבר עכבר המציג חותמת זמן ומדדים מרוכזים.

### 5. מפת זרימה וטופולוגיה רב-מדרגית (Multi-Site Replication DAG)
* דיאגרמת SVG חיה הממחישה את מסלול הרפליקציה:
  $$\text{Primary ASE} \longrightarrow \text{RepAgent} \longrightarrow \text{Inbound Queue} \longrightarrow \text{DIST Thread} \longrightarrow \text{Outbound Queues} \longrightarrow \text{DSI Threads} \longrightarrow \text{Targets}$$
* חלקיקים מונפשים הזורמים לאורך הנתיבים לפי קצב התעבורה, עם צביעה חזותית של תהליכים מושהים.

### 6. מסוף פקודות דיאגנוסטיקה (Admin ISQL Console)
* הרצת פקודות אדמין ישירות מול שרת הרפליקציה (`admin who`, `admin disk_space`, `admin who, sqm`, `admin who, sqt`, `admin stats, tps`, `admin health`) והצגת פלט טבלאי מדויק.

### 7. מרכז הדמיית תרחישי קיצון (DBA Chaos & Verification)
* אפשרות להזריק תרחישי בדיקה לבחינת תגובת המערכת:
  * ⚡ **קפיצת תור חדה (15GB Inbound Spike)**
  * 🛑 **השהיית תהליך DSI ל-CRM**
  * 💾 **מילוי מחיצת Stable Storage ל-97.5% קריטי**
  * 🔒 **שחרור / שחזור חסימת SPID 348 ב-Primary**

---

## 🏗️ ארכיטקטורת המערכת

```
┌─────────────────────────────────────────────────────────────┐
│                    DBA Web Dashboard                        │
│ (Modern Dark Mode SPA - Vanilla CSS + JS + High-Perf Canvas)│
└──────────────────────────────▲──────────────────────────────┘
                               │ HTTP REST & WebSockets (/ws/v1/live)
┌──────────────────────────────▼──────────────────────────────┐
│                    FastAPI Backend Server                   │
│   ├── REST API v1 (/servers, /health, /partitions, /queues) │
│   ├── WebSocket Live Pusher (5-sec cycles)                  │
│   ├── Alert Engine (Debouncing, Hysteresis, Persistence)    │
│   └── Ring Buffer In-Memory Cache (Last 30 Min)             │
└──────────────────────────────▲──────────────────────────────┘
                               │
┌──────────────────────────────▼──────────────────────────────┐
│                Collector Engine & Storage                   │
│   ├── SQLite Storage (Schema matching SRS 15.7 Spec)        │
│   ├── Circuit Breaker Pattern (>2s latency guard)           │
│   └── SRS Client & Enterprise Simulator                     │
│       ├── Simulation Mode (Active Telemetry & Scenarios)    │
│       └── Live Mode (OpenClient / isql / ODBC connectors)   │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 הוראות הרצה (Quick Start)

### דרישות קדם
* Python 3.10 ומעלה

### הפעלת השרת
בטרמינל או PowerShell, הרץ מתוך ספריית הפרויקט:
```powershell
python run_server.py
```

לאחר עליית השרת, פתח את הדפדפן בכתובת:
👉 **http://localhost:8000**

---

## 📁 מבנה הקבצים בפרויקט

```
c:\Users\User\Downloads\SRSMon\
  ├── backend/
  │    ├── __init__.py
  │    ├── config.py              # הגדרות תדירות דגימה, ספי התראה וחיבורים
  │    ├── database.py            # סכמת מסד נתונים ואינדקסים (SQLite תואם DDL Spec)
  │    ├── alert_engine.py        # מנוע התראות עם מנגנון Debouncing ושיהוי
  │    ├── collector/
  │    │    ├── parsers.py        # לוגיקת פענוח של admin disk_space, sqm ו-syslogshold
  │    │    ├── simulator.py      # מנוע סימולציה ברמה ארגונית להדמיית שרתים ותרחישים
  │    │    ├── srs_client.py     # מנהל חיבורים ופקודות אדמין (חי / סימולטור)
  │    │    └── engine.py         # שירות איסוף רקע (15s Core, 30s Primary, 60s Perf)
  │    ├── routers/
  │    │    ├── api_v1.py         # נקודות קצה RESTful מלאות לפי האפיון
  │    │    └── ws.py             # שרת WebSockets לעדכונים חיים (/ws/v1/live)
  │    └── main.py                # אפליקציית FastAPI ראשית
  ├── frontend/
  │    └── static/
  │         ├── css/style.css     # עיצוב Dark Mode יוקרתי, Tokens, Glassmorphism
  │         ├── js/
  │         │    ├── app.js       # ניהול מצב SPA וסנכרון נתונים חי
  │         │    ├── chart.js     # גרף קווי רב-ממדי (Canvas כפול-צירים)
  │         │    ├── topology.js  # מפת זרימת רפליקציה ב-SVG
  │         │    └── modal.js     # דיאלוג Lead Blocker, התראות ומסוף פקודות
  │         └── index.html        # ממשק משתמש סמנטי ומלא
  ├── run_server.py               # סקריפט הפעלה ראשי
  └── README.md                   # תיעוד מלא
```

---

## 🗄️ מסד הנתונים לשמירת המדדים (Metrics Storage: SAP Sybase ASE 16)

המערכת מוגדרת כעת לעבוד ישירות מול שרת **SAP Sybase ASE 16 (TESTDB)**:
* **כתובת**: `10.0.0.18:5002`
* **מסד נתונים**: `INFODB`
* **משתמש**: `sa` (ללא סיסמה)
* **דרייבר**: Adaptive Server Enterprise 64-bit ODBC Driver (באמצעות `pyodbc`)

כל הטבלאות והאינדקסים נוצרו ב-`INFODB` והמדדים נשמרים בו ישירות בזמן אמת:
* `monitored_servers`
* `partition_metrics`
* `queue_metrics`
* `thread_status`
* `open_transactions_log`
* `system_alerts`

---

## ⚙️ הגדרת חיבור לשרתים אמיתיים (Production Connection)

כברירת מחדל, המערכת עולה במצב **Simulation** המאפשר בחינה מיידית של כלל המסכים, הגרפים ותרחישי הקיצון ללא תלות בשרת פעיל.

כדי לחבר את המערכת לשרת SAP Replication Server אמיתי בסביבת ייצור:
1. ודא כי לקוח OpenClient / `isql` / FreeTDS מותקן בתחנה/שרת.
2. הגדר ב-[srs_config.json](srs_config.json) את פרטי שרת הרפליקציה (SRS) ושרת ה-Primary ASE.
3. הגדר משתנה סביבה:
   ```powershell
   $env:SRSMON_DATA_MODE="live"
   ```
4. שירות ה-Collector ישתמש בממשק ה-Admin ויריץ את הפקודות המוגדרות במפרט (`admin disk_space`, `admin who, sqm`, `admin who`, `syslogshold`), ויאגור את הממצאים ב-`INFODB` בשרת ה-ASE 16.

   ```powershell
   $env:SRSMON_DATA_MODE="live"
   ```
3. עדכן ב-`backend/config.py` או בטבלת `monitored_servers` את פרטי השרתים:
   * כתובת Host ופורט ה-Admin של ה-Replication Server (לדוגמה: `5005`)
   * פרטי החיבור לשרת ה-Primary ASE (פורט `5000`)
4. שירות ה-Collector ישתמש בממשק ה-Admin ויריץ את הפקודות המוגדרות במפרט (`admin disk_space`, `admin who, sqm`, `admin who`, `syslogshold`).
