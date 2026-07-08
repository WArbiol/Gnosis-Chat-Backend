import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient

from app.core.config import settings
from app.schemas.user import UserProfile

bearer_scheme = HTTPBearer()

# Cache the JWKS client globally to avoid fetching the keys on every request
jwks_url = f"{settings.supabase_url}/auth/v1/.well-known/jwks.json"
jwks_client = PyJWKClient(jwks_url, cache_keys=True)


async def _get_or_create_profile(user_id: str, email: str) -> UserProfile:
    try:
        from app.core.dependencies import get_supabase_client
        from app.infrastructure.supabase.supabase_database import SupabaseDatabase
        supabase_client = get_supabase_client()
        db = SupabaseDatabase(supabase_client)
        return await db.get_user_profile(user_id, email=email)
    except Exception as db_err:
        print(f"DEBUG AUTH: Falha ao garantir perfil para {user_id}: {db_err}")
        return UserProfile(
            id=user_id,
            email=email,
        )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> UserProfile:
    """Decode Supabase JWT and return the current user profile."""
    token = credentials.credentials
    alg = "UNKNOWN"

    # Bypass for testing in development mode
    if settings.app_env == "development":
        if token.startswith("test-"):
            user_id = token.replace("test-", "") or "test-user-123"
            return await _get_or_create_profile(user_id, f"{user_id}@gnosis.chat")
        try:
            # Em desenvolvimento, se o token for um JWT válido estruturalmente (mesmo com assinatura mockada/inválida),
            # nós decodificamos sem verificar a assinatura para facilitar testes locais e offline.
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("sub")
            if user_id:
                email = payload.get("email", f"{user_id}@gnosis.chat")
                print(f"DEBUG AUTH: Dev mode bypass verification for token. User ID: {user_id}")
                return await _get_or_create_profile(user_id, email)
        except Exception as dev_err:
            print(f"DEBUG AUTH: Dev mode unverified decode failed: {dev_err}")

    try:
        # Detect algorithm to decide verification method
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        
        if alg == "HS256":
            # For HS256, we use the JWT Secret from Supabase (Symmetric)
            secret = settings.supabase_jwt_secret or settings.supabase_service_role_key
            if not secret:
                raise ValueError("SUPABASE_JWT_SECRET is not configured for HS256 verification")
            
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                audience="authenticated",
            )
        else:
            # For Asymmetric (RS256 or ES256), we use JWKS from Supabase
            signing_key = jwks_client.get_signing_key_from_jwt(token)
            
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256", "ES256"],
                audience="authenticated",
                issuer=settings.supabase_url + "/auth/v1" if not settings.supabase_url.endswith("/auth/v1") else settings.supabase_url
            )
        
        # Extract user_id
        user_id = payload.get("sub")
        if not user_id:
            raise ValueError("Missing 'sub' in token payload")
            
        # Extract email from the token payload directly
        email = payload.get("email", "")
        
        return await _get_or_create_profile(user_id, email)
        
    except jwt.PyJWKClientError as e:
        print(f"DEBUG AUTH: JWKS Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unable to fetch JWKS from Supabase: {e}"
        )
    except jwt.InvalidTokenError as e:
        print(f"DEBUG AUTH: Invalid Token ({alg}): {e}. Token starts with: {token[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {e}"
        )
    except Exception as e:
        print(f"DEBUG AUTH: Unexpected login error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {e}"
        )
