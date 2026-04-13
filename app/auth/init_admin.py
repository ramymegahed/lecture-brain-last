import os
import logging
from app.models.user import User
from app.auth.jwt import get_password_hash

logger = logging.getLogger(__name__)

async def create_initial_admin():
    admin_email = os.getenv("FIRST_SUPERUSER_EMAIL", "admin@lecturebrain.com")
    admin_password = os.getenv("FIRST_SUPERUSER_PASSWORD", "admin123")
    
    admin_user = await User.find_one(User.email == admin_email)
    if not admin_user:
        hashed_password = get_password_hash(admin_password)
        admin_user = User(
            email=admin_email,
            hashed_password=hashed_password,
            role="admin",
            is_active=True
        )
        await admin_user.insert()
        logger.info(f"Created initial admin user with email: {admin_email}")
    else:
        # Ensure it has admin role if it already exists but lacks the role
        if admin_user.role != "admin":
            admin_user.role = "admin"
            await admin_user.save()
            logger.info(f"Updated existing user {admin_email} to admin role.")
        else:
            logger.info("Initial admin user already exists.")
