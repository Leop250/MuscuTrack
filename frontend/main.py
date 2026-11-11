from datetime import date
from pathlib import Path

import httpx
from fastapi import FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import api

BASE_DIR = Path(__file__).parent
ACCESS_COOKIE = "access_token"
PENDING_2FA_COOKIE = "pending_2fa"
ACCESS_COOKIE_MAX_AGE = 3600  # même durée que le JWT délivré par auth-service
PENDING_2FA_COOKIE_MAX_AGE = 300
EMPTY_SET_ROWS = 6

DISTANCES = {
    "5k": "5 km",
    "10k": "10 km",
    "semi": "Semi-marathon",
    "marathon": "Marathon",
}


def format_duration(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def format_weight(weight: float) -> str:
    return f"{weight:g}"


templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["duration"] = format_duration
templates.env.filters["weight"] = format_weight
templates.env.globals["DISTANCES"] = DISTANCES

app = FastAPI(title="Muscu Track - frontend", docs_url=None, redoc_url=None)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


class LoginRequired(Exception):
    pass


@app.exception_handler(LoginRequired)
def login_required_handler(request: Request, exc: LoginRequired) -> Response:
    response = redirect("/login")
    response.delete_cookie(ACCESS_COOKIE)
    return response


@app.exception_handler(httpx.HTTPError)
def service_error_handler(request: Request, exc: httpx.HTTPError) -> Response:
    return render(request, "error.html", status.HTTP_503_SERVICE_UNAVAILABLE)


# --- Outils ---


def render(request: Request, template: str, status_code: int = 200, **context) -> HTMLResponse:
    context.setdefault("logged_in", ACCESS_COOKIE in request.cookies)
    return templates.TemplateResponse(request, template, context, status_code=status_code)


def redirect(url: str) -> RedirectResponse:
    # 303 : après un POST, le navigateur recharge la page cible en GET.
    return RedirectResponse(url, status_code=status.HTTP_303_SEE_OTHER)


def set_cookie(request: Request, response: Response, name: str, value: str, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,  # inaccessible au JavaScript de la page
        samesite="lax",  # pas envoyé par les formulaires d'autres sites
        secure=request.url.scheme == "https",
    )


def login_response(request: Request, access_token: str) -> Response:
    response = redirect("/dashboard")
    set_cookie(request, response, ACCESS_COOKIE, access_token, ACCESS_COOKIE_MAX_AGE)
    response.delete_cookie(PENDING_2FA_COOKIE)
    return response


def get_token(request: Request) -> str:
    token = request.cookies.get(ACCESS_COOKIE)
    if not token:
        raise LoginRequired
    return token


def protected(service, request: Request, method: str, path: str, **kwargs) -> httpx.Response:
    # Appel d'un service avec le jeton de l'utilisateur ; jeton expiré -> retour à la connexion.
    response = service(method, path, get_token(request), **kwargs)
    if response.status_code == status.HTTP_401_UNAUTHORIZED:
        raise LoginRequired
    return response


def to_int(value: str) -> int:
    return int(value.strip() or 0)


# --- Pages publiques ---


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "frontend"}


@app.get("/")
def home(request: Request) -> Response:
    return redirect("/dashboard" if ACCESS_COOKIE in request.cookies else "/login")


@app.get("/register")
def register_page(request: Request) -> Response:
    return render(request, "register.html")


@app.post("/register")
def register(
    request: Request,
    email: str = Form(),
    password: str = Form(),
    password_confirm: str = Form(),
) -> Response:
    def error(message: str) -> Response:
        return render(request, "register.html", 400, error=message, email=email)

    if password != password_confirm:
        return error("Les deux mots de passe ne correspondent pas.")
    credentials = {"email": email, "password": password}
    response = api.auth("POST", "/register", json=credentials)
    if response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
        return error("Email invalide ou mot de passe trop court (8 caractères minimum).")
    if response.status_code != status.HTTP_201_CREATED:
        return error(api.error_detail(response, "Inscription impossible."))
    # Compte créé : connexion directe (pas de 2FA sur un compte neuf).
    login = api.auth("POST", "/login", json=credentials).json()
    return login_response(request, login["access_token"])


