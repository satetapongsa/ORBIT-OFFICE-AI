"""Lock every table away from hosted data APIs (Supabase PostgREST)

Supabase publishes the ``public`` schema through its REST/GraphQL API with the publishable
``anon`` key. The application never uses that API: only the backend, connecting as the table
owner, may read the data. So every table gets row level security with **no policies** (deny
all for every role except the owner, which bypasses RLS) and, where Supabase's API roles
exist, their privileges are revoked, including on tables created by later migrations.

On a plain PostgreSQL (Docker Compose, tests) the roles do not exist and RLS has no effect on
the owner, so behaviour is unchanged.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-19 10:00:00.000000+00:00
"""

from collections.abc import Sequence

from alembic import op


revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

API_ROLES = ("anon", "authenticated")


def upgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE t record;
        BEGIN
            FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
                EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t.tablename);
            END LOOP;
        END $$;
        """
    )
    for role in API_ROLES:
        op.execute(
            f"""
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
                    REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role};
                    REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role};
                    REVOKE ALL ON ALL FUNCTIONS IN SCHEMA public FROM {role};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role};
                    ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON FUNCTIONS FROM {role};
                END IF;
            END $$;
            """
        )


def downgrade() -> None:
    op.execute(
        """
        DO $$
        DECLARE t record;
        BEGIN
            FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
                EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t.tablename);
            END LOOP;
        END $$;
        """
    )
