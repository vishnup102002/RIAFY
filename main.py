"""
Personal Expense Tracker — FastAPI Backend
SQLite database via SQLAlchemy, Pydantic validation, full CRUD + summary.
"""

from __future__ import annotations

import datetime as dt
from datetime import datetime
import enum
import re
from typing import Optional

import uvicorn
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import (
    Column,
    Date,
    Float,
    Integer,
    String,
    create_engine,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

# ──────────────────────────────────────────────
# Database setup
# ──────────────────────────────────────────────
DATABASE_URL = "sqlite:///./expenses.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


# ──────────────────────────────────────────────
# Category enum
# ──────────────────────────────────────────────
class CategoryEnum(str, enum.Enum):
    FOOD = "Food"
    TRANSPORT = "Transport"
    SHOPPING = "Shopping"
    BILLS = "Bills"
    ENTERTAINMENT = "Entertainment"
    OTHER = "Other"


# ──────────────────────────────────────────────
# SQLAlchemy model
# ──────────────────────────────────────────────
class Expense(Base):
    __tablename__ = "expenses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    title = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    category = Column(String, nullable=False)
    date = Column(Date, nullable=False, default=dt.date.today)
    note = Column(String, nullable=True)


Base.metadata.create_all(bind=engine)


# ──────────────────────────────────────────────
# Pydantic schemas
# ──────────────────────────────────────────────
class ExpenseCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="Expense title")
    amount: float = Field(..., description="Expense amount")
    category: CategoryEnum
    date: str | dt.date = Field(..., description="Expense date (YYYY-MM-DD)")
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Title cannot be empty or just whitespace.")
        return v.strip()

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Enter valid amount.")
        return round(v, 2)

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @field_validator("date")
    @classmethod
    def verify_strict_raw_calendar_date(cls, v):
        if isinstance(v, dt.date):
            if v.year < 1 or v == dt.date(1, 1, 1):
                raise ValueError("Enter valid date.")
            if v > dt.date.today():
                raise ValueError("Expense date cannot be in the future.")
            return v
        if not v or not v.strip():
            raise ValueError("Date field cannot be empty.")
        
        # Strip any leading/trailing whitespace from user input
        cleaned_date = v.strip()
        
        try:
            # Attempt to parse strict YYYY-MM-DD math boundaries
            parsed_date = datetime.strptime(cleaned_date, "%Y-%m-%d").date()
            if parsed_date > dt.date.today():
                raise ValueError("Expense date cannot be in the future.")
            return parsed_date
        except ValueError as exc:
            if str(exc) == "Expense date cannot be in the future.":
                raise
            raise ValueError(f"'{cleaned_date}' is an invalid calendar date. Please use YYYY-MM-DD format with real calendar values.")


class ExpenseUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    amount: Optional[float] = Field(None)
    category: Optional[CategoryEnum] = None
    date: Optional[str | dt.date] = None
    note: Optional[str] = Field(None, max_length=500)

    @field_validator("title")
    @classmethod
    def title_must_not_be_empty(cls, v: str | None) -> str | None:
        if v is not None and not v.strip():
            raise ValueError("Title cannot be empty or just whitespace.")
        return v.strip() if v else v

    @field_validator("amount")
    @classmethod
    def amount_must_be_positive(cls, v: float | None) -> float | None:
        if v is not None and v <= 0:
            raise ValueError("Enter valid amount.")
        return round(v, 2) if v is not None else v

    @field_validator("note", mode="before")
    @classmethod
    def sanitize_note(cls, v):
        if v is not None and isinstance(v, str):
            v = v.strip()
            return v if v else None
        return v

    @field_validator("date")
    @classmethod
    def verify_strict_raw_calendar_date(cls, v):
        if v is None:
            return v
        if isinstance(v, dt.date):
            if v.year < 1 or v == dt.date(1, 1, 1):
                raise ValueError("Enter valid date.")
            if v > dt.date.today():
                raise ValueError("Expense date cannot be in the future.")
            return v
        if not v or not v.strip():
            raise ValueError("Date field cannot be empty.")
        
        # Strip any leading/trailing whitespace from user input
        cleaned_date = v.strip()
        
        try:
            # Attempt to parse strict YYYY-MM-DD math boundaries
            parsed_date = datetime.strptime(cleaned_date, "%Y-%m-%d").date()
            if parsed_date > dt.date.today():
                raise ValueError("Expense date cannot be in the future.")
            return parsed_date
        except ValueError as exc:
            if str(exc) == "Expense date cannot be in the future.":
                raise
            raise ValueError(f"'{cleaned_date}' is an invalid calendar date. Please use YYYY-MM-DD format with real calendar values.")


class ExpenseResponse(BaseModel):
    id: int
    title: str
    amount: float
    category: str
    date: dt.date
    note: Optional[str] = None

    class Config:
        from_attributes = True


class SummaryResponse(BaseModel):
    total_spent: float
    breakdown: dict[str, float]


