import streamlit as st
import yfinance as yf
import pandas as pd

from engines.technical import add_indicators, technical_scores, key_levels
from engines.patterns import detect_patterns
from engines.fundamentals import analyze_fundamentals
from engines.backtest import analog_backtest
from engines.assets import classify_asset, asset_explanation
from engines.market import market_context
from ui.charts import price_chart, volume_chart

st.set_page_config(page_title="Stock AI V4.1",page_icon="📈",layout="wide")
st.title("📈 Stock AI V4.1")

st.markdown("""
<style>
/* iPhone / mobile layout */
.block-container {
    max-width: 1200px;
    padding-top: 1rem;
    padding-bottom: 2rem;
}

[data-testid="stMetric"] {
    border: 1px solid rgba(128,128,128,.20);
    border-radius: 14px;
    padding: 12px;
}

@media (max-width: 768px) {
    .block-container {
        padding-left: 0.7rem;
        padding-right: 0.7rem;
        padding-top: 0.5rem;
    }

    h1 {
        font-size: 1.65rem !important;
        line-height: 1.2 !important;
    }

    h2, h3 {
        line-height: 1.25 !important;
    }

    [data-testid="stHorizontalBlock"] {
        gap: 0.45rem;
    }

    [data-testid="column"] {
        min-width: 100% !important;
        width: 100% !important;
        flex: 1 1 100% !important;
    }

    [data-testid="stMetric"] {
        margin-bottom: 0.35rem;
    }

    .stButton > button {
        width: 100%;
        min-height: 46px;
        border-radius: 12px;
        font-size: 1rem;
    }

    [data-testid="stTextInput"] input {
        min-height: 46px;
        font-size: 16px;
        border-radius: 12px;
    }

    [data-testid="stSelectbox"] > div > div {
        min-height: 44px;
    }

    [data-testid="stSidebar"] {
        min-width: 86vw !important;
        max-width: 86vw !important;
    }

    iframe {
        max-width: 100% !important;
    }
}
</style>
""", unsafe_allow_html=True)

st.caption("ניתוח שוק אישי — מותאם גם לאייפון")

def pct_raw(v):
    return "אין נתון" if v is None else f"{v:.1f}%"

def pct_fraction(v):
    return "אין נתון" if v is None else f"{v*100:.1f}%"

def money(v):
    if v is None:return "אין נתון"
    for n,s in [(1e12,"T"),(1e9,"B"),(1e6,"M")]:
        if abs(v)>=n:return f"${v/n:.2f}{s}"
    return f"${v:,.2f}"

def label(score):
    if score is None:return "אין נתון"
    return "🟢 חיובי" if score>=75 else "🟡 מעורב / דורש אישור" if score>=55 else "🔴 חלש"

with st.sidebar:
    st.header("⚙️ תצוגה")
    period=st.selectbox("תקופת גרף",["3 חודשים","6 חודשים","שנה","שנתיים","5 שנים"],2)
    candles=st.toggle("נרות יפניים",True)
    averages=st.toggle("ממוצעים נעים",True)
    zones=st.toggle("אזורי תמיכה/התנגדות",True)
    volume_on=st.toggle("מחזורי מסחר",True)
    patterns_on=st.toggle("זיהוי תבניות",True)
    backtest_on=st.toggle("מצבים היסטוריים דומים",True)
    market_on=st.toggle("השוואה לשוק/סקטור",True)

symbol=st.text_input("🔎 סימול נכס","NVDA").strip().upper()
run=st.button("נתח",type="primary")

