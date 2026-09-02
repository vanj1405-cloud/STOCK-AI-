import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
import plotly.graph_objects as go


def clamp(v, lo=0, hi=100):
    return max(lo, min(hi, v))

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    avg_gain = gains.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return (100 - (100 / (1 + rs))).fillna(50)

def add_indicators(data):
    d = data.copy()
    d["MA20"] = d["Close"].rolling(20).mean()
    d["MA50"] = d["Close"].rolling(50).mean()
    d["MA200"] = d["Close"].rolling(200).mean()
    d["RSI"] = calculate_rsi(d["Close"])
    d["EMA12"] = d["Close"].ewm(span=12, adjust=False).mean()
    d["EMA26"] = d["Close"].ewm(span=26, adjust=False).mean()
    d["MACD"] = d["EMA12"] - d["EMA26"]
    d["MACD_SIGNAL"] = d["MACD"].ewm(span=9, adjust=False).mean()
    d["RETURN"] = d["Close"].pct_change()
    d["VOL_AVG20"] = d["Volume"].rolling(20).mean()
    return d

def detect_swings(data, window=5):
    highs, lows = [], []
    for i in range(window, len(data)-window):
        h = float(data["High"].iloc[i])
        l = float(data["Low"].iloc[i])
        if h >= data["High"].iloc[i-window:i+window+1].max():
            highs.append((data.index[i], h))
        if l <= data["Low"].iloc[i-window:i+window+1].min():
            lows.append((data.index[i], l))
    return highs, lows

def cluster_levels(points, tolerance=0.02):
    prices = sorted([p for _, p in points])
    if not prices:
        return []
    groups = [[prices[0]]]
    for p in prices[1:]:
        mean = float(np.mean(groups[-1]))
        if abs(p-mean)/mean <= tolerance:
            groups[-1].append(p)
        else:
            groups.append([p])
    return [float(np.mean(g)) for g in groups]

def key_levels(data):
    recent = data.tail(min(252, len(data)))
    highs, lows = detect_swings(recent, 5)
    current = float(data["Close"].iloc[-1])
    supports = [x for x in cluster_levels(lows) if x < current]
    resistances = [x for x in cluster_levels(highs) if x > current]
    support = max(supports) if supports else float(recent["Low"].min())
    resistance = min(resistances) if resistances else float(recent["High"].max())
    return {
        "support": support,
        "support_zone": (support*0.985, support*1.015),
        "resistance": resistance,
        "resistance_zone": (resistance*0.985, resistance*1.015),
        "current": current,
    }

def technical_scores(data):
    last = data.iloc[-1]
    price = float(last["Close"])
    ma20, ma50, ma200 = map(float, [last["MA20"], last["MA50"], last["MA200"]])
    rsi = float(last["RSI"])
    macd, signal = float(last["MACD"]), float(last["MACD_SIGNAL"])
    volavg = float(last["VOL_AVG20"]) if pd.notna(last["VOL_AVG20"]) else 0
    volume_ratio = float(last["Volume"])/volavg if volavg > 0 else 1
    daily_change = (price/float(data["Close"].iloc[-2])-1)*100
    volatility = float(data["RETURN"].tail(20).std()*100)

    short = 50
    short += 10 if price > ma20 else -10
    short += 10 if price > ma50 else -10
    short += 10 if macd > signal else -10
    if 50 <= rsi <= 65: short += 10
    elif rsi > 75: short -= 10
    elif rsi < 30: short -= 5
    if volume_ratio >= 1.2:
        short += 10 if daily_change > 0 else -10
    if volatility > 4: short -= 10
    elif volatility < 2: short += 5

    medium = 50
    medium += 15 if price > ma50 else -15
    medium += 20 if price > ma200 else -20
    medium += 15 if ma50 > ma200 else -15
    if len(data) >= 64:
        medium += 10 if price > float(data["Close"].iloc[-63]) else -5

    return {
        "short": clamp(round(short)),
        "medium": clamp(round(medium)),
        "price": price, "ma20": ma20, "ma50": ma50, "ma200": ma200,
        "rsi": rsi, "macd": macd, "signal": signal,
        "volume_ratio": volume_ratio, "volatility": volatility,
        "daily_change": daily_change
    }


def _near(a, b, tolerance=0.035):
    return abs(a-b)/max(abs(a), abs(b), 1e-9) <= tolerance

