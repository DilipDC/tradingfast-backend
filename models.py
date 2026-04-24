from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, Field, validator
from enum import Enum

# ========== ENUMS ==========
class TradeDirection(str, Enum):
    UP = "UP"
    DOWN = "DOWN"

class TradeResult(str, Enum):
    WIN = "win"
    LOSS = "loss"
    PENDING = "pending"

class TransactionType(str, Enum):
    DEPOSIT = "deposit"
    WITHDRAW = "withdraw"

class TransactionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"

class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"

# ========== USER MODELS ==========
class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserProfileUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    dob: Optional[str] = None
    location: Optional[str] = None
    bio: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    created_at: datetime

class UserProfileResponse(BaseModel):
    user_id: str
    balance: float
    avatar: str
    dob: Optional[str]
    location: Optional[str]
    bio: Optional[str]
    phone: Optional[str]
    total_trades: int
    wins: int
    losses: int

# ========== STOCK MODELS ==========
class Stock(BaseModel):
    id: int
    name: str
    symbol: str
    price: float
    min_price: float
    max_price: float
    is_active: bool
    updated_at: datetime

class StockUpdate(BaseModel):
    name: Optional[str] = None
    symbol: Optional[str] = None
    min_price: Optional[float] = None
    max_price: Optional[float] = None
    is_active: Optional[bool] = None

# ========== TRADE MODELS ==========
class PlaceTradeRequest(BaseModel):
    stock_id: int
    direction: TradeDirection
    amount: float = Field(..., ge=10, le=100000)
    duration_minutes: int = Field(..., ge=1, le=5)

    @validator('amount')
    def validate_amount(cls, v):
        if v < 10:
            raise ValueError('Minimum trade amount is ₹10')
        return v

class TradeResponse(BaseModel):
    id: int
    stock_id: int
    stock_name: str
    stock_symbol: str
    direction: str
    amount: float
    duration_minutes: int
    entry_price: float
    exit_price: Optional[float]
    profit: Optional[float]
    result: str
    status: str
    placed_at: datetime
    expires_at: datetime

# ========== PAYMENT MODELS ==========
class DepositRequest(BaseModel):
    amount: float = Field(..., ge=100, le=100000)

class WithdrawRequest(BaseModel):
    amount: float = Field(..., ge=100, le=50000)
    upi_id: str = Field(..., min_length=3)
    upi_name: str = Field(..., min_length=2)

class TransactionResponse(BaseModel):
    id: int
    type: str
    amount: float
    status: str
    upi_id: Optional[str]
    upi_name: Optional[str]
    requested_at: datetime
    approved_at: Optional[datetime]

# ========== ADMIN MODELS ==========
class AdminLogin(BaseModel):
    username: str
    password: str

class AdminSettingsUpdate(BaseModel):
    deposit_enabled: Optional[bool] = None
    withdraw_enabled: Optional[bool] = None
    trading_enabled: Optional[bool] = None
    profit_percentage: Optional[int] = Field(None, ge=10, le=200)
    deposit_start_time: Optional[str] = None
    deposit_end_time: Optional[str] = None
    withdraw_start_time: Optional[str] = None
    withdraw_end_time: Optional[str] = None
    trade_window_duration_sec: Optional[int] = Field(None, ge=1, le=10)
    trade_window_interval_sec: Optional[int] = Field(None, ge=30, le=300)

class DashboardStats(BaseModel):
    total_users: int
    total_balance: float
    total_trades: int
    pending_deposits: int
    pending_withdrawals: int
    active_trades: int
    up_down_distribution: dict

# ========== COMMON RESPONSES ==========
class APIResponse(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class AuthResponse(BaseModel):
    access_token: str
    user: UserResponse