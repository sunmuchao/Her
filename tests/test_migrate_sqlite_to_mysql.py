import unittest

import migrate_sqlite_to_mysql as migration


class MigrateSqliteToMysqlTests(unittest.TestCase):
    def test_parse_mysql_dsn_supports_charset_and_collation(self):
        config = migration.parse_mysql_dsn(
            "mysql://demo:secret@127.0.0.1:3307/her_state?charset=utf8mb4&collation=utf8mb4_general_ci"
        )

        self.assertEqual(config["host"], "127.0.0.1")
        self.assertEqual(config["port"], 3307)
        self.assertEqual(config["user"], "demo")
        self.assertEqual(config["password"], "secret")
        self.assertEqual(config["database"], "her_state")
        self.assertEqual(config["charset"], "utf8mb4")
        self.assertEqual(config["collation"], "utf8mb4_general_ci")

    def test_destination_table_name_applies_prefix_verbatim(self):
        self.assertEqual(
            migration.destination_table_name("match_cases", "rec_"),
            "rec_match_cases",
        )
        self.assertEqual(
            migration.destination_table_name("match_cases", ""),
            "match_cases",
        )

    def test_build_create_table_sql_rewrites_foreign_key_targets_with_prefix(self):
        table = migration.SYSTEM_TABLES["recommendation"][1]
        sql = migration.build_create_table_sql(
            table,
            prefix="rec_",
            config={"charset": "utf8mb4", "collation": "utf8mb4_unicode_ci"},
        )

        self.assertIn("CREATE TABLE IF NOT EXISTS `rec_profile_recommendations`", sql)
        self.assertIn("REFERENCES `rec_saved_search_subscriptions` (`subscription_id`)", sql)
        self.assertIn("UNIQUE KEY", sql)

    def test_build_upsert_sql_updates_non_primary_key_columns_only(self):
        table = migration.SYSTEM_TABLES["matchmaking"][1]
        sql = migration.build_upsert_sql(table, prefix="mm_")

        self.assertIn("INSERT INTO `mm_matchmaking_edges`", sql)
        _, update_clause = sql.split("ON DUPLICATE KEY UPDATE", 1)
        self.assertNotIn("`edge_id` = VALUES(`edge_id`)", update_clause)
        self.assertIn("`owner_member_id` = VALUES(`owner_member_id`)", update_clause)
        self.assertIn("`payload_json` = VALUES(`payload_json`)", update_clause)

    def test_build_select_sql_orders_by_primary_key(self):
        table = migration.SYSTEM_TABLES["recommendation"][0]
        sql = migration.build_select_sql(table)

        self.assertIn('FROM "saved_search_subscriptions"', sql)
        self.assertIn('ORDER BY "subscription_id"', sql)

    def test_normalize_mysql_value_converts_bool_and_memoryview(self):
        self.assertEqual(migration.normalize_mysql_value(True), 1)
        self.assertEqual(migration.normalize_mysql_value(False), 0)
        self.assertEqual(
            migration.normalize_mysql_value(memoryview(b"abc")),
            b"abc",
        )


if __name__ == "__main__":
    unittest.main()