def detect_patterns(data):
    highs, lows = detect_swings(data.tail(min(220, len(data))), window=4)
    found = []

    if len(highs) >= 2:
        a, b = highs[-2], highs[-1]
        if _near(a[1], b[1]):
            found.append({
                "name": "Double Top", "hebrew": "פסגה כפולה",
                "bias": "שלילי", "confidence": 65,
                "status": "אפשרית — נדרש אישור בשבירת תמיכה",
                "level": float(np.mean([a[1], b[1]]))
            })

    if len(lows) >= 2:
        a, b = lows[-2], lows[-1]
        if _near(a[1], b[1]):
            found.append({
                "name": "Double Bottom", "hebrew": "תחתית כפולה",
                "bias": "חיובי", "confidence": 65,
                "status": "אפשרית — נדרשת פריצה מעל שיא הביניים",
                "level": float(np.mean([a[1], b[1]]))
            })

    if len(highs) >= 3:
        l, h, r = highs[-3:]
        if _near(l[1], r[1], 0.05) and h[1] > l[1]*1.025 and h[1] > r[1]*1.025:
            found.append({
                "name": "Head & Shoulders", "hebrew": "ראש וכתפיים",
                "bias": "שלילי", "confidence": 60,
                "status": "מבנה אפשרי — נדרש אישור בשבירת קו הצוואר",
                "level": float(h[1])
            })

    if len(lows) >= 3:
        l, h, r = lows[-3:]
        if _near(l[1], r[1], 0.05) and h[1] < l[1]*0.975 and h[1] < r[1]*0.975:
            found.append({
                "name": "Inverse Head & Shoulders", "hebrew": "ראש וכתפיים הפוך",
                "bias": "חיובי", "confidence": 60,
                "status": "מבנה אפשרי — נדרשת פריצה מעל קו הצוואר",
                "level": float(h[1])
            })

    return sorted(found, key=lambda x: x["confidence"], reverse=True)


def safe(v):
    try:
        if v is None or pd.isna(v): return None
        return float(v)
    except Exception:
        return None

def analyze_fundamentals(info, quote_type):
    if quote_type != "EQUITY":
        return {"available": False, "score": None, "valuation_score": None, "long_score": None, "fields": {}}

    f = {
        "revenue_growth": safe(info.get("revenueGrowth")),
        "earnings_growth": safe(info.get("earningsGrowth")),
        "profit_margin": safe(info.get("profitMargins")),
        "free_cash_flow": safe(info.get("freeCashflow")),
        "cash": safe(info.get("totalCash")),
        "debt": safe(info.get("totalDebt")),
        "forward_pe": safe(info.get("forwardPE")),
        "trailing_pe": safe(info.get("trailingPE")),
        "price_sales": safe(info.get("priceToSalesTrailing12Months")),
        "roe": safe(info.get("returnOnEquity")),
    }

    score, used = 50, 0
    for key in ["revenue_growth", "earnings_growth"]:
        v = f[key]
        if v is not None:
            used += 1
            score += 12 if v > .20 else 8 if v > .08 else 3 if v > 0 else -10
    if f["profit_margin"] is not None:
        used += 1
        v=f["profit_margin"]; score += 10 if v>.20 else 6 if v>.10 else 2 if v>0 else -10
    if f["free_cash_flow"] is not None:
        used += 1; score += 8 if f["free_cash_flow"] > 0 else -8
    if f["cash"] is not None and f["debt"] is not None:
        used += 1
        if f["cash"] > f["debt"]: score += 8
        elif f["debt"] > max(f["cash"],1)*3: score -= 8
    if f["roe"] is not None:
        used += 1
        score += 8 if f["roe"] > .20 else 4 if f["roe"] > .10 else 0

    valuation = 50
    pe=f["forward_pe"]
    if pe is not None:
        valuation += 15 if 0 < pe < 20 else 5 if pe < 30 else -15 if pe > 50 else 0
    ps=f["price_sales"]
    if ps is not None:
        valuation += 10 if 0 < ps < 5 else -10 if ps > 15 else 0

    score=max(0,min(100,score)); valuation=max(0,min(100,valuation))
    long_score=round(score*.7+valuation*.3)
    return {"available": used >= 2, "score": score, "valuation_score": valuation,
            "long_score": long_score, "fields": f, "used": used}

def classify_asset(symbol, info):
    q = (info.get("quoteType") or "").upper()
    if symbol.endswith("-USD") or q == "CRYPTOCURRENCY":
        return "CRYPTO"
    if "=X" in symbol or q == "CURRENCY":
        return "FX"
    if q in ["ETF", "MUTUALFUND"]:
        return "ETF"
    if q == "INDEX" or symbol.startswith("^"):
        return "INDEX"
    if q == "EQUITY":
        return "EQUITY"
    return q or "UNKNOWN"

def asset_explanation(asset_type):
    return {
        "EQUITY": "מניה — ניתוח טכני + עסקי + תמחור.",
        "ETF": "קרן סל — ניתוח מגמה/סיכון. אין להתייחס אליה כחברה בודדת.",
        "INDEX": "מדד — ניתוח שוק ומגמה, ללא רווחי חברה.",
        "CRYPTO": "קריפטו — ניתוח מחיר/מומנטום/סיכון בלבד.",
        "FX": "מט״ח — ניתוח מגמה ומומנטום; מאקרו דורש מקור נתונים נוסף.",
        "UNKNOWN": "סוג נכס לא זוהה במלואו."
    }.get(asset_type, "נכס פיננסי — הניתוח מותאם לפי הנתונים הזמינים.")


