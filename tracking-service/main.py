from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from database import Base, engine, get_db, wait_for_db
from models import RunningRecord, WorkoutSession, WorkoutSet
from schemas import ExerciseStats, RecordIn, RecordOut, SessionIn, SessionOut
from security import read_access_token

bearer = HTTPBearer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    wait_for_db()
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="Muscu Track - tracking-service", lifespan=lifespan)


def get_user_id(credentials: HTTPAuthorizationCredentials = Depends(bearer)) -> int:
    user_id = read_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Jeton invalide ou expiré")
    return user_id


def get_owned(db: Session, model, item_id: int, user_id: int):
    # 404 aussi quand l'objet appartient à un autre utilisateur : on ne révèle pas qu'il existe.
    item = db.get(model, item_id)
    if item is None or item.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Introuvable")
    return item


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "tracking-service"}


# --- Séances de musculation ---


@app.post("/sessions", response_model=SessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    body: SessionIn,
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> WorkoutSession:
    session = WorkoutSession(
        user_id=user_id,
        performed_on=body.performed_on,
        notes=body.notes or None,
        sets=[
            WorkoutSet(position=i, **workout_set.model_dump())
            for i, workout_set in enumerate(body.sets)
        ],
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


@app.get("/sessions", response_model=list[SessionOut])
def list_sessions(
    user_id: int = Depends(get_user_id), db: Session = Depends(get_db)
) -> list[WorkoutSession]:
    query = (
        select(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
        .options(selectinload(WorkoutSession.sets))
        .order_by(WorkoutSession.performed_on.desc(), WorkoutSession.id.desc())
    )
    return list(db.scalars(query))


@app.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(
    session_id: int,
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> WorkoutSession:
    return get_owned(db, WorkoutSession, session_id, user_id)


@app.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    session_id: int,
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(get_owned(db, WorkoutSession, session_id, user_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/exercises", response_model=list[ExerciseStats])
def list_exercises(
    user_id: int = Depends(get_user_id), db: Session = Depends(get_db)
) -> list[ExerciseStats]:
    rows = db.execute(
        select(WorkoutSet, WorkoutSession.performed_on)
        .join(WorkoutSession)
        .where(WorkoutSession.user_id == user_id)
    )
    # Regroupe sans tenir compte de la casse : "Squat" et "squat" sont le même exercice.
    stats: dict[str, ExerciseStats] = {}
    for workout_set, performed_on in rows:
        key = workout_set.exercise.casefold()
        current = stats.get(key)
        if current is None:
            stats[key] = ExerciseStats(
                exercise=workout_set.exercise,
                best_weight_kg=workout_set.weight_kg,
                total_sets=1,
                last_performed_on=performed_on,
            )
            continue
        current.total_sets += 1
        current.best_weight_kg = max(current.best_weight_kg, workout_set.weight_kg)
        if performed_on >= current.last_performed_on:
            current.last_performed_on = performed_on
            current.exercise = workout_set.exercise
    return sorted(stats.values(), key=lambda s: s.exercise.casefold())


# --- Records de course à pied ---


@app.post("/records", response_model=RecordOut, status_code=status.HTTP_201_CREATED)
def create_record(
    body: RecordIn,
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> RunningRecord:
    record = RunningRecord(user_id=user_id, **body.model_dump())
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@app.get("/records", response_model=list[RecordOut])
def list_records(
    user_id: int = Depends(get_user_id), db: Session = Depends(get_db)
) -> list[RunningRecord]:
    query = (
        select(RunningRecord)
        .where(RunningRecord.user_id == user_id)
        .order_by(RunningRecord.performed_on.desc(), RunningRecord.id.desc())
    )
    return list(db.scalars(query))


@app.get("/records/best", response_model=list[RecordOut])
def best_records(
    user_id: int = Depends(get_user_id), db: Session = Depends(get_db)
) -> list[RunningRecord]:
    # Le meilleur temps par distance ; à égalité, le plus ancien garde le record.
    query = (
        select(RunningRecord)
        .where(RunningRecord.user_id == user_id)
        .order_by(RunningRecord.duration_seconds, RunningRecord.performed_on)
    )
    best: dict[str, RunningRecord] = {}
    for record in db.scalars(query):
        best.setdefault(record.distance, record)
    return list(best.values())


@app.delete("/records/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(
    record_id: int,
    user_id: int = Depends(get_user_id),
    db: Session = Depends(get_db),
) -> Response:
    db.delete(get_owned(db, RunningRecord, record_id, user_id))
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
