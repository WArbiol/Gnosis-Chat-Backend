from fastapi import Request
from slowapi import Limiter

def get_ip_address(request: Request) -> str:
    """
    Extracts the client's IP address, respecting reverse proxy headers.
    """
    # Check X-Forwarded-For header (commonly set by load balancers like Railway, Cloudflare, etc.)
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        # The first IP in the comma-separated list is the client IP
        return forwarded_for.split(",")[0].strip()
    
    # Check X-Real-IP header
    real_ip = request.headers.get("x-real-ip")
    if real_ip:
        return real_ip.strip()
    
    # Fallback to client host
    if request.client:
        return request.client.host
    return "127.0.0.1"

# 200 global limit per minute by IP
limiter = Limiter(
    key_func=get_ip_address,
    default_limits=["200/minute"]
)
