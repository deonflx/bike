import os
import jwt
from jwt import PyJWKClient
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework import authentication, exceptions

User = get_user_model()


class ClerkAuthentication(authentication.BaseAuthentication):
    """
    DRF Authentication backend that verifies Clerk JWT session tokens.
    Tokens are received in the HTTP header:
        Authorization: Bearer <clerk_session_token>
    """

    _jwks_clients = {}

    @classmethod
    def get_jwks_client(cls, jwks_url: str) -> PyJWKClient:
        if jwks_url not in cls._jwks_clients:
            cls._jwks_clients[jwks_url] = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=3600)
        return cls._jwks_clients[jwks_url]

    def authenticate(self, request):
        auth_header = request.headers.get('Authorization') or request.META.get('HTTP_AUTHORIZATION')
        if not auth_header or not auth_header.startswith('Bearer '):
            return None

        token = auth_header.split(' ', 1)[1].strip()
        if not token:
            return None

        try:
            # 1. Unverified decode to inspect header & payload
            unverified_header = jwt.get_unverified_header(token)
            unverified_payload = jwt.decode(token, options={"verify_signature": False})

            # 2. Determine JWKS URL
            # Priority:
            #   a) Explicit settings.CLERK_JWKS_URL
            #   b) Environment variable CLERK_JWKS_URL
            #   c) Dynamic issuer from token: f"{issuer}/.well-known/jwks.json"
            jwks_url = getattr(settings, 'CLERK_JWKS_URL', None) or os.environ.get('CLERK_JWKS_URL')
            if not jwks_url:
                issuer = unverified_payload.get('iss')
                if issuer:
                    issuer_clean = issuer.rstrip('/')
                    jwks_url = f"{issuer_clean}/.well-known/jwks.json"
                else:
                    jwks_url = "https://api.clerk.com/v1/jwks"

            # 3. Retrieve signing key & verify token
            jwks_client = self.get_jwks_client(jwks_url)
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options={
                    "verify_aud": False,  # Clerk default session tokens don't enforce aud unless custom
                    "verify_exp": True,
                }
            )

        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Clerk token has expired")
        except jwt.PyJWTError as e:
            raise exceptions.AuthenticationFailed(f"Invalid Clerk token: {str(e)}")
        except Exception as e:
            raise exceptions.AuthenticationFailed(f"Clerk authentication failed: {str(e)}")

        # 4. Resolve Django User
        clerk_user_id = payload.get('sub')
        if not clerk_user_id:
            raise exceptions.AuthenticationFailed("Invalid Clerk token: missing 'sub' claim")

        email = (
            payload.get('email')
            or payload.get('email_address')
            or f"{clerk_user_id}@clerk.user"
        )
        first_name = payload.get('first_name', '')
        last_name = payload.get('last_name', '')

        user, created = User.objects.get_or_create(
            username=clerk_user_id,
            defaults={
                'email': email,
                'first_name': first_name,
                'last_name': last_name,
            }
        )

        # Update email/names if newly available
        fields_to_update = []
        if email and user.email != email and not user.email.endswith('@clerk.user'):
            user.email = email
            fields_to_update.append('email')
        if first_name and user.first_name != first_name:
            user.first_name = first_name
            fields_to_update.append('first_name')
        if last_name and user.last_name != last_name:
            user.last_name = last_name
            fields_to_update.append('last_name')
        if fields_to_update:
            user.save(update_fields=fields_to_update)

        return (user, payload)
