# מדריך קינפוג מקיף: שרתי SAP Replication Server (SRS) ובסיסי נתונים ניהוליים (RSSD)
## עבור צוותי DBA ותשתיות מסדי נתונים

---

## תוכן עניינים
1. [מבוא וארכיטקטורת RSSD מול SRS](#1-מבוא-וארכיטקטורת-rssd-מול-srs)
2. [מיפוי קבצי הקונפיגורציה ותשתיות התקשורת (interfaces / sql.ini)](#2-מיפוי-קבצי-הקונפיגורציה-ותשתיות-התקשורת-interfaces--sqlini)
3. [קינפוג שרת ה-SAP ASE המארח את ה-RSSD (עבור כל שרת רפליקציה בנפרד)](#3-קינפוג-שרת-ה-sap-ase-המארח-את-ה-rssd-עבור-כל-שרת-רפליקציה-בנפרד)
4. [קינפוג שרת ה-SAP Replication Server (SRS) וחיבורו ל-RSSD](#4-קינפוג-שרת-ה-sap-replication-server-srs-וחיבורו-ל-rssd)
5. [קינפוג שרת המקור (Primary ASE) וסוכן הרפליקציה (RepAgent)](#5-קינפוג-שרת-המקור-primary-ase-וסוכן-הרפליקציה-repagent)
6. [הגדרת משתמשי ניטור והרשאות ייעודיות עבור כלי הניטור SRSMon](#6-הגדרת-משתמשי-ניטור-והרשאות-ייעודיות-עבור-כלי-הניטור-srsmon)
7. [דוגמת יישום מלאה: שרת ייצור (Site A) מול שרת אסון (Site B DR)](#7-דוגמת-יישום-מלאה-שרת-ייצור-site-a-מול-שרת-אסון-site-b-dr)
8. [צ'ק-ליסט אימות ובדיקות תקינות (Health Check Commands)](#8-צק-ליסט-אימות-ובדיקות-תקינות-health-check-commands)

---

## 1. מבוא וארכיטקטורת RSSD מול SRS

במערך רפליקציה של **SAP Replication Server 15.7 ומעלה**, לכל שרת רפליקציה יש תפקיד עצמאי. כדי ששרת ה-SRS יוכל לדעת אילו טבלאות לשכפל, לאן לנתב נתונים, ואיך לתרגם שגיאות, הוא חייב בסיס נתונים ניהולי ייעודי הנקרא **RSSD (Replication Server System Database)**.

```
┌─────────────────────────────────────────────────────────────┐
│              SAP Adaptive Server Enterprise (ASE)           │
│  ┌────────────────────────┐     ┌────────────────────────┐  │
│  │   Primary User DB      │     │  RSSD (ניהול רפליקציה) │  │
│  │       (erpdb)          │     │       (REP_PRD_RSSD)   │  │
│  │   + RepAgent Thread    │     │   - rs_databases       │  │
│  └───────────┬────────────┘     │   - rs_objects         │  │
│              │                  │   - rs_routes          │  │
│              │                  │   - rs_segments        │  │
│              │                  └───────────▲────────────┘  │
└──────────────┼──────────────────────────────┼───────────────┘
               │ (TDS Changes)                │ (TDS Metadata)
┌──────────────▼──────────────────────────────▼───────────────┐
│               SAP Replication Server (SRS)                  │
│       - Inbound Queue (102:1)   - SQT / DIST Threads        │
│       - Stable Partitions (sqm) - DSI / RSI Apply Threads   │
└─────────────────────────────────────────────────────────────┘
```

### עקרונות ברזל בארכיטקטורת RSSD:
1. **כל שרת SRS חייב RSSD בלעדי משלו**: אין לחבר שני שרתי SRS לאותו RSSD!
2. **סוגי RSSD**:
   * **Custom / Standard RSSD**: בסיס נתונים רגיל היושב בתוך שרת SAP ASE ארגוני קיים או שרת ASE ייעודי (מומלץ ביותר בסביבות ייצור קריטיות בגלל גמישות הגיבוי והניטור).
   * **ERSSD (Embedded RSSD)**: מנוע SQL Anywhere מוטמע שרץ כ-sub-process מקומי (נפוץ בסביבות מעבדה או שרתים קטנים).
3. **תוכן ה-RSSD**: מכיל טבלאות מערכת קריטיות:
   * `rs_databases` – מיפוי בסיסי הנתונים המנוהלים (DS.DB) וה-dbid שלהם.
   * `rs_objects` / `rs_columns` – Replication Definitions עבור טבלאות ופרוצדורות.
   * `rs_routes` – ניתובים לשרתי רפליקציה עמיתים.
   * `rs_segments` – שימוש פיזי בסגמנטים של ה-Queues בדיסקים.
   * `rs_exceptshdr` / `rs_exceptscmd` – יומן שגיאות החלה (Exception Log).

---

## 2. מיפוי קבצי הקונפיגורציה ותשתיות התקשורת (interfaces / sql.ini)

תקשורת בין כל רכיבי ה-Sybase/SAP מתבצעת על בסיס קובץ המיפוי המרכזי.

### 2.1 נתיבי הקבצים במערכת ההפעלה
* **בלינוקס / יוניקס**: `$SYBASE/interfaces`
* **בווינדוס**: `%SYBASE%\ini\sql.ini`

### 2.2 מבנה הקובץ לדוגמה עבור אתר ייצור
יש להגדיר כניסות עבור: שרת ה-SRS, שרת ה-Primary ASE, ושרת ה-ASE המארח את ה-RSSD:

```ini
# --- שרת ה-Primary ASE (המקור של הנתונים) ---
[ASE_PROD]
master=TCP,10.0.0.10,5000
query=TCP,10.0.0.10,5000

# --- שרת ה-ASE המארח את ה-RSSD של שרת הרפליקציה ---
[ASE_RSSD_HOST]
master=TCP,10.0.0.12,5002
query=TCP,10.0.0.12,5002

# --- שרת הרפליקציה עצמו (SAP Replication Server) ---
[REP_PROD_01]
master=TCP,10.0.0.15,5005
query=TCP,10.0.0.15,5005

# --- שרת רפליקציה באתר DR מרוחק (אם מוגדר Route) ---
[REP_DR_02]
master=TCP,10.20.0.15,5005
query=TCP,10.20.0.15,5005
```

> [!IMPORTANT]
> **הערה חשובה**: שרת ה-SRS, שרת ה-ASE וסוכן ה-RepAgent חייבים שניהם לקרוא את אותו קובץ `interfaces`/`sql.ini` (או עותקים מסונכרנים שלו), כך שכל שרת יוכל לפתור את שמות השרתים האחרים לכתובת IP ופורט.

---

## 3. קינפוג שרת ה-SAP ASE המארח את ה-RSSD (עבור כל שרת רפליקציה בנפרד)

ביצוע ההגדרות הבאות ישירות מול שרת ה-ASE שבו יוקם ה-RSSD (דרך `isql` עם יוזר `sa`):

### 3.1 יצירת התקני דיסק (Devices) ובסיס הנתונים ל-RSSD
יש להקצות שטח ייעודי עבור ה-Data וה-Log של ה-RSSD (מומלץ: לפחות 2GB Data ו-1GB Log):

```sql
/* 1. הקצאת התקני דיסק ב-ASE */
DISK INIT
   NAME = 'rssd_data_dev',
   PHYSNAME = '/sybase/data/rssd_data_01.dat',
   SIZE = '2048M',
   VDEVNO = 15
go

DISK INIT
   NAME = 'rssd_log_dev',
   PHYSNAME = '/sybase/log/rssd_log_01.dat',
   SIZE = '1024M',
   VDEVNO = 16
go

/* 2. יצירת בסיס הנתונים ל-RSSD */
CREATE DATABASE REP_PRD_RSSD
   ON rssd_data_dev = '2048M'
   LOG ON rssd_log_dev = '1024M'
go

/* 3. הגדרת מאפייני מסד הנתונים */
EXEC sp_dboption 'REP_PRD_RSSD', 'trunc log on chkpt', true
go
EXEC sp_dboption 'REP_PRD_RSSD', 'select into/bulkcopy/pllsort', true
go
EXEC sp_dboption 'REP_PRD_RSSD', 'ddl in tran', true
go

USE REP_PRD_RSSD
go
CHECKPOINT
go
```

### 3.2 יצירת משתמשי המערכת ב-ASE עבור ה-SRS
שרת הרפליקציה דורש 2 משתמשים ייעודיים בשרת ה-ASE המארח את ה-RSSD:
1. **Primary/Maintenance User**: משתמש הניהול דרכו שרת הרפליקציה קורא וכותב ל-RSSD.
2. **RepAgent User**: משתמש שבאמצעותו ה-RepAgent של ה-RSSD עצמו מתחבר.

```sql
USE master
go

/* 1. יצירת Login למשתמש הניהול של ה-RSSD */
EXEC sp_addlogin 'REP_PROD_RSSD_maint', 'SecretPass123', 'REP_PRD_RSSD'
go

/* 2. יצירת Login לסוכן ה-RepAgent של ה-RSSD */
EXEC sp_addlogin 'REP_PROD_RSSD_ra', 'SecretPass123', 'REP_PRD_RSSD'
go

/* 3. הענקת הרשאות Sa וניהול למשתמשי ה-RSSD */
EXEC sp_role 'grant', 'sa_role', 'REP_PROD_RSSD_maint'
go
EXEC sp_role 'grant', 'sa_role', 'REP_PROD_RSSD_ra'
go

/* 4. שיוך המשתמשים למסד ה-RSSD כ-dbo */
USE REP_PRD_RSSD
go
EXEC sp_adduser 'REP_PROD_RSSD_maint', 'REP_PROD_RSSD_maint', 'dbo'
go
EXEC sp_adduser 'REP_PROD_RSSD_ra', 'REP_PROD_RSSD_ra'
go
```

### 3.3 הרצת סקריפטי האתחול של ה-RSSD (DDL Scripting)
שרת ה-Replication Server מספק סקריפטים מובנים ליצירת כל הטבלאות והפרוצדורות של ה-RSSD.
נתיב הסקריפטים: `$SYBASE/$SYBASE_REP/scripts/` (או `%SYBASE%\REP-16_0\scripts\` בווינדוס).

מריצים מול ה-ASE:
```bash
# הרצת סקריפט התקנת טבלאות ה-RSSD
isql -S ASE_RSSD_HOST -U sa -P YourPassword -i $SYBASE/$SYBASE_REP/scripts/rs_install_recovery.sql

# הרצת סקריפט פרוצדורות הניהול הפנימיות
isql -S ASE_RSSD_HOST -U sa -P YourPassword -d REP_PRD_RSSD -i $SYBASE/$SYBASE_REP/scripts/rs_install_primary.sql
```
*(לחלופין, כלי ה-`rs_init` של Sybase מריץ סקריפטים אלו באופן אוטומטי בעת הקמת השרת).*

---

## 4. קינפוג שרת ה-SAP Replication Server (SRS) וחיבורו ל-RSSD

### 4.1 קובץ הקונפיגורציה של שרת הרפליקציה (`<server_name>.cfg`)
קובץ זה נוצר בתיקייה שבה רץ השרת (לדוגמה `$SYBASE/$SYBASE_REP/REP_PROD_01.cfg`).
הגדרות קריטיות בתוך הקובץ:

```ini
# =======================================================
# קובץ קונפיגורציה עבור שרת הרפליקציה REP_PROD_01
# =======================================================
RS_NAME = REP_PROD_01
RS_ID = 101

# חיבור ל-RSSD
RSSD_SERVER = ASE_RSSD_HOST
RSSD_DB = REP_PRD_RSSD
RSSD_USER = REP_PROD_RSSD_maint
RSSD_PWD = SecretPass123

# פרמטרי זיכרון וביצועים
memory_limit = 4096
sqm_page_size = 16k
num_sub_threads = 4
num_dist_threads = 4
num_trace_threads = 2

# הגדרת ספי זיכרון תורים
sqt_max_prs_size = 1048576
sqm_max_queue_size = 2097152

# קובץ שגיאות
error_log = /sybase/REP-16_0/install/REP_PROD_01.log
```

### 4.2 קובץ הריצה של ה-SRS (`run_REP_PROD_01`)
```bash
#!/bin/sh
# קובץ הפעלת שרת הרפליקציה בלינוקס
$SYBASE/$SYBASE_REP/bin/repserver \
   -S REP_PROD_01 \
   -C /sybase/REP-16_0/REP_PROD_01.cfg \
   -E /sybase/REP-16_0/install/REP_PROD_01.log
```

### 4.3 הוספת מחיצות אחסון יציב (Stable Storage Partitions)
לאחר עליית ה-SRS לראשונה, מתחברים אליו ב-`isql` ומגדירים את ה-Partitions (ה-Stable Devices של ה-Queues):

```sql
/* הרצה מול ה-SRS: isql -S REP_PROD_01 -U sa -P SecretPass */

-- הוספת מחיצה ראשונה (100GB)
add partition partition_1
   on '/sybase/srs_devices/part01.dat'
   size 102400
go

-- הוספת מחיצה שנייה (100GB)
add partition partition_2
   on '/sybase/srs_devices/part02.dat'
   size 102400
go

-- בדיקת סך המקום הפנוי
admin disk_space
go
```

### 4.4 הגדרת חיבור לבסיסי נתונים של יעדים (Replicate Databases)
כדי שה-SRS יוכל לשפוך נתונים לבסיס נתונים ביעד דרך תהליך DSI:

```sql
/* הרצה מול ה-SRS */
create connection to TARGET_ASE.crmdb
   set error class to rs_sqlserver_error_class
   set function string class to rs_sqlserver_function_class
   set username to crmdb_maint
   set password to MaintPass123
   set batch to 'on'
go
```

---

## 5. קינפוג שרת המקור (Primary ASE) וסוכן הרפליקציה (RepAgent)

בשרת ה-Primary ASE, תהליך ה-RepAgent סורק את יומן העסקאות של בסיס הנתונים ומזרים שינויים ל-SRS Inbound Queue.

### 5.1 הפעלת רפליקציה בבסיס הנתונים המקורי
```sql
/* הרצה מול ה-Primary ASE */
USE erpdb
go

-- סימון בסיס הנתונים כמועמד לרפליקציה
EXEC sp_reptostandby 'erpdb', 'all'
go
```

### 5.2 יצירת משתמש עבור סוכן ה-RepAgent ב-Primary ASE
```sql
USE master
go
EXEC sp_addlogin 'erpdb_ra', 'RaPass123', 'erpdb'
go
EXEC sp_role 'grant', 'sa_role', 'erpdb_ra'
go

USE erpdb
go
EXEC sp_adduser 'erpdb_ra', 'erpdb_ra'
go
```

### 5.3 קינפוג והפעלת ה-RepAgent
```sql
/* הגדרת ה-RepAgent של erpdb לפנות ל-REP_PROD_01 */
EXEC sp_config_rep_agent 'erpdb', 'enable', 'REP_PROD_01', 'erpdb_ra', 'RaPass123'
go

-- הגדרת גודל אצווה וסריקת לוג אופטימלית
EXEC sp_config_rep_agent 'erpdb', 'batch size', '1000'
go
EXEC sp_config_rep_agent 'erpdb', 'scan max trans', '500'
go

-- הפעלת ה-RepAgent
EXEC sp_start_rep_agent 'erpdb'
go

-- בדיקת סטטוס סוכן הרפליקציה
EXEC sp_help_rep_agent 'erpdb'
go
```

---

## 6. הגדרת משתמשי ניטור והרשאות ייעודיות עבור כלי הניטור SRSMon

עבור כלי הניטור **SRSMon** מומלץ ליצור משתמש ניטור ייעודי (למשל `srs_monitor`) בעל הרשאות קריאה בלבד ללא הרשאות עדכון (Read-Only Least Privilege).

### 6.1 בשרת ה-Replication Server (SRS)
```sql
/* הרצה מול ה-SRS */
-- יצירת משתמש ניטור
create user srs_monitor
   set password 'MonitorPass2026'
go

-- הענקת תפקיד ניטור ואיסוף סטטוסים
grant role sa_role to srs_monitor
go
```
> [!NOTE]
> בגרסאות SRS מסוימות, פקודות `admin disk_space` ו-`admin who` דורשות הרשאת `sa_role`.

### 6.2 בשרת ה-Primary ASE (לצורך איתור Lead Blocker)
```sql
/* הרצה מול ה-Primary ASE */
USE master
go
EXEC sp_addlogin 'srs_monitor', 'MonitorPass2026', 'master'
go

-- הענקת תפקיד ניטור ביצועים
EXEC sp_role 'grant', 'mon_role', 'srs_monitor'
go

-- הרשאות קריאה מפורשות על טבלאות החסימה ביומן
GRANT SELECT ON master..sysprocesses TO srs_monitor
go
GRANT SELECT ON master..syslogshold TO srs_monitor
go
GRANT SELECT ON master..systransactions TO srs_monitor
go
```

### 6.3 בשרת ה-ASE המארח את ה-RSSD (אימות טבלאות סגמנטים)
```sql
/* הרצה מול ה-ASE שמארח את ה-RSSD */
USE REP_PRD_RSSD
go
EXEC sp_addlogin 'srs_monitor', 'MonitorPass2026', 'REP_PRD_RSSD'
go
EXEC sp_adduser 'srs_monitor', 'srs_monitor'
go

-- הרשאות קריאה על טבלאות מטא-דאטה וסגמנטים
GRANT SELECT ON rs_databases TO srs_monitor
go
GRANT SELECT ON rs_segments TO srs_monitor
go
GRANT SELECT ON rs_queues TO srs_monitor
go
GRANT SELECT ON rs_routes TO srs_monitor
go
```

---

## 7. דוגמת יישום מלאה: שרת ייצור (Site A) מול שרת אסון (Site B DR)

טבלה מרכזת המציגה את ההפרדה המלאה בין שני שרתי רפליקציה בארגון:

| מאפיין | אתר ראשי / ייצור (Site A) | אתר משני / אסון (Site B DR) |
| :--- | :--- | :--- |
| **שם שרת ה-SRS** | `REP_PROD_01` | `REP_DR_02` |
| **כתובת ופורט SRS** | `10.0.0.15:5005` | `10.20.0.15:5005` |
| **שרת ה-ASE המארח את ה-RSSD** | `ASE_RSSD_PROD` (`10.0.0.12:5002`) | `ASE_RSSD_DR` (`10.20.0.12:5002`) |
| **שם מסד ה-RSSD** | `REP_PRD_RSSD` | `REP_DR_RSSD` |
| **משתמש תחזוקת RSSD** | `REP_PROD_RSSD_maint` | `REP_DR_RSSD_maint` |
| **בסיס נתונים מקור (Primary)** | `ASE_ERP_PRIMARY.erpdb` | - |
| **בסיסי נתונים יעד (Replicate)** | `CRM_DS.crmdb`, `BI_DS.dwdb` | `ASE_ERP_STANDBY.erpdb` |
| **קשר ניתוב (Route)** | `create route to REP_DR_02` | - |

### מיפוי בקובץ הקונפיגורציה של הכלי `srs_config.json`
לאחר ששני השרתים קונפגו, קובץ ה-`srs_config.json` של **SRSMon** ייראה כך:

```json
{
  "mode": "live",
  "metrics_storage": {
    "backend": "ase",
    "server_alias": "TESTDB",
    "host": "10.0.0.18",
    "port": 5002,
    "database": "INFODB",
    "user": "sa",
    "password": ""
  },
  "servers": [
    {
      "server_id": 1,
      "server_name": "REP_PROD_01",
      "host": "10.0.0.15",
      "port": 5005,
      "user": "srs_monitor",
      "password": "MonitorPass2026",
      "primary_ase": {
        "server_name": "ASE_ERP_PRIMARY",
        "host": "10.0.0.10",
        "port": 5000,
        "user": "srs_monitor",
        "password": "MonitorPass2026",
        "database": "erpdb"
      }
    },
    {
      "server_id": 2,
      "server_name": "REP_DR_02",
      "host": "10.20.0.15",
      "port": 5005,
      "user": "srs_monitor",
      "password": "MonitorPass2026",
      "primary_ase": {
        "server_name": "ASE_DR_PRIMARY",
        "host": "10.20.0.10",
        "port": 5000,
        "user": "srs_monitor",
        "password": "MonitorPass2026",
        "database": "erpdb"
      }
    }
  ]
}
```

---

## 8. צ'ק-ליסט אימות ובדיקות תקינות (Health Check Commands)

לאחר סיום הקינפוג, ה-DBA יכול לוודא את תקינות הרפליקציה בעזרת הפקודות הבאות:

### בשרת ה-SRS:
1. בדיקת תקינות מחיצות דיסק:
   ```sql
   admin disk_space
   go
   ```
2. בדיקת מצב התהליכים (לוודא שכל ה-Threads בסטטוס `Active` ולא `Suspended`):
   ```sql
   admin who
   go
   ```
3. בדיקת נפחי תורים (לוודא שאין תורים עם פער של מאות סגמנטים):
   ```sql
   admin who, sqm
   go
   ```
4. בדיקת טרנזקציות פתוחות בתורים:
   ```sql
   admin who, sqt
   go
   ```
5. בדיקת קצב תעבורה (Transactions Per Second):
   ```sql
   admin stats, tps
   go
   ```

### בשרת ה-Primary ASE:
1. בדיקת סוכן הרפליקציה:
   ```sql
   sp_help_rep_agent erpdb
   go
   ```
2. בדיקה האם ה-Secondary Truncation Point מתקדם ולא תקוע:
   ```sql
   dbcc gettrunc
   go
   ```
3. בדיקה אם קיימת טרנזקציה חוסמת ביומן:
   ```sql
   SELECT p.spid, p.status, p.loggedindatetime, p.hostname, p.program_name, p.cmd, t.name
   FROM master..sysprocesses p
   JOIN master..syslogshold h ON p.spid = h.spid
   LEFT JOIN master..systransactions t ON p.spid = t.spid
   WHERE h.dbid = db_id('erpdb')
   go
   ```
