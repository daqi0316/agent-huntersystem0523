#!/usr/bin/env python3
"""
AI Recruitment System - Database Seed Script
Populates the database with sample data for development.
"""

import asyncio
import sys
import os
from datetime import datetime, timedelta
from uuid import uuid4

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def seed_database():
    """
    Seed the database with sample JobPositions, Candidates, and Applications.
    Run after alembic upgrade head.
    """
    print("=== Seeding Database ===")
    print()

    # Import here so app module is available
    try:
        from app.core.database import AsyncSessionLocal
        from app.core.security import hash_password
        from app.models.user import User, UserRole
        from app.models.job_position import JobPosition
        from app.models.candidate import Candidate
        from app.models.application import Application
        from sqlalchemy import text
    except ImportError as e:
        print(f"[ERROR] Could not import app modules: {e}")
        print("Make sure you run this from the apps/api/ directory with the virtualenv active.")
        sys.exit(1)

    async with AsyncSessionLocal() as session:
        # Check if already seeded
        result = await session.execute(text("SELECT COUNT(*) FROM job_positions"))
        count = result.scalar()
        if count and count > 0:
            print(f"Database already has {count} job positions. Skipping seed.")
            return

        print("Creating admin user...")
        admin_user = User(
            id=str(uuid4()),
            email="admin@example.com",
            hashed_password=hash_password("admin123"),
            name="Admin",
            role=UserRole.ADMIN,
        )
        session.add(admin_user)

        hr_user = User(
            id=str(uuid4()),
            email="hr@example.com",
            hashed_password=hash_password("hr123456"),
            name="HR Zhang",
            role=UserRole.HR,
        )
        session.add(hr_user)

        print("Creating sample job positions...")
        jobs = [
            JobPosition(
                id=str(uuid4()),
                title="Senior Frontend Engineer",
                department="Engineering",
                description="Build and maintain our React/Next.js frontend applications.",
                requirements="5+ years React experience, TypeScript, Next.js preferred",
                location="Remote",
                salary_range="200K-350K",
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
            JobPosition(
                id=str(uuid4()),
                title="Backend ML Engineer",
                department="AI",
                description="Design and implement ML pipelines for resume parsing and matching.",
                requirements="3+ years Python, ML/DL experience, NLP background preferred",
                location="Remote",
                salary_range="250K-400K",
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
            JobPosition(
                id=str(uuid4()),
                title="Product Manager - AI Products",
                department="Product",
                description="Define product strategy for AI-powered recruitment features.",
                requirements="5+ years PM experience, technical background, AI product experience",
                location="San Francisco, CA",
                salary_range="180K-280K",
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
        ]
        session.add_all(jobs)

        print("Creating sample candidates...")
        candidates = [
            Candidate(
                id=str(uuid4()),
                name="Alice Zhang",
                email="alice.zhang@example.com",
                phone="+1-555-0101",
                summary="Senior frontend engineer with 6 years of React experience.",
                skills=["React", "TypeScript", "Next.js", "Tailwind CSS", "GraphQL"],
                experience_years=6,
                education="MS Computer Science, Stanford",
                current_company="TechCorp",
                current_title="Senior Frontend Engineer",
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
            Candidate(
                id=str(uuid4()),
                name="Bob Chen",
                email="bob.chen@example.com",
                phone="+1-555-0102",
                summary="ML engineer with expertise in NLP and large language models.",
                skills=["Python", "PyTorch", "NLP", "LLM", "RAG", "FastAPI"],
                experience_years=4,
                education="PhD Machine Learning, MIT",
                current_company="AILabs",
                current_title="ML Engineer",
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
            Candidate(
                id=str(uuid4()),
                name="Carol Liu",
                email="carol.liu@example.com",
                phone="+1-555-0103",
                summary="Product leader with deep experience in AI-powered SaaS products.",
                skills=["Product Strategy", "AI/ML", "SaaS", "User Research", "Data Analysis"],
                experience_years=8,
                education="MBA, Harvard Business School",
                current_company="SaaSPro",
                current_title="Senior Product Manager",
                status="active",
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            ),
        ]
        session.add_all(candidates)

        print("Creating sample applications...")
        applications = [
            Application(
                id=str(uuid4()),
                candidate_id=candidates[0].id,
                job_id=jobs[0].id,
                status="screening",
                match_score=0.92,
                ai_summary="Strong match for Senior Frontend Engineer. Extensive React/TypeScript experience.",
                created_at=datetime.utcnow() - timedelta(days=2),
                updated_at=datetime.utcnow(),
            ),
            Application(
                id=str(uuid4()),
                candidate_id=candidates[1].id,
                job_id=jobs[1].id,
                status="pending",
                match_score=0.88,
                ai_summary="Excellent ML background with NLP expertise. PhD from MIT.",
                created_at=datetime.utcnow() - timedelta(days=1),
                updated_at=datetime.utcnow(),
            ),
            Application(
                id=str(uuid4()),
                candidate_id=candidates[2].id,
                job_id=jobs[2].id,
                status="interview",
                match_score=0.85,
                ai_summary="Strong product background with AI SaaS experience. MBA from HBS.",
                created_at=datetime.utcnow() - timedelta(hours=12),
                updated_at=datetime.utcnow(),
            ),
        ]
        session.add_all(applications)

        await session.commit()
        print()
        print("  Created 2 users (admin@example.com / admin123)")
        print(f"  Created {len(jobs)} job positions")
        print(f"  Created {len(candidates)} candidates")
        print(f"  Created {len(applications)} applications")
        print()
        print("Database seeded successfully!")


if __name__ == "__main__":
    asyncio.run(seed_database())