@app.get("/login")
def login_page(request: Request) -> Response:
    return render(request, "login.html")


@app.post("/login")
def login(request: Request, email: str = Form(), password: str = Form()) -> Response:
    response = api.auth("POST", "/login", json={"email": email, "password": password})
    if response.status_code != status.HTTP_200_OK:
        return render(request, "login.html", 401, error="Email ou mot de passe incorrect.", email=email)
    body = response.json()
    if body.get("two_factor_required"):
        result = redirect("/login/2fa")
        set_cookie(request, result, PENDING_2FA_COOKIE, body["temporary_token"], PENDING_2FA_COOKIE_MAX_AGE)
        return result
    return login_response(request, body["access_token"])


@app.get("/login/2fa")
def login_2fa_page(request: Request) -> Response:
    if PENDING_2FA_COOKIE not in request.cookies:
        return redirect("/login")
    return render(request, "login_2fa.html")


@app.post("/login/2fa")
def login_2fa(request: Request, code: str = Form()) -> Response:
    temporary_token = request.cookies.get(PENDING_2FA_COOKIE)
    if not temporary_token:
        return redirect("/login")
    response = api.auth(
        "POST", "/login/2fa", json={"temporary_token": temporary_token, "code": code.strip()}
    )
    if response.status_code == status.HTTP_200_OK:
        return login_response(request, response.json()["access_token"])
    if response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
        message = "Le code doit contenir 6 chiffres."
    else:
        message = api.error_detail(response, "Code incorrect.")
    return render(request, "login_2fa.html", response.status_code, error=message)


@app.post("/logout")
def logout() -> Response:
    response = redirect("/login")
    response.delete_cookie(ACCESS_COOKIE)
    return response


# --- Tableau de bord ---


@app.get("/dashboard")
def dashboard(request: Request) -> Response:
    sessions = protected(api.tracking, request, "GET", "/sessions").json()
    best = protected(api.tracking, request, "GET", "/records/best").json()
    exercises = protected(api.tracking, request, "GET", "/exercises").json()
    best.sort(key=lambda r: list(DISTANCES).index(r["distance"]))
    return render(
        request,
        "dashboard.html",
        sessions=sessions[:5],
        best_records=best,
        exercises=exercises,
    )


# --- Séances de musculation ---


def session_form(request: Request, status_code: int = 200, **context) -> HTMLResponse:
    rows = context.pop("rows", [])
    rows += [{"exercise": "", "reps": "", "weight_kg": ""}] * max(EMPTY_SET_ROWS - len(rows), 1)
    context.setdefault("performed_on", date.today().isoformat())
    return render(request, "session_new.html", status_code, rows=rows, **context)


@app.get("/sessions")
def sessions_page(request: Request) -> Response:
    sessions = protected(api.tracking, request, "GET", "/sessions").json()
    return render(request, "sessions.html", sessions=sessions)


@app.get("/sessions/new")
def new_session_page(request: Request) -> Response:
    get_token(request)
    return session_form(request)


@app.post("/sessions/new")
async def create_session(request: Request) -> Response:
    form = await request.form()
    performed_on = str(form.get("performed_on", ""))
    notes = str(form.get("notes", ""))
    rows = [
        {"exercise": str(e).strip(), "reps": str(r).strip(), "weight_kg": str(w).strip()}
        for e, r, w in zip(form.getlist("exercise"), form.getlist("reps"), form.getlist("weight_kg"))
    ]
    rows = [row for row in rows if any(row.values())]  # lignes laissées vides

    def error(message: str) -> Response:
        return session_form(request, 400, error=message, rows=rows, performed_on=performed_on, notes=notes)

    if not rows:
        return error("Ajoute au moins une série.")
    try:
        sets = [
            {
                "exercise": row["exercise"],
                "reps": int(row["reps"]),
                "weight_kg": float(row["weight_kg"].replace(",", ".")),
            }
            for row in rows
        ]
    except ValueError:
        return error("Chaque série doit avoir un nombre de répétitions et un poids.")

    body = {"performed_on": performed_on, "notes": notes or None, "sets": sets}
    response = protected(api.tracking, request, "POST", "/sessions", json=body)
    if response.status_code != status.HTTP_201_CREATED:
        return error("Vérifie la date et les séries : exercice renseigné, 1 à 1000 répétitions, 0 à 1000 kg.")
    return redirect(f"/sessions/{response.json()['id']}")


