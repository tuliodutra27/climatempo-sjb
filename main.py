import asyncio
from datetime import datetime, date
from fastapi import FastAPI, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
import httpx
import pytz

app = FastAPI()
templates = Jinja2Templates(directory="templates")

LAT = -21.637
LON = -41.051
TIMEZONE = "America/Sao_Paulo"

WIND_DIRS = ["N","NNE","NE","ENE","L","ESE","SE","SSE","S","SSO","SO","OSO","O","ONO","NO","NNO"]
DAYS_PT = ["Segunda-feira","Terça-feira","Quarta-feira","Quinta-feira","Sexta-feira","Sábado","Domingo"]


def moon_phase(dt: date) -> tuple[str, str]:
    ref = date(2000, 1, 6)
    phase = ((dt - ref).days % 29.53) / 29.53
    if phase < 0.03 or phase > 0.97:
        return "Lua nova", "🌑"
    elif phase < 0.22:
        return "Lua crescente", "🌒"
    elif phase < 0.28:
        return "Quarto crescente", "🌓"
    elif phase < 0.47:
        return "Lua gibosa crescente", "🌔"
    elif phase < 0.53:
        return "Lua cheia", "🌕"
    elif phase < 0.72:
        return "Lua gibosa minguante", "🌖"
    elif phase < 0.78:
        return "Quarto minguante", "🌗"
    return "Lua minguante", "🌘"


def deg_to_dir(deg: float) -> str:
    return WIND_DIRS[round(deg / 22.5) % 16]


def uv_label(uv: float) -> str:
    if uv <= 2: return "Baixo"
    if uv <= 5: return "Moderado"
    if uv <= 7: return "Alto"
    if uv <= 10: return "Muito alto"
    return "Extremo"


def rain_label(pct: int) -> str:
    if pct >= 70: return "Alta"
    if pct >= 40: return "Moderada"
    return "Baixa"


async def fetch_dados() -> dict:
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)

    async with httpx.AsyncClient(timeout=10) as client:
        w, m = await asyncio.gather(
            client.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": LAT, "longitude": LON,
                    "current": "temperature_2m,apparent_temperature,precipitation_probability,"
                               "wind_speed_10m,wind_gusts_10m,wind_direction_10m,uv_index",
                    "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,"
                             "sunrise,sunset,precipitation_probability_max",
                    "wind_speed_unit": "kmh", "timezone": TIMEZONE, "forecast_days": 1,
                },
            ),
            client.get(
                "https://marine-api.open-meteo.com/v1/marine",
                params={
                    "latitude": LAT, "longitude": LON,
                    "current": "wave_height,wave_period,wave_direction",
                    "timezone": TIMEZONE,
                },
            ),
        )

    cur = w.json()["current"]
    daily = w.json()["daily"]
    mar = m.json().get("current", {})

    rain_pct = daily["precipitation_probability_max"][0] or 0
    wind_speed = round(cur["wind_speed_10m"])
    wind_gust = round(cur["wind_gusts_10m"])
    wind_dir = deg_to_dir(cur["wind_direction_10m"])
    uv = round(cur["uv_index"])
    precip_sum = round(daily["precipitation_sum"][0] or 0.0, 1)
    wave_height = round(mar.get("wave_height") or 0, 1)
    wave_period = round(mar.get("wave_period") or 0)
    wave_dir = deg_to_dir(mar.get("wave_direction") or 0)
    moon_name, moon_emoji = moon_phase(now.date())
    sunrise = daily["sunrise"][0].split("T")[1][:5]
    sunset = daily["sunset"][0].split("T")[1][:5]
    day_name = DAYS_PT[now.weekday()]

    alerts = []
    if rain_pct >= 70:
        alerts.append("atenção às chuvas")
    if wind_gust >= 40:
        alerts.append("vento forte")

    return {
        "date_str": f"{day_name} · {now.day}/{now.month}/{now.year}",
        "updated_at": now.strftime("%H:%M"),
        "temp_max": round(daily["temperature_2m_max"][0]),
        "temp_min": round(daily["temperature_2m_min"][0]),
        "temp_feels": round(cur["apparent_temperature"]),
        "temp_current": round(cur["temperature_2m"]),
        "moon_name": moon_name,
        "moon_emoji": moon_emoji,
        "rain_pct": rain_pct,
        "rain_label": rain_label(rain_pct),
        "wind_speed": wind_speed,
        "wind_gust": wind_gust,
        "wind_dir": wind_dir,
        "uv": uv,
        "uv_label": uv_label(uv),
        "precip_sum": precip_sum,
        "wave_height": wave_height,
        "wave_period": wave_period,
        "wave_dir": wave_dir,
        "sunrise": sunrise,
        "sunset": sunset,
        "alerts": alerts,
    }


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    dados = await fetch_dados()
    return templates.TemplateResponse("index.html", {"request": request, **dados})


@app.get("/api/dados")
async def api_dados():
    return await fetch_dados()
