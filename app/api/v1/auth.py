from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.services import auth_service

router = APIRouter()

class ProfileUpdate(BaseModel):
    display_name: str | None = None
    avatar_url: str | None = None
    chamber_level: int | None = None

@router.get("/me", response_model=UserProfile)
async def get_me(current_user: UserProfile = Depends(get_current_user)) -> UserProfile:
    """Return the profile of the currently authenticated user."""
    # current_user from get_current_user only has ID and Email from the JWT token.
    # We fetch the full profile from the database here.
    return await auth_service.get_user_profile(current_user.id)

@router.patch("/me", response_model=UserProfile)
async def update_me(
    update_data: ProfileUpdate,
    current_user: UserProfile = Depends(get_current_user)
) -> UserProfile:
    """Update user profile fields."""
    from app.core.dependencies import get_supabase_client
    
    client = get_supabase_client()
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    
    if update_dict:
        client.table("users").update(update_dict).eq("id", current_user.id).execute()
        
    return await auth_service.get_user_profile(current_user.id)

class VerifyPasscodeRequest(BaseModel):
    passcode: str

@router.post("/second-chamber/verify")
async def verify_second_chamber(
    request: VerifyPasscodeRequest,
    current_user: UserProfile = Depends(get_current_user)
):
    # 1. Fast local verification (typo-tolerant string check)
    cleaned_pass = request.passcode.lower().strip()
    is_valid_local = (
        ("paz" in cleaned_pass or "pas" in cleaned_pass or "pax" in cleaned_pass) and
        ("inverencial" in cleaned_pass or "inveremcial" in cleaned_pass) and
        ("jachin" in cleaned_pass or "jaquim" in cleaned_pass or "jakin" in cleaned_pass) and
        ("boaz" in cleaned_pass or "boas" in cleaned_pass)
    )
    
    # Define a pydantic model for JSON validation
    class PasscodeEvaluation(BaseModel):
        valid: bool
        reason: str

    if is_valid_local:
        evaluation = PasscodeEvaluation(valid=True, reason="Local verification passed.")
    else:
        # 2. Get LLM instance as a fallback
        from app.agents.nodes.utils import get_llm
        llm = get_llm()
        
        # 3. Call LLM to evaluate the passcode
        prompt = (
            "Você deve analisar se a resposta fornecida pelo usuário corresponde à saudação/passe sagrado:\n"
            "\"Paz Inverencial, Jachin Boaz\"\n\n"
            "Exemplos de respostas válidas (mesmo com erros de digitação, acentuação ou grafia):\n"
            "- pas inveremcial, jaquim boas\n"
            "- Pax Inverencial Jakin Boazz\n"
            "- Paz, Inverencial, Jachin, Boaz..\n"
            "- Paz Inverencial, Jachin Boaz\n"
            "- paz inverencial jachin boaz\n\n"
            "A resposta NÃO deve ser aceita se for completamente diferente ou não contiver a essência da saudação e das palavras Jachin/Boaz.\n\n"
            f"Resposta do usuário: \"{request.passcode}\"\n\n"
            "Retorne OBRIGATORIAMENTE um JSON estruturado com o seguinte formato:\n"
            "{\n"
            "  \"valid\": true ou false,\n"
            "  \"reason\": \"Breve explicação em português do porquê ser válido ou inválido\"\n"
            "}"
        )
        
        try:
            evaluation = await llm.generate_json(
                prompt=prompt,
                response_schema=PasscodeEvaluation,
                system_instruction="Você é um validador de passes sagrados gnósticos e deve retornar apenas JSON estruturado."
            )
        except Exception as e:
            # Fallback basic string matching if LLM fails
            cleaned_pass = request.passcode.lower().strip()
            is_valid = ("paz" in cleaned_pass or "pas" in cleaned_pass or "pax" in cleaned_pass) and \
                       ("inverencial" in cleaned_pass or "inveremcial" in cleaned_pass) and \
                       ("jachin" in cleaned_pass or "jaquim" in cleaned_pass or "jakin" in cleaned_pass) and \
                       ("boaz" in cleaned_pass or "boas" in cleaned_pass)
            evaluation = PasscodeEvaluation(
                valid=is_valid,
                reason="Fallback string matching used."
            )

    if evaluation.valid:
        # Update user's chamber_level to 2 in the database
        from app.core.dependencies import get_supabase_client
        client = get_supabase_client()
        client.table("users").update({"chamber_level": 2}).eq("id", current_user.id).execute()
        
        # Get updated user profile
        updated_profile = await auth_service.get_user_profile(current_user.id)
        return {"valid": True, "reason": "Acesso concedido.", "user": updated_profile.model_dump()}
    else:
        return {"valid": False, "reason": "Passe incorreto. Tente novamente."}


@router.post("/delete-account")
async def delete_account(current_user: UserProfile = Depends(get_current_user)):
    """Permanently delete user profile, conversation data, active Stripe subscription, and authentication record."""
    return await auth_service.delete_user_account(current_user.id)