@app.get("/sessions/{session_id}")
def session_page(request: Request, session_id: int) -> Response:
    response = protected(api.tracking, request, "GET", f"/sessions/{session_id}")
    if response.status_code == status.HTTP_404_NOT_FOUND:
        return render(request, "error.html", 404, message="Cette séance n'existe pas.")
    return render(request, "session_detail.html", session=response.json())


@app.post("/sessions/{session_id}/delete")
def delete_session(request: Request, session_id: int) -> Response:
    protected(api.tracking, request, "DELETE", f"/sessions/{session_id}")
    return redirect("/sessions")


# --- Records de course à pied ---


def records_page_response(request: Request, status_code: int = 200, **context) -> HTMLResponse:
    records = protected(api.tracking, request, "GET", "/records").json()
    best = protected(api.tracking, request, "GET", "/records/best").json()
    context.setdefault("form", {"performed_on": date.today().isoformat()})
    return render(
        request,
        "records.html",
        status_code,
        records=records,
        best_ids={r["id"] for r in best},
        **context,
    )


@app.get("/records")
def records_page(request: Request) -> Response:
    return records_page_response(request)


@app.post("/records")
def create_record(
    request: Request,
    distance: str = Form(),
    hours: str = Form(""),
    minutes: str = Form(""),
    seconds: str = Form(""),
    performed_on: str = Form(),
) -> Response:
    form = {"distance": distance, "hours": hours, "minutes": minutes, "seconds": seconds, "performed_on": performed_on}
    try:
        duration = to_int(hours) * 3600 + to_int(minutes) * 60 + to_int(seconds)
    except ValueError:
        duration = 0
    body = {"distance": distance, "duration_seconds": duration, "performed_on": performed_on}
    response = protected(api.tracking, request, "POST", "/records", json=body)
    if response.status_code != status.HTTP_201_CREATED:
        return records_page_response(request, 400, error="Vérifie la distance, le temps et la date.", form=form)
    return redirect("/records")


@app.post("/records/{record_id}/delete")
def delete_record(request: Request, record_id: int) -> Response:
    protected(api.tracking, request, "DELETE", f"/records/{record_id}")
    return redirect("/records")


# --- Compte et double authentification ---


@app.get("/account")
def account_page(request: Request) -> Response:
    user = protected(api.auth, request, "GET", "/me").json()
    return render(request, "account.html", user=user)


@app.post("/account/2fa/setup")
def setup_2fa(request: Request) -> Response:
    response = protected(api.auth, request, "POST", "/2fa/setup")
    if response.status_code != status.HTTP_200_OK:
        return redirect("/account")
    return render(request, "account_2fa.html", setup=response.json())


@app.post("/account/2fa/verify")
def verify_2fa(
    request: Request,
    code: str = Form(),
    secret: str = Form(),
    qr_code: str = Form(),
) -> Response:
    response = protected(api.auth, request, "POST", "/2fa/verify", json={"code": code.strip()})
    if response.status_code == status.HTTP_200_OK:
        return redirect("/account")
    if response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT:
        message = "Le code doit contenir 6 chiffres."
    else:
        message = api.error_detail(response, "Code incorrect.")
    # Réaffiche le même QR code : le secret n'a pas changé côté auth-service.
    if not qr_code.startswith("data:image/png;base64,"):
        qr_code = ""
    setup = {"secret": secret, "qr_code": qr_code}
    return render(request, "account_2fa.html", 400, setup=setup, error=message)
