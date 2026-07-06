#!/usr/bin/env python3
"""Verify database schema refactoring changes."""

from __future__ import annotations

import os
import sys

# Add repo root to path
repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, repo_root)

# Load .env file for testing
try:
    from dotenv import load_dotenv
    env_path = os.path.join(repo_root, ".env")
    if os.path.isfile(env_path):
        load_dotenv(env_path, override=False)
except ImportError:
    pass  # dotenv not available, use environment variables directly

from db_migrations.runner import TARGETS, load_target_migrations


def verify_migration_targets():
    """Verify all new migration targets are registered."""
    expected_targets = [
        "infrastructure",
        "auth",
        "verification",
        "risk",
        "recommendation",
        "matchmaking",
        "chat",
        "discovery",
        "persona",
        "relationship_ledger",
    ]

    print("=== Verifying Migration Targets ===")
    for target in expected_targets:
        if target in TARGETS:
            print(f"✅ {target}: registered")
            # Try loading migrations
            try:
                migrations = load_target_migrations(target)
                print(f"   - {len(migrations)} migrations loaded")
            except Exception as e:
                print(f"   ❌ Failed to load migrations: {e}")
        else:
            print(f"❌ {target}: NOT registered")

    return all(target in TARGETS for target in expected_targets)


def verify_env_variables():
    """Verify all new environment variables are set."""
    expected_vars = [
        "HER_INFRASTRUCTURE_DB",
        "HER_AUTH_DB",
        "HER_VERIFICATION_DB",
        "HER_RISK_DB",
        "PARTNER_RECOMMENDATION_DB",
        "PARTNER_MATCHMAKING_DB",
        "PARTNER_CHAT_DB",
        "PARTNER_DISCOVERY_DB",
        "HER_RELATION_LEDGER_DB",
    ]

    print("\n=== Verifying Environment Variables ===")
    all_set = True
    for var in expected_vars:
        value = os.environ.get(var)
        if value:
            print(f"✅ {var}: {value[:50]}...")
        else:
            print(f"❌ {var}: NOT set")
            all_set = False

    return all_set


def verify_schema_functions():
    """Verify all schema functions exist."""
    import outer_system_mysql_schema as schema

    expected_functions = [
        "infrastructure_tables",
        "auth_tables",
        "verification_tables",
        "risk_tables",
        "chat_tables_core",
        "chat_tables",
        "recommendation_tables",
        "matchmaking_tables",
        "discovery_tables",
        "relationship_ledger_tables",
    ]

    print("\n=== Verifying Schema Functions ===")
    all_exist = True
    for func_name in expected_functions:
        if hasattr(schema, func_name):
            func = getattr(schema, func_name)
            tables = func()
            print(f"✅ {func_name}: {len(tables)} tables")
        else:
            print(f"❌ {func_name}: NOT found")
            all_exist = False

    return all_exist


def verify_system_tables_dict():
    """Verify SYSTEM_TABLES dictionary includes all new targets."""
    import outer_system_mysql_schema as schema

    expected_keys = [
        "infrastructure",
        "auth",
        "verification",
        "risk",
        "recommendation",
        "matchmaking",
        "chat",
        "discovery",
        "relationship_ledger",
    ]

    print("\n=== Verifying SYSTEM_TABLES Dictionary ===")
    all_exist = True
    for key in expected_keys:
        if key in schema.SYSTEM_TABLES:
            tables = schema.SYSTEM_TABLES[key]
            print(f"✅ {key}: {len(tables)} tables")
        else:
            print(f"❌ {key}: NOT in SYSTEM_TABLES")
            all_exist = False

    return all_exist


def verify_storage_modules():
    """Verify all storage modules exist."""
    expected_modules = [
        ("infrastructure_system", "external-systems.infrastructure-system.infrastructure_system"),
        ("auth_system", "external-systems.auth-system.auth_system"),
        ("verification_system", "external-systems.verification-system.verification_system"),
        ("risk_system", "external-systems.risk-system.risk_system"),
    ]

    print("\n=== Verifying Storage Modules ===")
    all_exist = True
    for module_name, module_path in expected_modules:
        try:
            # Try importing
            import importlib
            module = importlib.import_module(module_path)
            print(f"✅ {module_name}: imported")

            # Check for required functions
            required_funcs = ["connect_db", "initialize_database", "reset_all_tables"]
            for func in required_funcs:
                if hasattr(module, func):
                    print(f"   - {func}: exists")
                else:
                    print(f"   ❌ {func}: missing")
                    all_exist = False
        except ImportError as e:
            print(f"❌ {module_name}: import failed ({e})")
            all_exist = False

    return all_exist


def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Database Schema Refactoring Verification")
    print("=" * 60)

    results = {
        "Migration Targets": verify_migration_targets(),
        "Environment Variables": verify_env_variables(),
        "Schema Functions": verify_schema_functions(),
        "SYSTEM_TABLES": verify_system_tables_dict(),
        "Storage Modules": verify_storage_modules(),
    }

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{name}: {status}")

    all_passed = all(results.values())
    if all_passed:
        print("\n🎉 All verifications passed!")
        return 0
    else:
        print("\n⚠️  Some verifications failed. Please review.")
        return 1


if __name__ == "__main__":
    sys.exit(main())