# ──────────────────────────────────────────────
# FastAPI application
# ──────────────────────────────────────────────
app = FastAPI(title="Personal Expense Tracker", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent


@app.get("/", include_in_schema=False)
async def serve_frontend():
    return FileResponse(BASE_DIR / "index.html")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    # Extract readable error messages
    errors = exc.errors()
    details = []
    for error in errors:
        loc = " -> ".join(str(x) for x in error.get("loc", []))
        msg = error.get("msg", "Validation error")
        details.append(f"{loc}: {msg}")
    return JSONResponse(
        status_code=400,
        content={"detail": "; ".join(details)},
    )


# ──────────────────────────────────────────────
# Helper: DB session dependency
# ──────────────────────────────────────────────
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ──────────────────────────────────────────────
# POST /api/expenses — Create
# ──────────────────────────────────────────────
@app.post("/api/expenses", response_model=ExpenseResponse, status_code=201)
def create_expense(payload: ExpenseCreate, db: Session = Depends(get_db)):
    try:
        expense = Expense(
            title=payload.title,
            amount=payload.amount,
            category=payload.category.value,
            date=payload.date,
            note=payload.note,
        )
        db.add(expense)
        db.commit()
        db.refresh(expense)
        return expense
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# ──────────────────────────────────────────────
# GET /api/expenses — List with optional filters
# ──────────────────────────────────────────────
@app.get("/api/expenses", response_model=list[ExpenseResponse])
def list_expenses(
    category: Optional[str] = Query(None, description="Exact category match"),
    start_date: Optional[dt.date] = Query(None, description="Start date (inclusive)"),
    end_date: Optional[dt.date] = Query(None, description="End date (inclusive)"),
    title: Optional[str] = Query(None, description="Partial case-insensitive title search"),
    db: Session = Depends(get_db),
):
    try:
        # Gracefully handle end_date before start_date in filters
        if start_date and end_date and end_date < start_date:
            return []

        query = db.query(Expense)

        if category:
            # Validate category value
            try:
                CategoryEnum(category)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid category '{category}'. Must be one of: {[c.value for c in CategoryEnum]}",
                )
            query = query.filter(Expense.category == category)

        if start_date:
            query = query.filter(Expense.date >= start_date)

        if end_date:
            query = query.filter(Expense.date <= end_date)

        if title:
            # Strip title search and escape SQL wildcard characters
            search_title = title.strip()
            if search_title:
                # Escape %, _, and \ to prevent them being interpreted as SQL wildcards
                escaped = (
                    search_title
                    .replace("\\", "\\\\")
                    .replace("%", "\\%")
                    .replace("_", "\\_")
                )
                query = query.filter(Expense.title.ilike(f"%{escaped}%", escape="\\"))

        expenses = query.order_by(Expense.date.desc(), Expense.id.desc()).all()
        return expenses
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# ──────────────────────────────────────────────
# GET /api/expenses/summary — Monthly summary
# ──────────────────────────────────────────────
@app.get("/api/expenses/summary", response_model=SummaryResponse)
def monthly_summary(db: Session = Depends(get_db)):
    try:
        today = dt.date.today()
        current_month = today.month
        current_year = today.year

        # Start and end of the current calendar month
        start_of_month = dt.date(current_year, current_month, 1)
        if current_month == 12:
            end_of_month = dt.date(current_year, 12, 31)
        else:
            end_of_month = dt.date(current_year, current_month + 1, 1) - dt.timedelta(days=1)

        # All expenses strictly within the current calendar month
        month_expenses = (
            db.query(Expense)
            .filter(
                Expense.date >= start_of_month,
                Expense.date <= end_of_month,
            )
            .all()
        )

        total_spent = round(sum(e.amount for e in month_expenses), 2)
        breakdown: dict[str, float] = {}
        for e in month_expenses:
            breakdown[e.category] = round(breakdown.get(e.category, 0.0) + e.amount, 2)

        return SummaryResponse(
            total_spent=round(total_spent, 2),
            breakdown=breakdown,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# ──────────────────────────────────────────────
# PUT /api/expenses/{id} — Update
# ──────────────────────────────────────────────
@app.put("/api/expenses/{expense_id}", response_model=ExpenseResponse)
def update_expense(expense_id: int, payload: ExpenseUpdate, db: Session = Depends(get_db)):
    try:
        expense = db.query(Expense).filter(Expense.id == expense_id).first()
        if not expense:
            raise HTTPException(status_code=404, detail=f"Expense with id {expense_id} not found")

        update_data = payload.model_dump(exclude_unset=True)
        if "category" in update_data and update_data["category"] is not None:
            update_data["category"] = update_data["category"].value

        for key, value in update_data.items():
            setattr(expense, key, value)

        db.commit()
        db.refresh(expense)
        return expense
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# ──────────────────────────────────────────────
# DELETE /api/expenses/{id} — Delete
# ──────────────────────────────────────────────
@app.delete("/api/expenses/{expense_id}")
def delete_expense(expense_id: int, db: Session = Depends(get_db)):
    try:
        expense = db.query(Expense).filter(Expense.id == expense_id).first()
        if not expense:
            raise HTTPException(status_code=404, detail=f"Expense with id {expense_id} not found")
        db.delete(expense)
        db.commit()
        return {"detail": f"Expense {expense_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Database error: {exc}") from exc


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
