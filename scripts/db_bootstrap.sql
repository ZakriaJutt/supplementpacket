-- Run once as the local superuser (owner role). Creates the non-superuser application
-- role used by the API, the worker and every isolation test. It cannot bypass RLS and
-- owns no tables, so row-level security always applies to it (AD-02).
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'supplementpacket_app') THEN
    CREATE ROLE supplementpacket_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$;
ALTER ROLE supplementpacket_app NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE;
