import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta
from app.infrastructure.supabase.supabase_database import SupabaseDatabase
from app.schemas.user import PlanEnum

# Mock fixed dates for deterministic testing:
# Wed, July 8, 2026 (Weekday = 2)
MOCK_NOW_WED = datetime(2026, 7, 8, 12, 0, 0, tzinfo=timezone.utc)
# Thu, July 9, 2026 (Weekday = 3) - Same week as July 8
MOCK_NOW_THU = datetime(2026, 7, 9, 12, 0, 0, tzinfo=timezone.utc)
# Sun, July 12, 2026 (Weekday = 6) - New week starts
MOCK_NOW_SUN = datetime(2026, 7, 12, 12, 0, 0, tzinfo=timezone.utc)
# Sat, Aug 1, 2026 - New month starts
MOCK_NOW_AUG = datetime(2026, 8, 1, 12, 0, 0, tzinfo=timezone.utc)


def setup_mock_db(plan: str, question_count: int, last_reset_at: datetime):
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.data = [{
        "id": "real-uuid-style-id-123",
        "email": "user@test.com",
        "avatar_url": None,
        "plan": plan,
        "chamber_level": 1,
        "question_count": question_count,
        "last_reset_at": last_reset_at.isoformat(),
        "created_at": last_reset_at.isoformat()
    }]
    
    mock_select = MagicMock()
    mock_eq = MagicMock()
    mock_eq.execute.return_value = mock_response
    mock_select.eq.return_value = mock_eq
    mock_client.table.return_value.select.return_value = mock_select
    
    return SupabaseDatabase(mock_client), mock_client


@pytest.mark.asyncio
async def test_free_plan_resets_when_sunday_crossed():
    """Valida que o plano FREE reseta quando cruza o domingo."""
    # last_reset foi quarta-feira, July 8
    db, mock_client = setup_mock_db(plan="free", question_count=3, last_reset_at=MOCK_NOW_WED)
    
    # Mock datetime.now para retornar Domingo, July 12
    with patch("app.infrastructure.supabase.supabase_database.datetime") as mock_datetime:
        mock_datetime.now.return_value = MOCK_NOW_SUN
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        profile = await db.get_user_profile("real-uuid-style-id-123")
        
    assert profile.question_count == 0
    # Verifica se o update foi chamado no banco
    mock_client.table.assert_any_call("users")
    mock_client.table().update.assert_called_with({"question_count": 0, "last_reset_at": MOCK_NOW_SUN.isoformat()})


@pytest.mark.asyncio
async def test_free_plan_no_reset_in_same_week():
    """Valida que o plano FREE NÃO reseta no mesmo período semanal (quarta para quinta)."""
    # last_reset foi quarta-feira, July 8
    db, mock_client = setup_mock_db(plan="free", question_count=3, last_reset_at=MOCK_NOW_WED)
    
    # Mock datetime.now para retornar Quinta, July 9
    with patch("app.infrastructure.supabase.supabase_database.datetime") as mock_datetime:
        mock_datetime.now.return_value = MOCK_NOW_THU
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        profile = await db.get_user_profile("real-uuid-style-id-123")
        
    assert profile.question_count == 3
    # Verifica que update não foi chamado
    mock_client.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_premium_plan_resets_when_month_crossed():
    """Valida que planos pagos resetam quando cruzam o mês calendário (dia 1)."""
    # last_reset foi quarta-feira, July 8
    db, mock_client = setup_mock_db(plan="premium", question_count=15, last_reset_at=MOCK_NOW_WED)
    
    # Mock datetime.now para retornar Sábado, Aug 1 (novo mês)
    with patch("app.infrastructure.supabase.supabase_database.datetime") as mock_datetime:
        mock_datetime.now.return_value = MOCK_NOW_AUG
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        profile = await db.get_user_profile("real-uuid-style-id-123")
        
    assert profile.question_count == 0
    mock_client.table().update.assert_called_with({"question_count": 0, "last_reset_at": MOCK_NOW_AUG.isoformat()})


@pytest.mark.asyncio
async def test_premium_plan_no_reset_in_same_month():
    """Valida que planos pagos NÃO resetam dentro do mesmo mês calendário."""
    # last_reset foi quarta-feira, July 8
    db, mock_client = setup_mock_db(plan="premium", question_count=15, last_reset_at=MOCK_NOW_WED)
    
    # Mock datetime.now para retornar Domingo, July 12 (mesmo mês)
    with patch("app.infrastructure.supabase.supabase_database.datetime") as mock_datetime:
        mock_datetime.now.return_value = MOCK_NOW_SUN
        mock_datetime.fromisoformat = datetime.fromisoformat
        
        profile = await db.get_user_profile("real-uuid-style-id-123")
        
    assert profile.question_count == 15
    mock_client.table().update.assert_not_called()


@pytest.mark.asyncio
async def test_increment_with_current_count_sets_exact_new_value():
    """Valida que passar current_count incrementa atomicamente sem re-consultar o banco."""
    db, mock_client = setup_mock_db(plan="free", question_count=3, last_reset_at=MOCK_NOW_WED)
    
    # Simula que o perfil foi resetado para 0 no início do use case
    await db.increment_user_question_count("real-uuid-style-id-123", current_count=0)
    
    mock_client.table.assert_called_with("users")
    mock_client.table().update.assert_called_with({"question_count": 1})

