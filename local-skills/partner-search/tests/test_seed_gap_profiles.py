import pathlib
import sys
import types
import unittest


BACKFILL_SCRIPT_PATH = (
    pathlib.Path(__file__).resolve().parents[1] / "scripts" / "backfill_profile_enrichment.py"
)
backfill_profile_enrichment = types.ModuleType("backfill_profile_enrichment")
backfill_profile_enrichment.__file__ = str(BACKFILL_SCRIPT_PATH)
exec(
    compile(BACKFILL_SCRIPT_PATH.read_text(encoding="utf-8"), str(BACKFILL_SCRIPT_PATH), "exec"),
    backfill_profile_enrichment.__dict__,
)
sys.modules["backfill_profile_enrichment"] = backfill_profile_enrichment

SCRIPT_PATH = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "seed_gap_profiles.py"
seed_gap_profiles = types.ModuleType("seed_gap_profiles")
seed_gap_profiles.__file__ = str(SCRIPT_PATH)
exec(
    compile(SCRIPT_PATH.read_text(encoding="utf-8"), str(SCRIPT_PATH), "exec"),
    seed_gap_profiles.__dict__,
)


class SeedGapProfilesTests(unittest.TestCase):
    def test_resolve_connection_config_from_source(self):
        args = seed_gap_profiles.parse_args.__globals__["argparse"].Namespace(
            source="mysql://demo:pw@127.0.0.1:3306/her?table=profiles&photos_table=profile_photos",
            host=None,
            port=None,
            user=None,
            password=None,
            database=None,
            table=None,
            photos_table=None,
            charset=None,
        )
        config = seed_gap_profiles.resolve_connection_config(args)
        self.assertEqual(config["database"], "her")
        self.assertEqual(config["table"], "profiles")
        self.assertEqual(config["photos_table"], "profile_photos")


if __name__ == "__main__":
    unittest.main()