if run:
    try:
        with st.spinner(f"מנתח {symbol}..."):
            t=yf.Ticker(symbol)
            data=t.history(period="5y",auto_adjust=True)
            if data.empty or len(data)<60:
                st.error("אין מספיק נתונים לנכס הזה."); st.stop()
            try: info=t.info or {}
            except Exception: info={}
            data=add_indicators(data)
            tech=technical_scores(data)
            levels=key_levels(data)
            asset_type=classify_asset(symbol,info)
            fundamental=analyze_fundamentals(info,asset_type)
            patterns=detect_patterns(data) if patterns_on else []
            context=market_context(symbol,info,asset_type) if market_on else {}
            bt=analog_backtest(data) if backtest_on else {}

        name=info.get("longName",symbol)
        st.header(f"{name} ({symbol})")
        st.caption(f"סוג נכס: {asset_type} | {asset_explanation(asset_type)}")

        c1,c2,c3,c4=st.columns(4)
        c1.metric("מחיר",f"${tech['price']:.2f}",f"{tech['daily_change']:.2f}%")
        c2.metric("טווח קצר",f"{tech['short']}/100")
        c3.metric("טווח בינוני",f"{tech['medium']}/100")
        c4.metric("טווח ארוך",f"{fundamental['long_score']}/100" if fundamental.get("available") else "לא רלוונטי/חסר")

        entry=round(tech["short"]*.6+tech["medium"]*.4)
        st.subheader("🎯 השורה התחתונה")
        if entry>=75:
            st.success("🟢 התמונה הטכנית חיובית יחסית. יש תמיכה מצד המגמה והמומנטום, אך אין ודאות לעלייה.")
        elif entry>=55:
            st.warning("🟡 המתנה לאישור נוסף. חלק מהמדדים תומכים וחלקם עדיין חלשים.")
        else:
            st.error("🔴 התמונה הטכנית חלשה כרגע. המערכת אינה מזהה יתרון טכני ברור לכניסה חדשה.")

        days={"3 חודשים":90,"6 חודשים":180,"שנה":365,"שנתיים":730,"5 שנים":1825}[period]
        chart_data=data[data.index>=data.index[-1]-pd.Timedelta(days=days)]
        st.subheader("📊 גרף")
        st.plotly_chart(price_chart(chart_data,levels,candles,averages,zones),use_container_width=True)
        if volume_on:
            st.plotly_chart(volume_chart(chart_data),use_container_width=True)

        a,b,c=st.columns(3)
        a.metric("📍 תמיכה",f"${levels['support_zone'][0]:.2f}–${levels['support_zone'][1]:.2f}")
        b.metric("מחיר",f"${tech['price']:.2f}")
        c.metric("🚧 התנגדות",f"${levels['resistance_zone'][0]:.2f}–${levels['resistance_zone'][1]:.2f}")

        st.subheader("🧠 מה קורה עכשיו?")
        st.write(f"• RSI **{tech['rsi']:.1f}** — " + ("גבוה יחסית." if tech["rsi"]>=70 else "נמוך יחסית." if tech["rsi"]<=30 else "לא באזור קיצוני."))
        st.write("• MACD — " + ("המומנטום הקצר מתחזק." if tech["macd"]>tech["signal"] else "המומנטום הקצר נחלש."))
        st.write(f"• מחזור **{tech['volume_ratio']:.2f}×** מממוצע 20 הימים.")
        st.write(f"• תנודתיות יומית אחרונה **{tech['volatility']:.2f}%**.")

        if market_on:
            st.subheader("🌍 מול השוק והסקטור")
            m1,m2,m3=st.columns(3)
            m1.metric("ביצועי הנכס — 3 חודשים",pct_raw(context.get("asset_3m")))
            m2.metric(context.get("benchmark_name","מדד השוואה"),pct_raw(context.get("benchmark_3m")))
            m3.metric("סקטור",pct_raw(context.get("sector_3m")))
            if context.get("relative_market") is not None:
                if context["relative_market"]>0:
                    st.success(f"הנכס חזק מהשוק בכ־{context['relative_market']:.1f} נקודות אחוז ב-3 החודשים האחרונים.")
                else:
                    st.warning(f"הנכס מפגר אחרי השוק בכ־{abs(context['relative_market']):.1f} נקודות אחוז ב-3 החודשים האחרונים.")
            if context.get("relative_sector") is not None:
                st.write(f"ביחס לסקטור: **{context['relative_sector']:+.1f} נקודות אחוז**.")

        if patterns_on:
            st.subheader("🧩 תבניות גרפיות")
            if patterns:
                for p in patterns[:4]:
                    st.info(f"**{p['hebrew']} ({p['name']})** | נטייה: {p['bias']} | "
                            f"ביטחון ראשוני {p['confidence']}% | {p['status']}")
            else:
                st.write("לא זוהתה כרגע תבנית מבנית מספיק ברורה.")

        st.subheader("🏢 ניתוח לפי סוג הנכס")
        if asset_type=="EQUITY" and fundamental.get("available"):
            f=fundamental["fields"]
            x1,x2,x3=st.columns(3)
            x1.metric("צמיחת הכנסות",pct_fraction(f["revenue_growth"]))
            x2.metric("צמיחת רווחים",pct_fraction(f["earnings_growth"]))
            x3.metric("שולי רווח",pct_fraction(f["profit_margin"]))
            y1,y2,y3=st.columns(3)
            y1.metric("תזרים חופשי",money(f["free_cash_flow"]))
            y2.metric("מזומן",money(f["cash"]))
            y3.metric("חוב",money(f["debt"]))
            st.write(f"איכות עסקית: **{fundamental['score']}/100** | "
                     f"תמחור בסיסי: **{fundamental['valuation_score']}/100** | "
                     f"טווח ארוך: **{fundamental['long_score']}/100**")
        elif asset_type=="ETF":
            st.info("קרן סל: V4.1 משתמשת בעיקר במגמה, תנודתיות והשוואת שוק. ניתוח אחזקות ודמי ניהול יתווסף בשלב הבא.")
        elif asset_type=="INDEX":
            st.info("מדד: אין משמעות לרווחי חברה בודדת. ההתמקדות היא במגמה ובמצב השוק.")
        elif asset_type in ["CRYPTO","FX"]:
            st.info("בנכס הזה ההתמקדות כרגע היא במחיר, מומנטום וסיכון. מאקרו/On-chain ידרשו ספקי נתונים נוספים.")
        else:
            st.info("הניתוח הותאם לנתונים הזמינים ולא הופעל מודל חברה בכוח.")

        if backtest_on:
            st.subheader("🧪 מה קרה בעבר במצבים דומים?")
            if bt:
                cols=st.columns(3)
                for col,(h,r) in zip(cols,bt.items()):
                    with col:
                        st.markdown(f"### {h}")
                        st.write(f"מקרים דומים: **{r['samples']}**")
                        st.write("חיוביים: **" + (f"{r['positive_pct']:.1f}%" if r["positive_pct"] is not None else "אין נתון") + "**")
                        st.write("ממוצע: **" + (f"{r['avg_return']:.1f}%" if r["avg_return"] is not None else "אין נתון") + "**")
                        st.write("חציון: **" + (f"{r['median_return']:.1f}%" if r["median_return"] is not None else "אין נתון") + "**")
                        st.write("גרוע ביותר: **" + (f"{r['worst']:.1f}%" if r["worst"] is not None else "אין נתון") + "**")
                st.caption("זהו תיאור היסטורי של מצבים טכניים דומים — לא הסתברות מובטחת ולא תחזית.")
            else:
                st.write("אין כרגע מספיק היסטוריה לבדיקת מצבים דומים.")

        st.subheader("👀 מה ישנה את התמונה?")
        left,right=st.columns(2)
        with left:
            st.markdown("### 🟢 שיפור")
            if tech["price"]<=tech["ma20"]: st.write(f"• חזרה מעל MA20 (${tech['ma20']:.2f})")
            if tech["price"]<=tech["ma50"]: st.write(f"• חזרה מעל MA50 (${tech['ma50']:.2f})")
            if tech["macd"]<=tech["signal"]: st.write("• MACD יחזור מעל קו האיתות")
            st.write(f"• פריצה מעל ${levels['resistance_zone'][0]:.2f}–${levels['resistance_zone'][1]:.2f} במחזור חזק")
        with right:
            st.markdown("### 🔴 סיכון")
            st.write(f"• שבירה מתחת ${levels['support_zone'][0]:.2f}–${levels['support_zone'][1]:.2f}")
            st.write("• ירידה במחיר יחד עם מחזור מכירות חריג")

        st.caption("⚠️ Stock AI V4.1 הוא כלי ניסיוני ללמידה וניתוח מידע, לא ייעוץ השקעות. "
                   "כיסוי הנתונים תלוי ב-Yahoo Finance ולכן אינו מובטח לכל נכס או בורסה.")

    except Exception as e:
        st.error("אירעה שגיאה בניתוח.")
        st.code(str(e))
