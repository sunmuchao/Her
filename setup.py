from __future__ import annotations

from setuptools import find_packages, setup


DESCRIPTION = (
    "Relationship-operations prototype: search, persona memory, recommendation, and matchmaking."
)

INSTALL_REQUIRES = [
    "apscheduler>=3.10,<4",
    "openai>=1.0.0",
    "openai-agents",
    "pydantic>=2.0.0",
    "pymysql>=1.0.0",
    "python-dotenv>=1.0.0",
]

DEV_REQUIRES = [
    "pytest>=7.0.0",
    "setuptools>=61.2",
]

ROOT_PACKAGES = find_packages(
    where=".",
    include=[
        "db_migrations",
        "db_migrations.*",
        "async_jobs",
        "async_jobs.*",
        "match_domain",
        "match_domain.*",
        "task_scheduler",
        "task_scheduler.*",
        "observability",
        "observability.*",
        "partner_search",
        "partner_search.*",
        "persona_memory_sync",
        "persona_memory_sync.*",
        "profile_service",
        "profile_service.*",
    ],
)

EXTERNAL_PACKAGES = (
    find_packages(
        where="external-systems/partner-recommendation-system",
        include=["recommendation_system", "recommendation_system.*"],
    )
    + find_packages(
        where="external-systems/partner-matchmaking-system",
        include=["matchmaking_system", "matchmaking_system.*"],
    )
    + find_packages(
        where="external-systems/partner-chat-system",
        include=["chat_system", "chat_system.*"],
    )
    + find_packages(
        where="external-systems/partner-http-gateway",
        include=["gateway", "gateway.*"],
    )
    + find_packages(
        where="external-systems/partner-discovery-system",
        include=["discovery_system", "discovery_system.*"],
    )
)


setup(
    name="her",
    version="0.1.0",
    description=DESCRIPTION,
    python_requires=">=3.10",
    install_requires=INSTALL_REQUIRES,
    extras_require={"dev": DEV_REQUIRES},
    packages=ROOT_PACKAGES + EXTERNAL_PACKAGES,
    package_dir={
        "": ".",
        "recommendation_system": "external-systems/partner-recommendation-system/recommendation_system",
        "matchmaking_system": "external-systems/partner-matchmaking-system/matchmaking_system",
        "chat_system": "external-systems/partner-chat-system/chat_system",
        "gateway": "external-systems/partner-http-gateway/gateway",
        "discovery_system": "external-systems/partner-discovery-system/discovery_system",
    },
    py_modules=[
        "her_external_systems",
        "generate_virtual_profiles",
        "her_activate_repo",
        "her_env",
        "her_json_utils",
        "her_monorepo_bootstrap",
        "her_repo_path_bootstrap",
        "her_runtime_context",
        "her_time_utils",
        "mysql_source_config",
        "outer_mysql_compat",
        "outer_system_mysql_schema",
        "partner_moderation",
        "profile_detail_reader",
        "profile_source_refs",
    ],
    entry_points={
        "console_scripts": [
            "partner-search=partner_search.search_candidates:main",
            "persona-memory-sync=persona_memory_sync.cli:main",
        ]
    },
)
