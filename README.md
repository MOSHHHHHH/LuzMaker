# לו״ז מייקר

אפליקציית קוד פתוח בעברית ליצירת לוחות זמנים אישיים לאוטובוסים בישראל, ללא שרת בתשלום.

## שימוש
האתר: https://moshhhhhh.github.io/LuzMaker/

- צרו קבוצת קווים, בחרו מסלולים ותחנות ושמרו את הקבוצה בדפדפן.
- בחרו תאריכים ידנית (עד חמישה) או הפעילו השוואה חכמה לכל הימים הזמינים.
- ימים עם לוחות נסיעה זהים יקובצו יחד; ניתן לתת כינוי לכל לוח.
- ייצאו CSV או השתמשו בהדפסה / שמירה כ-PDF עבור כל לוח בנפרד או עבור כולם.

**הבהרה חשובה:** אלה זמני נסיעה *מתוכננים*, לא נתוני זמן אמת. יש לוודא נסיעות אצל המפעיל.

## הגדרת היום
היום התחבורתי מתחיל ב-**03:00** ומסתיים ב-**02:59:59 למחרת**.

- נסיעה בשבת בשעה 02:30 לפנות בוקר שייכת ללוח של יום שישי.
- GTFS יכול לכלול שעות כמו `25:30:00`; הן נשמרות בהתאם ליום השירות המקורי ומתורגמות ליום התחבורתי הנכון.
- החיתוך מיושם בעיבוד, במיון ובהפקת הלוחות.

## מקור הנתונים
הקובץ הרשמי: https://gtfs.mot.gov.il/gtfsfiles/israel-public-transportation.zip

הסקריפט `scripts/build_gtfs.py` קורא את `routes.txt`, `trips.txt`, `stop_times.txt`, `stops.txt`, `calendar.txt` ו-`calendar_dates.txt`, ומייצר קובצי JSON קטנים לפי מספר קו.

הפורמט המעובד משתמש במסכת ביטים של 14 יום ובקיבוץ נסיעות לפי שירות ותחנה, כדי להימנע מכפילות מיותרת של תאריכים.

## פרסום אוטומטי
ה-workflow `.github/workflows/gtfs-pages.yml` מבצע:
1. בדיקות יחידה לתאריך, לשעות חצות ולחריגי לוח.
2. בדיקת תחביר של JavaScript.
3. הורדת GTFS רשמי ועיבודו.
4. אימות נתונים ופרסום דרך GitHub Pages.

העדכון מתוכנן מדי יום בשעה 05:35 UTC, וניתן להפעילו ידנית. קבצי ה-ZIP וה-JSON לא נשמרים בהיסטוריית Git; תוצרי הפרסום נארזים כ-GitHub Pages artifact.

**כדי לאפשר פרסום:** בהגדרות המאגר, תחת Settings → Pages → Build and deployment → Source, בחרו GitHub Actions. אם כבר מוגדר כך, אין צורך לשנות דבר.

## בדיקות מקומיות
```bash
python -m unittest discover -s tests -v
python scripts/build_gtfs.py --zip /path/to/israel-public-transportation.zip --output _site
cp index.html _site/index.html
python -m http.server 8000 -d _site
```

## לוגואים של מפעילי תחבורה
לוגואים זמינים נטענים אוטומטית לפרסום מתוך Wikimedia Commons, ומוצגים לצד שמות מפעילים בממשק וב-PDF. אם לוגו חסר, נשאר שם המפעיל בטקסט. האתר אינו קשור למפעילים ואינו מייצג אותם. הלוגואים עשויים להיות מוגנים כסימני מסחר.

מקורות הקבצים: [אגד](https://commons.wikimedia.org/wiki/File:Egged_logo.svg), [קווים](https://commons.wikimedia.org/wiki/File:KavimLogo.svg) (יוצר: סטודיו DoArt, רישיון CC BY-SA 4.0), [מטרופולין](https://commons.wikimedia.org/wiki/File:Metropoline_buses_logo.svg), [סופרבוס](https://commons.wikimedia.org/wiki/File:Superbus_logo.svg), [נתיב אקספרס](https://commons.wikimedia.org/wiki/File:Nateev_Express_Logo.svg), [בית שמש אקספרס](https://commons.wikimedia.org/wiki/File:בית_שמש_אקספרס.svg). יש לבדוק בכל מקור את תנאי השימוש, במיוחד לצורך פרסום מודפס.

## מצב הפרויקט
גרסת בטא. שמירת קבוצות מקומית בלבד; אין סנכרון בין מכשירים. יצירת PDF מתבצעת באמצעות חלון ההדפסה של הדפדפן.