SECTOR_ETFS = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
    "Communication Services": "XLC",
}

def _perf(symbol, days=63):
    try:
        d=yf.Ticker(symbol).history(period="1y",auto_adjust=True)
        if len(d)<=days: return None
        return (float(d["Close"].iloc[-1])/float(d["Close"].iloc[-days])-1)*100
    except Exception:
        return None

def market_context(symbol, info, asset_type):
    ctx = {}
    if symbol.endswith(".TA"):
        benchmark = "^TA125.TA"
        ctx["benchmark_name"] = "ת״א-125"
    elif asset_type in ["EQUITY","ETF"]:
        benchmark = "SPY"
        ctx["benchmark_name"] = "S&P 500"
    else:
        benchmark = None

    ctx["benchmark_symbol"] = benchmark
    ctx["asset_3m"] = _perf(symbol,63)
    ctx["benchmark_3m"] = _perf(benchmark,63) if benchmark else None

    sector=info.get("sector")
    sector_etf=SECTOR_ETFS.get(sector)
    ctx["sector_name"]=sector or "לא זמין"
    ctx["sector_symbol"]=sector_etf
    ctx["sector_3m"]=_perf(sector_etf,63) if sector_etf else None

    if ctx["asset_3m"] is not None and ctx["benchmark_3m"] is not None:
        ctx["relative_market"]=ctx["asset_3m"]-ctx["benchmark_3m"]
    else:
        ctx["relative_market"]=None

    if ctx["asset_3m"] is not None and ctx["sector_3m"] is not None:
        ctx["relative_sector"]=ctx["asset_3m"]-ctx["sector_3m"]
    else:
        ctx["relative_sector"]=None
    return ctx


def state_signature(row):
    return {
        "above50": row["Close"] > row["MA50"],
        "above200": row["Close"] > row["MA200"],
        "ma50above200": row["MA50"] > row["MA200"],
        "macdpos": row["MACD"] > row["MACD_SIGNAL"],
        "rsi_band": 0 if row["RSI"] < 40 else 1 if row["RSI"] <= 60 else 2,
    }

def analog_backtest(data):
    """
    Finds historical states similar to today's technical state.
    This is descriptive historical evidence, not a calibrated probability forecast.
    """
    d=data.dropna(subset=["MA50","MA200","RSI","MACD","MACD_SIGNAL"]).copy()
    if len(d)<260:
        return {}

    today=state_signature(d.iloc[-1])
    matches=[]
    # Exclude last year from candidate pool when possible, to reduce overlap with current state.
    end=max(0,len(d)-252)
    for i in range(200,end):
        s=state_signature(d.iloc[i])
        similarity=sum(s[k]==today[k] for k in today)/len(today)
        if similarity >= .8:
            matches.append(i)

    out={}
    for label,h in [("חודש",21),("3 חודשים",63),("שנה",252)]:
        vals=[]
        for i in matches:
            if i+h < len(d):
                vals.append((float(d["Close"].iloc[i+h])/float(d["Close"].iloc[i])-1)*100)
        arr=np.array(vals,dtype=float)
        out[label]={
            "samples": int(len(arr)),
            "positive_pct": float((arr>0).mean()*100) if len(arr) else None,
            "avg_return": float(arr.mean()) if len(arr) else None,
            "median_return": float(np.median(arr)) if len(arr) else None,
            "worst": float(arr.min()) if len(arr) else None,
            "best": float(arr.max()) if len(arr) else None,
        }
    return out


def price_chart(data, levels, candles=True, averages=True, zones=True):
    fig=go.Figure()
    if candles:
        fig.add_trace(go.Candlestick(
            x=data.index, open=data["Open"], high=data["High"],
            low=data["Low"], close=data["Close"], name="מחיר"))
    else:
        fig.add_trace(go.Scatter(x=data.index,y=data["Close"],name="מחיר"))
    if averages:
        for col in ["MA20","MA50","MA200"]:
            if col in data:
                fig.add_trace(go.Scatter(x=data.index,y=data[col],name=col))
    if zones:
        sl,sh=levels["support_zone"]; rl,rh=levels["resistance_zone"]
        fig.add_hrect(y0=sl,y1=sh,opacity=.12,line_width=0,annotation_text="אזור תמיכה")
        fig.add_hrect(y0=rl,y1=rh,opacity=.12,line_width=0,annotation_text="אזור התנגדות")
    fig.update_layout(height=620,xaxis_rangeslider_visible=False,
                      hovermode="x unified",yaxis_title="מחיר")
    return fig

def volume_chart(data):
    fig=go.Figure(go.Bar(x=data.index,y=data["Volume"],name="מחזור"))
    fig.update_layout(height=240,yaxis_title="מחזור")
    return fig



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